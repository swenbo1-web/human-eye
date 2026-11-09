"""Run the affected host/bridge regressions and save their actual result."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
package = types.ModuleType('human_eye_plugin')
package.__path__ = [str(ROOT / 'human_eye_plugin')]
sys.modules['human_eye_plugin'] = package
output = Path(sys.argv[1]).resolve()
output.mkdir(parents=True, exist_ok=True)
patterns = ['test_blender_host_contracts.py', 'test_blender_process.py',
            'test_blender_worker_protocol.py', 'test_blender_mcp_host.py',
            'test_blender_process_residency.py', 'test_readonly_dependency_loader.py']
sources = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in (ROOT / 'human_eye_plugin').glob('*.py')}
suite = unittest.TestSuite()
for pattern in patterns:
    suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / 'verification'), pattern=pattern))
suite.addTests(unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_residency_contract.py'))
if '--world-reuse' in sys.argv[2:]:
    suite.addTests(unittest.defaultTestLoader.discover(str(Path(__file__).parent.with_name('arch_resident_opt_001')), pattern='test_*.py'))
    patterns.append('arch_resident_opt_001/test_*.py')
stream = io.StringIO()
start = time.perf_counter_ns()
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
unchanged = sources == {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (ROOT / 'human_eye_plugin').glob('*.py')}
record = {'passed': result.wasSuccessful() and unchanged, 'tests': result.testsRun,
          'errors': len(result.errors), 'failures': len(result.failures),
          'duration_ms': (time.perf_counter_ns() - start) / 1e6,
          'product_sources_unchanged': unchanged, 'source_files': sources,
          'patterns': patterns + ['arch_resident_001/test_residency_contract.py']}
(output / 'unit.log').write_text(stream.getvalue(), encoding='utf8')
(output / 'unit.json').write_text(json.dumps(record, indent=2), encoding='utf8')
print(json.dumps({k: v for k, v in record.items() if k not in ('source_files', 'patterns')}))
sys.exit(0 if record['passed'] else 1)
