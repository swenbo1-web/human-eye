"""Run the previously sealed focused unit suite on the isolated candidate."""

import importlib.util
from pathlib import Path
from runpy import run_path
import sys
import unittest


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUILD = run_path(str(HERE/'build.py'))
BASE = run_path(str(HERE.parent/'m2_source_region_shared_normalization_live_001/experiment.py'))
read, pin, require, write = (BASE[key] for key in ('read','pin','require','write'))
PRIOR = Path('D:/he_m4_source_region_curved_view_sample_001/preflight/UNIT_WITH_OLD_FIXTURE.json')


def main():
    p = read(PRIOR)
    binding = read(HERE/'install/PRODUCT_RUN_BINDING.json')
    require(sys.flags.isolated and sys.dont_write_bytecode and p['passed'] and p['tested'] == 60
            and binding['preparation_git'] == BUILD['CANDIDATE'], 'fixed_unit_suite_and_install_required')
    shared = REPO/'verification/m5_harness_recovery_001/SHARED_DEPENDENCY.json'
    sys.path[:0] = [binding['install_root'], binding['dependency_root'], read(shared)['dependency_root'], str(REPO)]
    suite = unittest.TestSuite()
    for row in p['source_pins']:
        path = Path(row['path'])
        require(pin(path) == row, 'retained_unit_source_changed/'+path.name)
        if path.suffix == '.py':
            spec = importlib.util.spec_from_file_location(path.stem,path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[path.stem] = module
            spec.loader.exec_module(module)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    import human_eye_plugin.live_spatial_mcp as installed

    require(Path(installed.__file__).is_relative_to(Path(binding['install_root'])), 'candidate_unit_import_changed')
    write(BUILD['ROOT']/'preflight/UNIT.json', {'passed':result.wasSuccessful() and result.testsRun == 60,
          'tested':result.testsRun, 'failures':[(str(test),failure) for test,failure in result.failures],
          'errors':[(str(test),error) for test,error in result.errors], 'modules':p['modules'],
          'product_git':binding['preparation_git'], 'source_sha256':binding['source_sha256'],
          'source_pins':[*p['source_pins'],pin(PRIOR),pin(shared),pin(Path(sys.executable)),
                         pin(REPO/'verification/test_blender_host_contracts.py')]})
    return result.wasSuccessful() and result.testsRun == 60


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
