"""Create the small public tables from the pinned datasets and v1.1 leaderboard."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'evidence'
REPOS = {'opentitan':'OpenTitan','ibex':'Ibex','cva6':'CVA6','caliptra-rtl':'Caliptra',
         'XiangShan':'XiangShan','rocket-chip':'Rocket Chip'}
BOARD_KEYS = {'Caliptra':'caliptra','Rocket Chip':'rocketchip'}

def read_tasks(path):
    tasks = {}
    for line in path.read_text().splitlines():
        record = json.loads(line)
        key = record['org'], record['repo'], record['number']
        if key in tasks:
            raise ValueError(f'Duplicate task {key}')
        tasks[key] = record
    return tasks

def save(name, records):
    with (OUT / name).open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache', type=Path)
    cache = parser.parse_args().cache
    old, new = (read_tasks(cache / name) for name in ('v10.jsonl','v11.jsonl'))
    assert old.keys() == new.keys() and len(new) == 417
    revised, labels, checks = Counter(), Counter(), Counter()
    counts, file_changes = Counter(), Counter()
    for key, entry in new.items():
        fields = sorted(k for k in old[key].keys() | entry.keys()
                        if k not in old[key] or k not in entry or old[key][k]!=entry[k])
        revised[' + '.join(fields) or 'unchanged'] += 1
        counts[REPOS[entry['repo']]] += 1
        for field in fields:
            file_changes[field] += 1
        labels[entry['level2']] += 1
        checks[len(entry['f2p_tests'])] += 1
    save('revisions.csv', [dict(fields=k,tasks=n) for k,n in sorted(revised.items())])
    save('task_labels.csv', [dict(label=k,tasks=n) for k,n in labels.most_common()])
    models = json.loads((cache / 'code/website/scores-v1.1.json').read_text())['models']
    table = []
    for m in models:
        assert m['overall'] == sum(m['resolved'].values())
        table.append(dict(model=m['name'],harness=m['agent'],passed=m['overall'],tasks=len(new),
                          usd=m['costs'],**{p:m['resolved'][BOARD_KEYS.get(p,p.lower())] for p in counts}))
    save('systems.csv', table)
    by_model = {r['model']:r for r in table}
    save('projects.csv', [dict(project=p,tasks=n,claude_unsolved=n-by_model['Claude Opus 5.5'][p],
                               deepseek_unsolved=n-by_model['DeepSeek V4.1 Flash 1017'][p])
                          for p,n in counts.most_common()])
    print('Changed fields:',dict(file_changes),'F2P checks per task:',dict(checks))

if __name__ == '__main__':
    main()
