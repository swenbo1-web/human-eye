"""Use the retained M5 runtime with the canonical installed MCP contract."""

import ast
from pathlib import Path
from textwrap import dedent

from common import CATALOGUE, GLOBAL, HERE, PRODUCT_SCHEMA, load_retained


previous = load_retained('_m5_projection_recovery_runtime_source', GLOBAL / 'harness/runtime.py')
retained_startup = previous.Runtime._start_public_mcp
STARTUP_SOURCE = Path(retained_startup.__code__.co_filename)
parsed = ast.parse(STARTUP_SOURCE.read_bytes())
owner = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == 'Runtime')
method = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == '_start_public_mcp')
source = dedent('\n'.join(STARTUP_SOURCE.read_text(encoding='utf-8').splitlines()[
    method.lineno - 1:method.end_lineno]))
anchor = "    save(self.folder / 'MCP_IDENTITY.json', identity)"
replacements = {
    "'--phase', 'formal'": "'--phase', self.phase",
    "read(NS / 'inputs/PRODUCT_SCHEMA.json')": 'read(PRODUCT_SCHEMA)',
    anchor: "    if self.product_tools != read(CATALOGUE):\n"
            "        raise ValueError('actual_public_catalogue_changed')\n" + anchor,
}
for before, after in replacements.items():
    if source.count(before) != 1:
        raise ValueError('retained_installed_mcp_startup_anchor_changed/' + before)
    source = source.replace(before, after)
scope = dict(retained_startup.__globals__, HERE=HERE, PRODUCT_SCHEMA=PRODUCT_SCHEMA, CATALOGUE=CATALOGUE)
exec(compile(source, str(STARTUP_SOURCE), 'exec'), scope)


class Runtime(previous.Runtime):
    _start_public_mcp = scope['_start_public_mcp']
