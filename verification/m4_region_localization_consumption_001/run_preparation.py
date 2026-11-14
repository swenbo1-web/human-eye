"""Run one explicit N or P fake consumer through the actual frozen route."""

import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', required=True, choices=('N', 'P'))
    arguments = parser.parse_args()
    here = Path(__file__).resolve().parent
    specification = importlib.util.spec_from_file_location('_localization_launcher', here / 'launcher.py')
    launcher = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(launcher)
    result = launcher.run_local(launcher.read(here / 'PLAN.json'), arguments.group)
    print(json.dumps({'group': result['group'], 'attempt': result['attempt'], 'passed': result['passed'],
                      'new_model_sessions': 0, 'render_attempts': result['route'].get('new_renders')}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
