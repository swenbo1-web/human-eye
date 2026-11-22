"""Apply the established independent Blender and MCP close verification."""

from common import FORMAL, load_retained


previous = load_retained('_perf050_dense_closure', FORMAL / 'harness/closure.py')
ready_closure, startup_closure = previous.ready_closure, previous.startup_closure
