"""Two small local controls, isolated from the official working trees."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

raw = Path(sys.argv[1]).resolve()
out = Path(__file__).resolve().parents[1] / 'evidence'
versions = {v:list(map(json.loads,(raw/f'v{v}.jsonl').read_text().splitlines())) for v in ('10','11')}
def case(v,repo,n):
    return next(r for r in versions[v] if r['repo']==repo and r['number']==n)

def run(args, cwd, **kw):
    return subprocess.run(args,cwd=cwd,timeout=90,capture_output=True,text=True,**kw)

def probetb():
    return """module probe;
logic [31:0] i, o; logic compressed, illegal;
ibex_compressed_decoder dut(.instr_i(i), .instr_o(o), .is_compressed_o(compressed), .illegal_instr_o(illegal));
initial begin
for (int k=0; k<65536; k=k+1) begin
  i=k; #1; $display("%04h %b %b %08h",i[15:0],compressed,illegal,o);
end
$finish;
end
endmodule"""

report={'simulator':run(['iverilog','-V'],raw).stdout.splitlines()[0],
        'method':'Native Icarus; standard hidden script changes only /home/ibex to a disposable checkout. All inputs have upper halfword zero.','ibex54':{},'macro12505':{}}
vectors={}
with tempfile.TemporaryDirectory() as tmp:
    for variant in ('base','reference','gpt5.6-sol','deepseek_v3.2','opus4.6','sonnet4.6','gpt5.4','kimi_k2.5','qwen3.6plus'):
        w=Path(tmp)/variant
        shutil.copytree(raw/'ibex54',w)
        if variant!='base':
            patch=case('11','ibex',54)['fix_patch'] if variant=='reference' else (raw/'pieces'/f'ibex-54-{variant}'/'model_patch.diff').read_text()
            run(['git','apply','--whitespace=nowarn','-'],w,input=patch,check=True)
        verdict={}
        for version in versions:
            script=case(version,'ibex',54)['tb_script'].replace('/home/ibex',str(w))
            trial=run(['bash','-c',script],w)
            m=re.search(r'TEST: compressed_hint_decoder \.\.\. (PASS|FAIL)',trial.stdout)
            assert m and ((trial.returncode==0)==(m[1]=='PASS')), trial.stdout[-500:]
            verdict[version]=m[1]
        (w/'probe.sv').write_text(probetb())
        run(['iverilog','-g2012','-s','probe','-o','probe.out','rtl/ibex_defines.sv','rtl/ibex_compressed_decoder.sv','probe.sv'],w,check=True)
        lines=run(['vvp','probe.out'],w,check=True).stdout.splitlines()
        vectors[variant]=[line.split()[1:] for line in lines if re.match('^[0-9a-f]{4} ',line)]
        assert len(vectors[variant])==65536
        report['ibex54'][variant]={'official_script':verdict}
    for variant,values in vectors.items():
        delta=[i for i,(v,g) in enumerate(zip(values,vectors['reference'])) if v!=g]
        report['ibex54'][variant].update(full_output_diff_count=len(delta),
              illegal_flag_diff_count=sum(v[1]!=g[1] for v,g in zip(values,vectors['reference'])),
              first_40_diff=[f'{i:04x}' for i in delta[:40]], value_at_0002=values[2], value_at_6101=values[0x6101])
    for v in versions:
        line=next(s for s in case(v,'opentitan',12505)['tb_script'].splitlines() if s.startswith('`define ASSERT('))
        for n,args in [('two','A,p'),('three','A,p,clk'),('four','A,p,clk,rst')]:
            w=Path(tmp)
            (w/'macro.sv').write_text(line+'\nmodule m; wire p, clk, rst;\n`ASSERT('+args+')\nendmodule\n')
            test=run(['iverilog','-g2012','-s','m','-o','macro.out','macro.sv'],w)
            report['macro12505'][v+'_'+n]={'rc':test.returncode,'stderr':test.stderr.strip().replace(str(w),'[tmp]')}
(out/'replay.json').write_text(json.dumps(report,indent=2)+'\n')
print({k:(v['official_script'],v['full_output_diff_count']) for k,v in report['ibex54'].items()})
print(report['macro12505'])
