"""Use the recovered synchronous product archive association unchanged."""

from common import GLOBAL, load_retained


previous = load_retained('_m5_projection_runtime_source', GLOBAL / 'harness/runtime.py')
Runtime = previous.Runtime
