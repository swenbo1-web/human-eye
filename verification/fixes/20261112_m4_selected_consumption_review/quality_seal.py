import json, hashlib
from pathlib import Path
from datetime import datetime, timezone
R=Path(__file__).resolve().parent
files=[p for d in ['root_quality','independent_quality','quality_inputs'] for p in (R/d).rglob('*') if p.is_file()]
seal={'cycle_id':'M4-SELECTED-GEOMETRY-CONSUMPTION-001','stage':'quality_fixed_before_cost_or_map_read','created_utc':datetime.now(timezone.utc).isoformat(),
 'root_complete_correct':9,'fresh_independent_complete_correct':9,'denominator':9,'disagreements':[],
 'source_commit':'de35ceda1f5e3f5af2c9ec02f0e4646808f417c2',
 'files':[{'path':str(p.relative_to(R)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(files)],
 'review_harness_correction':'First root delivery equality assertion compared CLI envelope to MCP envelope and failed before producing scores. Corrected to compare exact content with successful status; all recorded completed public contents then matched owner contents. This is reviewer harness evidence, not a consumer failure.',
 'blindness_limit':'No perfect double blindness: public tool names/source hashes may reveal routes. Neither root nor fresh scorer read current formal map/cost before this seal. Author raw-cell exposure remains disclosed and is not used as blind grading.'}
with (R/'QUALITY_SEAL.json').open('x',encoding='utf8',newline='\n') as f: json.dump(seal,f,ensure_ascii=False,indent=2);f.write('\n')
print(hashlib.sha256((R/'QUALITY_SEAL.json').read_bytes()).hexdigest())
