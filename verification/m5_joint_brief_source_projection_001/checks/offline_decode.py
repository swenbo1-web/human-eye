"""Reconstruct the original whole-object task from its versioned public source tables."""

from copy import deepcopy


VERSION = 'active-observation-region-task-result-v1'
SOURCE_COLUMNS = ['object_index', 'geometry_id', 'source_triangle_count',
                  'source_triangle_index_ranges', 'ordered_geometry_sha256']
PARENT_COLUMNS = ['object_index', 'host_id', 'instance_id', 'object_name']
INHERITED = ('source', 'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope')


def require(condition, label):
    if not condition:
        raise ValueError(label)


def decode_task(body):
    """Return the full v3 task. Missing, ambiguous or noncanonical rows are rejected."""
    task = body['task_result']
    binding, parent, objects = task['binding'], body['binding'], body['objects']
    require(body['schema'] == 'active-observation-region-task-brief-v2'
            and task['schema_version'] == VERSION and objects['columns'] == PARENT_COLUMNS
            and set(binding) == {'capture_scope', 'measurement_scope', 'selection_key', 'scene_fingerprint',
                                'object_indices', 'sources'}
            and binding['capture_scope'] == 'observation_task_objects'
            and binding['measurement_scope'] == 'whole_objects', 'unsupported_compact_task_source')
    parent_rows = [dict(zip(PARENT_COLUMNS, row, strict=True)) for row in objects['rows']]
    require(len({row['host_id'] for row in parent_rows}) == len(parent_rows)
            and all(type(row['object_index']) is int and row['object_index'] == i
                    for i, row in enumerate(parent_rows)), 'ambiguous_parent_object_index')
    order = binding['object_indices']
    require(len(order) == 2 and all(type(index) is int and 0 <= index < len(parent_rows) for index in order)
            and order[0] != order[1], 'invalid_measurement_object_order')
    table = binding['sources']
    require(table['columns'] == SOURCE_COLUMNS, 'incompatible_measurement_source_columns')
    rows = [dict(zip(SOURCE_COLUMNS, row, strict=True)) for row in table['rows']]
    source_indices = [row['object_index'] for row in rows]
    require(len(source_indices) == 2 and all(type(index) is int for index in source_indices)
            and set(source_indices) == set(order), 'incompatible_measurement_source_roster')
    source_rows = []
    for row in rows:
        index = row['object_index']
        obj = parent_rows[index]
        count = row['source_triangle_count']
        require(type(count) is int and count > 0 and row['source_triangle_index_ranges'] == [[0, count - 1]],
                'incomplete_measurement_source_range')
        source_rows.append(dict(object_id=obj['host_id'], instance_id=obj['instance_id'],
                                observation_object_index=index,
                                **{name: deepcopy(row[name]) for name in SOURCE_COLUMNS[1:]}))
    state = deepcopy(parent['capture_state'])
    selection_key = binding['selection_key']
    state['selection_key'] = selection_key
    original = dict(schema='active-observation-task-source-v1',
                    measurement_scope=binding['measurement_scope'], capture_scope=binding['capture_scope'],
                    capture_state=state, parent_binding_sha256=parent['binding_sha256'],
                    parent_source_binding_sha256=parent['source_binding_sha256'],
                    parent_capture_scope=parent['capture_scope'], objects=source_rows)
    restored = deepcopy(task)
    restored['schema_version'] = 'task-query-v3'
    restored['binding'] = dict(
        capture_scope=binding['capture_scope'], scene_fingerprint=binding['scene_fingerprint'],
        scene_revision='observation-task:' + selection_key, candidate_count=len(parent_rows),
        selected_count=len(order), observation_source=original,
        objects=[{'name': parent_rows[i]['object_name'], 'object_id': parent_rows[i]['host_id']} for i in order],
        **{key: deepcopy(parent[key]) for key in INHERITED})
    return restored
