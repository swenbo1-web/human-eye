"""Relay the actual Codex MCP stream to the held Owner without rewriting calls."""

from pathlib import Path
from runpy import run_path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host import OLD, RUN, assemble, require


if __name__ == '__main__':
    endpoint = Path(sys.argv[sys.argv.index('--endpoint')+1]).resolve(strict=True)
    folder = endpoint.parent
    root = folder.parents[1]
    audit = Path(sys.argv[sys.argv.index('--audit')+1]).resolve()
    require(endpoint == root/'slots'/folder.name/'ENDPOINT.json' and audit.is_relative_to(folder)
            and (root == RUN or root.is_relative_to(RUN/'preflight')), 'current_owned_thin_endpoint_and_archive_required')
    common, _, _ = assemble(root, folder.name)
    common.load_retained('bridge', OLD/'native/bridge.py')
    run_path(str(common.PRIOR/'thin_stdio.py'), run_name='__main__')
