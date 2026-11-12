"""Re-execute the author's frozen offline suite in a root-owned isolated output.

This independently executes existing tests; it does not call Blender or add
independent test cases. The separately authored correctness audit does that.
"""
from pathlib import Path
import hashlib
import json
import sys
import types

HERE = Path(__file__).resolve().parent
SOURCE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
RUNNER = SOURCE / 'verification/m2_tight_directory_001/correctness/run_unit.py'
EXPECTED = '6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb'

raw = RUNNER.read_bytes()
module = types.ModuleType('_root_directory_offline_runner')
module.__file__ = str(RUNNER)
exec(compile(raw, str(RUNNER), 'exec', dont_inherit=True), module.__dict__)
module.HERE = HERE
module.ROOT = SOURCE
sys.argv = [str(RUNNER), '--output', 'root_offline', '--expected-source-sha256', EXPECTED]
exit_code = module.main()
record = {
    'source_runner': str(RUNNER),
    'source_runner_sha256': hashlib.sha256(raw).hexdigest(),
    'root_driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'candidate_source_sha256': EXPECTED,
    'exit_code': exit_code,
    'scope': 'Root independently re-executed frozen author offline cases; no Blender/model/process/socket calls by the suite',
    'full_json_schema_engine': 'not_run: jsonschema unavailable in the existing dependency Python; no dependency installation',
}
(HERE / 'ROOT_OFFLINE_EXECUTION.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
raise SystemExit(exit_code)
