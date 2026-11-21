"""Use the same ordinary read-only bridge surface as the original pilot."""

from common import PILOT, load_retained


previous = load_retained('_m4_active_view_pilot_frame_bridge', PILOT / 'harness/bridge.py')
SOURCE_REGION, load = previous.SOURCE_REGION, previous.load
