import json
from pathlib import Path
import sys
import sysconfig

from human_eye_plugin import runtime_identity
import numpy
import PIL

output = Path(__file__).resolve().parents[1]
purelib = Path(sysconfig.get_path('purelib')).resolve()
identity = runtime_identity.runtime_identity()
assert identity['source_kind'] == 'installed_distribution'
assert identity['source_sha256'] == 'b0b4e1d3fa96a0b9c9676863fc7565215f82557a2936f247a5a4abd5b911103a'
assert len(identity['source_files']) == 130
assert runtime_identity.check_source_drift()['compatible']
for module in (runtime_identity, numpy, PIL):
    assert Path(module.__file__).resolve().is_relative_to(purelib)
with (output / 'INSTALLED_IDENTITY.json').open('x', encoding='utf8') as stream:
    json.dump(dict(identity=identity, executable=sys.executable, purelib=str(purelib),
                   python=sys.version, numpy=numpy.__version__, pillow=PIL.__version__), stream, indent=2)
