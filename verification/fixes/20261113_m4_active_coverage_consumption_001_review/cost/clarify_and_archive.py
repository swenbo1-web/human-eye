"""Preserve initial audit; correct only LF interpretation against original wire.
Also independently verify both layers of sealed archive members.
"""
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001')
checks=[];inputs={}
def raw(p):
    p=Path(p);b=p.read_bytes();inputs[str(p)]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());return b
def doc(p):return json.loads(raw(p))
def ck(name,value,detail=None):checks.append(dict(name=name,passed=bool(value),detail=detail))
def enc(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
initial=doc(HERE/'RESULTS.json');failed=initial['failed']
ck('only15_LF_expectations',len(failed)==15 and all(x['name'].endswith('_response_bytes') and x['detail']['actual']+1==x['detail']['expected'] for x in failed))
member_count=0
for slot,row in initial['routes'].items():
    folder=BASE/'r'/slot;route=doc(folder/'RESULT.json');tools=doc(folder/'o/TOOLS.json')
    rx=[(p,raw(p)) for p in (folder/'c/attachments').rglob('RX.bin')]
    for i,tool in enumerate(tools['tools'],1):
        response=doc(folder/'o'/('tool_'+str(i).zfill(2))/'RESPONSE.json')
        matches=[(p,b) for p,b in rx if json.loads(b)==response]
        ck(slot+f'/tool{i}_one_wire_match',len(matches)==1)
        if len(matches)==1:
            p,b=matches[0]
            ck(slot+f'/tool{i}_canonical_plus_LF',b==enc(response)+b'\n')
            ck(slot+f'/tool{i}_actual_wire_count',len(b)==tool['response_bytes'])
    outer=route['originals'];inner=doc(folder/'c/ARCHIVE.json')
    for level,path,origin,digests,expected_sha,expected_bytes in [
        ('outer',Path(outer['path']),folder,outer['members_sha256'],outer['sha256'],outer['bytes']),
        ('consumer',Path(inner['archive']),folder/'c',inner['source_files_sha256'],inner['archive_sha256'],inner['archive_bytes']),
    ]:
        payload=raw(path)
        ck(slot+'/'+level+'_archive_bytes',len(payload)==expected_bytes and hashlib.sha256(payload).hexdigest()==expected_sha)
        with zipfile.ZipFile(path) as z:
            ck(slot+'/'+level+'_member_set',set(z.namelist())==set(digests))
            for name in z.namelist():
                b=z.read(name);current=raw(origin/name);member_count+=1
                ck(slot+'/'+level+'/'+name,b==current and hashlib.sha256(b).hexdigest()==digests[name])
ck('627_members',member_count==627)
out=dict(scope='15 original audit LF assumptions corrected from exact RX.bin; original fail remains. Existing archive members only, no workloads run.',checks=checks,
         passed=sum(c['passed'] for c in checks),failed=[c for c in checks if not c['passed']],archive_members=member_count,original_invalid_LF_expectations=15,inputs=inputs)
(HERE/'WIRE_AND_ARCHIVE.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
accept=dict(initial)
accept.update(verdict='pass_recorded_costs' if not out['failed'] else 'review_failed',
    original_valid_checks=initial['passed'],original_invalid_expectations=15,
    supplemental_checks_passed=out['passed'],supplemental_failures=out['failed'],archive_members=member_count,
    reviewer_correction='Initial helper encoded JSON without the wire LF; actual response_bytes includes LF. All15 corrected against raw RX bytes, no author discrepancy.',
    source_initial_results='RESULTS.json',source_supplement='WIRE_AND_ARCHIVE.json')
# Keep original failed list under an explicit name, never silently erase history.
accept['original_invalid_expectation_records']=accept.pop('failed')
(HERE/'COST_ACCEPTANCE.json').write_text(json.dumps(accept,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:out[k] for k in ('passed','failed','archive_members','original_invalid_LF_expectations')},ensure_ascii=False))
