"""Control fixture preserving the old identical-error result representation."""

import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location('_interface_same_representation_cli',
                                             Path(__file__).with_name('fake_cli.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.SAME_REPRESENTATION_ERRORS = True


if __name__ == '__main__':
    raise SystemExit(fixture.legacy.main())
