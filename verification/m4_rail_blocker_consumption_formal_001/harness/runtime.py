"""Bind the exact rail runtime to the six new slots and the original schema."""

import sys

from common import OLD, load


sys.path.append(str(OLD))
_retained = load('_rail_original_runtime', OLD / 'harness/runtime.py')
Runtime, _previous = _retained.Runtime, _retained._previous
# The shared runtime uses NS only here to check the installed tool schema.
Runtime._start_public_mcp.__globals__['NS'] = OLD
