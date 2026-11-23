"""Isolate the published UART test's restore phase on two genuine PR paths."""
import hashlib,json,re,shutil,subprocess,sys,tempfile
from pathlib import Path
root=Path(sys.argv[1]).resolve()
out=Path(__file__).resolve().parents[1]/'evidence/owned.json'
paths=['hw/ip/uart/dv/env/uart_scoreboard.sv','hw/ip/uart/rtl/uart_core.sv']
result={}
def run(args,w,**kw):
    return subprocess.run(args,cwd=w,check=True,capture_output=True,**kw)
def hashes(w):
    return [hashlib.sha256((w/p).read_bytes()).hexdigest() for p in paths]
for version in ('10','11'):
    row=next(r for r in map(json.loads,(root/f'v{version}.jsonl').read_text().splitlines()) if r['repo']=='opentitan' and r['number']==21632)
    with tempfile.TemporaryDirectory() as t:
        w=Path(t)/'repo';shutil.copytree(root/'uart',w)
        run(['git','init','-q'],w);run(['git','add','.'],w)
        run(['git','-c','user.email=a@localhost','-c','user.name=study','commit','-qm','two upstream files'],w)
        base=hashes(w)
        run(['git','apply',*['--include='+p for p in paths],'-'],w,input=row['fix_patch'].encode())
        patched=hashes(w);assert all(x!=y for x,y in zip(base,patched))
        block=re.search(r"(?ms)^while IFS= read -r f; do\n.*?^HWE_TEST_OWNED$",row['tb_script'])
        if block:
            names=block[0].split("<<'HWE_TEST_OWNED'\n")[1].splitlines()[:-1]
            assert all(re.fullmatch(r'hw/ip/uart/[\w./-]+',p) and '..' not in p for p in names)
            run(['bash','-ec','hwe_base=$(git rev-parse HEAD)\n'+block[0]],w)
        final=hashes(w)
        result[version]={p:{'base':a,'patched':b,'after_restore_phase':c} for p,a,b,c in zip(paths,base,patched,final)}
out.write_text(json.dumps(result,indent=2)+'\n')
print({v:[r['patched']==r['after_restore_phase'] for r in checks.values()] for v,checks in result.items()})
