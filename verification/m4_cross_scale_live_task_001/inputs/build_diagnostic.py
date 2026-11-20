"""Freeze ordinary tool Python for the diagnostic-only no-model demonstration."""

import ast
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sources = (
    (ROOT / 'verification/m4_global_local_qualification_001/oracle/static_oracle.py',
     ('sub', 'dot', 'cross', 'primitive', 'component_analysis')),
    (ROOT / 'verification/m4_cross_scale_discovery_001/oracle/geometry_witness.py',
     ('clip', 'area2', 'prove')),
)
parts = ['from collections import Counter, defaultdict\nfrom fractions import Fraction as F\n'
         'from math import gcd, lcm, sqrt\nimport json']
for path, names in sources:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    parts.extend(ast.unparse(functions[n]) for n in names)
parts.append((HERE / 'diagnostic_native.py').read_text(encoding='utf8'))
code = '\n\n'.join(parts)
compile(code, '<frozen-native-qualification-example>', 'exec')
payload = {'calls': [{'name': 'execute_python', 'arguments': {'code': code}}]}
with (HERE / 'DIAGNOSTIC_N.json').open('x', encoding='utf8', newline='\n') as stream:
    json.dump(payload, stream, indent=2)
    stream.write('\n')
