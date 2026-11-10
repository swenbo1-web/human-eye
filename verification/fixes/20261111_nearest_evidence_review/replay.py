"""Root replay of the unchanged fixed runner; output directory only relocated."""
from pathlib import Path
import hashlib, json, sys, types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).parent
path = ROOT/'verification/m1_nearest_evidence_001/run_offline.py'
index = json.loads((path.parent/'ARTIFACT_INDEX.json').read_text(encoding='utf-8-sig'))
raw = path.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
role = sys.argv[1]
expected = {'baseline':'0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a',
            'candidate':'7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'}[role]
# Pin the runner to the current committed preparation bytes, not a modified copy.
import subprocess
committed = subprocess.run(['git','-C',str(ROOT),'show',
    '107641ec19919d56aa843c1949261590fc338148:verification/m1_nearest_evidence_001/run_offline.py'],
    check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
assert raw == committed
module = types.ModuleType('_root_nearest_evidence_replay')
module.__file__ = str(path)
sys.modules[module.__name__] = module
exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
assert module.ROOT.resolve()==ROOT.resolve()
module.HERE = HERE
sys.argv = [str(path),'--role',role,'--expected-source-sha256',expected,
            '--output','root_'+role+'_01']
provenance={'role':role,'implementation_commit':'107641ec19919d56aa843c1949261590fc338148',
    'runner_sha256':digest,'runner_matches_commit':True,'root_override':'HERE only, to relocate output; ROOT and all runner/test/product source bytes unchanged',
    'product_sha256':expected,'models':0,'Blender':0}
(HERE/('REPLAY_'+role.upper()+'_PROVENANCE.json')).write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
raise SystemExit(module.main())
