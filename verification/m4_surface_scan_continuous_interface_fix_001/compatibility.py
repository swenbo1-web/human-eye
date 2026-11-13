"""Match the two recorded successful owner/CLI result representations."""

import json


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def successful_result_matches(response, item):
    """Accept explicit success with exact business data and a known envelope."""
    if type(response) is not dict or 'error' in response or type(item) is not dict:
        return False
    owner = response.get('result')
    actual = item.get('result')
    if type(owner) is not dict or type(actual) is not dict:
        return False
    if set(owner) != {'content', 'isError'} or owner['isError'] is not False:
        return False
    if item.get('status') != 'completed' or 'error' not in item or item['error'] is not None:
        return False
    if type(owner['content']) is not list or type(actual.get('content')) is not list:
        return False
    if set(actual) == {'content', 'isError'}:
        if actual['isError'] is not False:
            return False
    elif set(actual) == {'content', 'structured_content'}:
        if actual['structured_content'] is not None:
            return False
    else:
        return False
    return encoded(owner['content']) == encoded(actual['content'])
