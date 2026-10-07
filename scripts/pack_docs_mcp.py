#!/usr/bin/env python3
"""Build a deterministic MCPB ZIP of the read-only documentation server."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();source=ROOT/'integrations/docs-mcp'
    files=[source/name for name in ('manifest.json','server.mjs','LICENSE','README.md')]
    index=json.loads((source/'docs/index.json').read_text())
    names={'index.json',*(entry['file'] for entry in index)}
    if any(Path(name).name!=name or not name.endswith(('.md','.json')) for name in names):
        p.error('Unsafe bundled documentation filename')
    files+=[source/'docs'/name for name in sorted(names)]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for file in files:
            entry=zipfile.ZipInfo(file.relative_to(source).as_posix(),date_time=(2026,1,1,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED
            entry.external_attr=0o100644<<16
            archive.writestr(entry,file.read_bytes())
    print(json.dumps({'file':str(a.output),'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}))
if __name__=='__main__':main()
