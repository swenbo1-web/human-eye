"""Use the retained Owner with one isolated consumer-side request constraint."""

from copy import deepcopy
import time

from common import ORIGINAL, load_retained


original = load_retained('_region_task_profile_original_owner', ORIGINAL / 'harness/bridge.py')
DISCOVERY, TOOL_LIMIT, MAX_FRAME, PRODUCT_TOOL = (
    original.DISCOVERY, original.TOOL_LIMIT, original.MAX_FRAME, original.PRODUCT_TOOL)
TOOLS, TOOL_NAMES = original.TOOLS, original.TOOL_NAMES
encoded, error_result, remaining, save = original.encoded, original.error_result, original.remaining, original.save
SOURCE_REGION, load = original.SOURCE_REGION, original.load

REGION_TASK_RULE = {
    'if': {'required': ['query'], 'properties': {'query': {
        'type': 'object', 'required': ['mode', 'region_task'],
        'properties': {'mode': {'const': 'active_observation'}}}}},
    'then': {'properties': {'response_detail': {'const': 'brief'}}},
}
DETAIL_ERROR = 'response_detail must be brief or omitted for active_observation with region_task in this client profile'


class Owner(original.Owner):
    def __init__(self, runtime, config, budget=None):
        before = time.perf_counter_ns()
        super().__init__(runtime, config, budget=budget)
        self.base_startup_ns = time.perf_counter_ns() - before
        self.profile_projection_ns = self.profile_publish_ns = 0
        if self.label == 'QB':
            before = time.perf_counter_ns()
            observe = next(row for row in self.tools if row['name'] == PRODUCT_TOOL)
            observe['inputSchema']['allOf'].append(deepcopy(REGION_TASK_RULE))
            self.profile_projection_ns = time.perf_counter_ns() - before
            before = time.perf_counter_ns()
            save(self.output / 'TOOLS_SCHEMA.json', self.tools)
            self.profile_publish_ns = time.perf_counter_ns() - before

    def dispatch(self, name, arguments, row, folder):
        if self.label == 'QB' and name == PRODUCT_TOOL:
            started = time.perf_counter_ns()
            query = arguments.get('query')
            restricted = (type(query) is dict and query.get('mode') == 'active_observation'
                          and 'region_task' in query)
            accepted = not restricted or 'response_detail' not in arguments or arguments['response_detail'] == 'brief'
            row['client_profile'] = {'constrained':restricted, 'accepted':accepted,
                                     'check_ns':time.perf_counter_ns()-started}
            if not accepted:
                raise ValueError(DETAIL_ERROR)
        return super().dispatch(name, arguments, row, folder)
