"""Fetch public, pinned inputs into a separate directory and verify each file."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def matches(data, item):
    if 'sha256' in item:
        return hashlib.sha256(data).hexdigest() == item['sha256']
    header = b'blob ' + str(len(data)).encode() + b'\0'
    return hashlib.sha1(header + data).hexdigest() == item['git_blob']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache', type=Path)
    cache = parser.parse_args().cache
    inputs = json.loads((ROOT / 'evidence/inputs.json').read_text())
    for item in inputs:
        path = cache / item['local']
        if path.exists() and matches(path.read_bytes(), item):
            continue
        with urllib.request.urlopen(item['url'], timeout=90) as response:
            data = response.read()
        if not matches(data, item):
            raise ValueError(f"Input fingerprint mismatch for {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f'{len(inputs)} verified inputs in {cache}')

if __name__ == '__main__':
    main()
