"""Local CLI fixture emitting the successful and failed shapes in real records.

The original process fixture supplies framing, explicit resume and workspace
checks. This wrapper changes its completed-tool event before stdout emission.
It never imports or contacts a provider.
"""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
source = ROOT / 'verification/m4_surface_scan_continuity_001_fix1/consumer/fake_cli.py'
spec = importlib.util.spec_from_file_location('_interface_fix_fixture_cli', source)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
original_emit = legacy.emit
SAME_REPRESENTATION_ERRORS = False


def emit(event):
    item = event.get('item', {})
    if event.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call':
        owner_result = item['result']
        assert set(owner_result) == {'content', 'isError'}
        assert type(owner_result['isError']) is bool
        result = (owner_result if owner_result['isError'] and SAME_REPRESENTATION_ERRORS
                  else {'content': owner_result['content'], 'structured_content': None})
        item = {**item, 'result': result,
                'status': 'failed' if owner_result['isError'] else 'completed', 'error': None}
        event = {**event, 'item': item}
    original_emit(event)


legacy.emit = emit


if __name__ == '__main__':
    raise SystemExit(legacy.main())
