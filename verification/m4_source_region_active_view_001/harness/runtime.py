"""Use the real pilot runtime with the selected arm's frozen installed identity."""

from common import HERE, ORDER, PILOT, arguments, load_retained


previous = load_retained('_m4_active_view_pilot_runtime', PILOT / 'harness/runtime.py')
if previous.Runtime._start_public_mcp.__globals__['HERE'] != HERE:
    raise ValueError('active_view_installed_child_namespace_changed')


class Runtime(previous.Runtime):
    def __init__(self, folder, label, task_deadline, owned_deadline, business_calls):
        super().__init__(folder, label, task_deadline, owned_deadline)
        self.business_calls = business_calls

    def public_request(self, value):
        if self.label not in ORDER or value != arguments() or len(self.public_requests) >= 2:
            raise ValueError('only_the_fixed_cold_and_hot_original_request_is_admitted')
        return super().public_request(value)
