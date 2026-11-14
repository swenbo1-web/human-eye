"""Direct-base actor bootstrap using the accepted isolated dependency bytes."""

import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys


def main():
    target = Path(sys.argv[1]).resolve()
    arguments = sys.argv[2:]
    config_path = Path(arguments[arguments.index('--config') + 1])
    config = json.loads(config_path.read_bytes())
    runtime = config['runtime_binding']
    for name in ('binding', 'verified_bootstrap'):
        specification = runtime[name]
        if hashlib.sha256(Path(specification['path']).read_bytes()).hexdigest() != specification['sha256']:
            raise ValueError('accepted_actor_runtime_source_changed_' + name)
    binding = json.loads(Path(runtime['binding']['path']).read_bytes())
    sys.path.insert(0, binding['dependency_root'])
    sys.path.insert(0, binding['install_root'])
    specification = importlib.util.spec_from_file_location('_localization_accepted_source_bootstrap', runtime['verified_bootstrap']['path'])
    helper = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(helper)
    guard = helper.bootstrap(binding)
    guard.verify_loaded()
    sys.argv = [str(target), *arguments]
    runpy.run_path(str(target), run_name='__main__',
                   init_globals={'LOCALIZATION_SOURCE_GUARD': guard})


if __name__ == '__main__':
    main()
