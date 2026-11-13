"""Pure proposed stop_reason condition for a future separately frozen batch."""


def shared_success_binding_fault(reason, response, item):
    """Identify a binding fault between independently explicit success records.

    This does not inspect answer quality or change ordinary tool-error policy.
    No formal driver imports this recommendation in the current offline cycle.
    """
    if reason not in ('CLI_result_differs_from_owner', 'CLI_request_differs_from_owner'):
        return False
    if type(response) is not dict or 'error' in response or type(item) is not dict:
        return False
    owner = response.get('result')
    actual = item.get('result')
    return (type(owner) is dict and owner.get('isError') is False
            and type(owner.get('content')) is list
            and type(actual) is dict and type(actual.get('content')) is list
            and item.get('status') == 'completed' and 'error' in item and item['error'] is None)
