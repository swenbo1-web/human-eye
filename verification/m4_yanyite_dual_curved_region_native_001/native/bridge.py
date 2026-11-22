"""Expose the same retained ordinary viewport and compute tools on both arms."""

from common import V, load_retained


_retained = load_retained(
    '_yanyite_retained_native_bridge',
    V / 'perf050_dense_micro_surface_holdout_recovery_001/harness/bridge.py',
)
DISCOVERY, TOOL_LIMIT, MAX_FRAME = _retained.DISCOVERY, _retained.TOOL_LIMIT, _retained.MAX_FRAME
PRODUCT_TOOL, SOURCE_REGION, VIEWS = _retained.PRODUCT_TOOL, _retained.SOURCE_REGION, _retained.VIEWS
TOOLS, TOOL_NAMES = _retained.TOOLS, _retained.TOOL_NAMES
load = _retained.load
encoded, save, remaining = _retained.encoded, _retained.save, _retained.remaining
error_result = _retained.error_result


class Owner(_retained.Owner):
    def handle(self, request, attempt=None):
        reply = super().handle(request, attempt)
        if request.get('method') == 'initialize' and reply is not None:
            reply['result']['serverInfo']['name'] = 'm4-yanyite-dual-curved-region'
        return reply
