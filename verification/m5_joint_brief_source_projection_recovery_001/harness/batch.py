"""Keep the previously measured joint outer message and transport byte-for-byte."""

from common import GLOBAL, load_retained


previous = load_retained('_m5_projection_recovery_outer_source', GLOBAL / 'harness/batch.py')
MARKERS, outer_message, owner_for, execute = (
    previous.MARKERS, previous.outer_message, previous.owner_for, previous.execute,
)
