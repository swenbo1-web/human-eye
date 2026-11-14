"""Read remaining telemetry without invoking any product code."""
from pathlib import Path
import hashlib,json
p=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_observation_region_anchors_001/external_archive/f0028_audit.jsonl')
raw=p.read_bytes()
traces=[r['trace'] for r in map(json.loads,raw.splitlines()) if r['event']=='request_trace']
rows=[{'request':t['annotations']['mcp_request_id'],'duration_ns':t['duration_ns'],'pid':t['pid'],'peak_rss':t['peak_rss'],'model_usage_available':[u['usage_available'] for u in t['usage']],'telemetry_issues':t['telemetry_issues'],'native_images':t['annotations']['mcp_native_image_block_count'],'outcome':t['outcome'],'spans':t['spans']} for t in traces]
checks={'three_traces':len(rows)==3,'correct_order':[r['request'] for r in rows]==['joined_cold','joined_hot','cached_full'],'server_pid':all(r['pid']==22452 for r in rows),'complete':all(r['outcome']=='complete' for r in rows),'lifetime_peak_scope':all(r['peak_rss']['scope']=='process_lifetime_peak' for r in rows),'reported_peak':max(r['peak_rss']['bytes'] for r in rows)==93618176,'usage_unavailable':all(r['model_usage_available']==[False] for r in rows),'image_counts':all(r['native_images']==3 for r in rows),'telemetry_issues_empty':all(not r['telemetry_issues'] for r in rows)}
result={'passed':all(checks.values()),'checks':checks,'input':str(p),'input_sha256':hashlib.sha256(raw).hexdigest(),'rows':rows,'scope':'Saved source telemetry; no new execution. Peak is whole server process lifetime, not localization delta.'}
Path(__file__).with_name('TRACE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':result['passed'],'checks':checks,'peak_working_set_bytes':max(r['peak_rss']['bytes'] for r in rows)}))
