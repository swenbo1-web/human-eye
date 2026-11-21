"""Retain the owned startup, shutdown and original-file closure checks."""

from common import FORMAL, load_retained


previous = load_retained('_task_entry_dense_closure', FORMAL / 'harness/closure.py')
ready_closure, startup_closure = previous.ready_closure, previous.startup_closure
