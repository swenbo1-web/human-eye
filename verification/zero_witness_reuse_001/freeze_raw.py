"""Seal original experiment outputs before independent read-only review."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (OUT/'RAW_FREEZE.json').exists()
files=[]
for directory in ('offline_01','qa_baseline','qa_candidate','qa_invocation_baseline','qa_invocation_candidate'):
    for p in sorted((OUT/directory).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
            files.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
for p in OUT.glob('OFFLINE_*'):
    if p.is_file():files.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
value=dict(sealed_utc=datetime.now(timezone.utc).isoformat(),file_count=len(files),files=files,
    original_outputs_preserved=True,new_sessions=2,public_observations=18,physical_RPC=28,model_consumers=0)
(OUT/'RAW_FREEZE.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
before=json.loads((OUT/'PROTECTED_BEFORE.json').read_bytes())
for row in before['files']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
(OUT/'PROTECTED_AFTER.json').write_text(json.dumps(dict(files=before['files'],all_unchanged=True),indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(raw_files=len(files),protected_files=len(before['files']))))
