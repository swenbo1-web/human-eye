"""Reuse the original process-handle, asset, and genuine EOF checks."""

from common import FORMAL, load_retained


previous = load_retained('_yanyite_closure',FORMAL/'harness/closure.py')
ready_closure, startup_closure = previous.ready_closure, previous.startup_closure
