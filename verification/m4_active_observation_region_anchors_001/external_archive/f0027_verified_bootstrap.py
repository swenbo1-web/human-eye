"""Bind installed product bytes with the existing controlled source loader."""

import hashlib
from pathlib import Path
import sys
import types


def bootstrap(binding):
    root = Path(binding['install_root']).resolve()
    manifest = binding['source_manifest']
    relative = 'human_eye_plugin/verified_source_loader.py'
    expected = {row['path']: row['sha256'] for row in manifest}
    path = root / relative
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected[relative]:
        raise ValueError('installed_verified_loader_pin_changed')
    name = '_human_eye_core_verified_source_bootstrap'
    helper = types.ModuleType(name)
    helper.__file__ = str(path)
    sys.modules[name] = helper
    exec(compile(raw, str(path), 'exec', dont_inherit=True), helper.__dict__)
    return helper.install(root, manifest, bootstrap_module=helper)
