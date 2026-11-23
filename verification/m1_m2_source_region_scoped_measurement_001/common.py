"""One frozen request representation for the controller and closed scorer."""


def query_from_record(record):
    if type(record) is not dict or set(record) != {'query','include_image'} or record['include_image'] is not False:
        raise ValueError('one_frozen_no_image_request_record_required')
    query = record['query']
    if (type(query) is not dict or set(query) != {'mode','region','reference','requested_facts'}
            or query['mode'] != 'source_region' or query['requested_facts'] != ['surface_proximity']
            or type(query['region']) is not dict or set(query['region']) != {'object','world_box_m'}):
        raise ValueError('one_source_region_world_box_query_required')
    return query


def arguments(record,arm):
    result = {'query':query_from_record(record),'include_image':False}
    if arm not in ('A','B'):
        raise ValueError('unregistered_measurement_arm')
    if arm == 'B':
        result['query'] = {**result['query'], 'mode': 'source_region_measurement'}
    else:
        result['response_detail'] = 'brief'
    return result


def order(records):
    if type(records) not in (list,tuple) or len(records) != 2:
        raise ValueError('two_frozen_queries_required')
    first,second = records
    if query_from_record(first) == query_from_record(second):
        raise ValueError('distinct_secondary_region_required')
    return first,first,second
