"""Run the unchanged consumer loop, tool bridge, and common prompt."""

from common import OLD, load


_retained = load('_rail_original_consumer', OLD / 'harness/consumer.py')
# Both retained functions read their input or bridge paths through NS.
_retained.NS = OLD
consumer_adapter = _retained.consumer_adapter
consume_slot = _retained.consume_slot
