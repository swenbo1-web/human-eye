"""Bind this diagnostic batch; never normalize existing raw records."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
files={str(p.relative_to(HERE)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
       for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='SEAL.json'}
value={'task':'SCALE-DIAG-001','parent_commit':'ecdda96aa2f70a098716a0f3b9e345f00a0d0f46','file_count':len(files),
       'raw_bytes':sum((HERE/n).stat().st_size for n in files),'scope':'all new batch sources, fixtures, preflights, formal raw measurements, independent oracle/quality, ledgers, report and cleanup; SEAL excludes itself',
       'product_sources_changed':False,'files':files}
target=HERE/'SEAL.json';assert not target.exists(),'seal_already_exists'
target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'file_count':len(files),'bytes':value['raw_bytes'],'seal_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
