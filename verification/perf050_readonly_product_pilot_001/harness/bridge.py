"""Expose the same ordinary tools and one real read-only installed P tool."""

from common import FORMAL, SLOTS, load, load_retained


bridge = load_retained('_perf050_dense_common_bridge', FORMAL / 'bridge.py')
if bridge.SLOTS is not SLOTS:
    raise ValueError('bridge_loaded_wrong_experiment')
DISCOVERY, TOOL_LIMIT, MAX_FRAME, PRODUCT_TOOL = (
    bridge.DISCOVERY, bridge.TOOL_LIMIT, bridge.MAX_FRAME, bridge.PRODUCT_TOOL,
)
TOOLS, TOOL_NAMES, VIEWS = bridge.TOOLS, bridge.TOOL_NAMES, bridge.VIEWS
SOURCE_REGION = bridge.SOURCE_REGION
encoded, save, remaining = bridge.encoded, bridge.save, bridge.remaining


class Owner(bridge.Owner):
    def handle(self, request, attempt=None):
        reply = super().handle(request, attempt)
        if request.get('method') == 'initialize' and reply is not None:
            reply['result']['serverInfo']['name'] = 'perf050-readonly-product-pilot'
        return reply
