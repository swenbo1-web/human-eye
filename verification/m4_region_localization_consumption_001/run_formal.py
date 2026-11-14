"""Run the single frozen six-slot provider batch after local qualification."""

import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true', required=True)
    parser.add_argument('--preparation-git', required=True)
    arguments = parser.parse_args()
    here = Path(__file__).resolve().parent
    specification = importlib.util.spec_from_file_location('_localization_launcher', here / 'launcher.py')
    launcher = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(launcher)
    result = launcher.run_formal(launcher.read(here / 'PLAN.json'), arguments.preparation_git)
    print(json.dumps({'actual_routes': result['actual_routes'],
                      'states': {name: sum(row['execution_state'] == name for row in result['records'])
                                 for name in ('completed', 'failed', 'not_run')}}))


if __name__ == '__main__':
    main()
