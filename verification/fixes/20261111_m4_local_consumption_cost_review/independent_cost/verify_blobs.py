from pathlib import Path
import hashlib, json, subprocess
OUT=Path(__file__).parent
WT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
COMMIT='06d1b4b4cadd880884a0a3c0927a3095ea761f30'
x=json.loads((OUT/'COST_REVIEW.json').read_bytes())
paths={Path(k).relative_to(WT).as_posix():v for k,v in x['source_sha256'].items() if Path(k).is_relative_to(WT)}
raw=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(COMMIT+':'+p+'\n' for p in paths).encode(),check=True,capture_output=True).stdout
pos=0
for name,digest in paths.items():
    end=raw.index(b'\n',pos);header=raw[pos:end].split();assert header[1]==b'blob'
    n=int(header[2]);pos=end+1;value=raw[pos:pos+n];pos+=n;assert raw[pos:pos+1]==b'\n';pos+=1
    assert hashlib.sha256(value).hexdigest()==digest and value==(WT/name).read_bytes(),name
assert pos==len(raw)
result={'commit':COMMIT,'independently_read_source_files':len(x['source_sha256']),'implementation_source_blobs_verified':len(paths),'all_equal_current_disk':True,'root_quality_seal_sha256':hashlib.sha256(Path('D:/hefe/verification/fixes/20261111_m4_local_consumption_quality_review/QUALITY_SEAL.json').read_bytes()).hexdigest(),'cost_review_sha256':hashlib.sha256((OUT/'COST_REVIEW.json').read_bytes()).hexdigest()}
(OUT/'SOURCE_BLOB_CHECK.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps(result))
