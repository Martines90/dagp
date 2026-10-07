#!/usr/bin/env python3
"""Run and verify a configured reference society, without external services."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'starter/society.json')
    parser.add_argument('--output', type=Path, default=ROOT/'starter/output')
    parser.add_argument('--replay', action='store_true', help='Repeat the run and compare every artifact')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error('Python 3.10 or newer is required')
    try:
        config = json.loads(args.config.read_text())
    except (OSError, ValueError) as error:
        parser.error(f'Cannot read configuration: {error}')
    if not isinstance(config, dict) or set(config) != {'name', 'citizens', 'seeds', 'modes'}:
        parser.error('Config must contain exactly name, citizens, seeds and modes')
    if not isinstance(config['name'], str) or not 1 <= len(config['name']) <= 120:
        parser.error('name must be 1–120 characters')
    if type(config['citizens']) is not int or not 200 <= config['citizens'] <= 10000:
        parser.error('citizens must be an integer between 200 and 10000')
    seeds, modes = config['seeds'], config['modes']
    if (not isinstance(seeds, list) or not 1 <= len(seeds) <= 10
            or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
            or len(set(seeds)) != len(seeds)):
        parser.error('seeds must contain 1–10 distinct unsigned 32-bit integers')
    if (not isinstance(modes, list) or not modes or len(modes) > 2
            or any(type(m) is not str or m not in ('WEIGHTED','FLAT') for m in modes)
            or len(set(modes)) != len(modes)):
        parser.error('modes must contain distinct WEIGHTED and/or FLAT entries')
    output = args.output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('output must be absent or empty; choose a new directory to preserve earlier runs')
    print(f"Starting {config['name']} — reference simulation, no real agents or funds", flush=True)
    subprocess.run([sys.executable, str(ROOT/'chain/simulation/community.py'),
                    '--citizens',str(config['citizens']), '--seeds', *map(str,seeds),
                    '--modes', *modes, '--output',str(output)], check=True, cwd=ROOT)
    verify = [sys.executable,str(ROOT/'chain/simulation/verify.py'),str(output)]
    if args.replay:
        verify.append('--replay')
    subprocess.run(verify, check=True, cwd=ROOT)
    print(f"Verified society report: {output/'REPORT.md'}", flush=True)

if __name__ == '__main__':
    main()
