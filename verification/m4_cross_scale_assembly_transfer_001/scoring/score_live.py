"""Derive the frozen scorer with the observed cross-process enumeration fix."""

import argparse
from hashlib import sha256
import inspect
from pathlib import Path
import runpy


HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'score.py'
SOURCE_SHA = 'c2ee51eaa5068f5c19bd49169b62f6763d05b7099dc2c3a2ad9579af02bacd07'

if sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA:
    raise ValueError('frozen_assembly_scorer_source_has_changed')
legacy = runpy.run_path(str(SOURCE))
namespace = legacy['bound_terminal'].__globals__
code = inspect.getsource(legacy['bound_terminal'])

# The old exporter traversed by name and the fresh worker traverses by its
# current host order. Keep the strict before/after equality within each
# worker. Check each export's offsets and mask in its own addressing domain.
before = """            all(last[field] == previous[field] for field in ('source_face_offsets', 'display_object_mask',
                                                             'display_scope', 'display_read')),
            'archived_assembly_scope_or_ordered_offsets_differ')
    object_fields = ('name', 'mesh_name', 'parent', 'native_matrix_world', 'matrix_world', 'modifiers',
                     'display', 'visible_get', 'evaluated', 'native')
    for old, new in zip(previous['objects'], last['objects'], strict=True):
"""
after = """            all(last[field] == previous[field] for field in ('display_scope', 'display_read')),
            'archived_assembly_display_convention_differs')
    for capture in (previous, last):
        offsets = [0]
        for item in capture['objects']:
            offsets.append(offsets[-1] + len(item['evaluated']['triangles']))
        require(capture['source_face_offsets'] == offsets and
                capture['display_object_mask'] == [item['visible_get'] for item in capture['objects']],
                'capture_source_face_offsets_or_display_order_invalid')
    previous_by_name = {item['name']: item for item in previous['objects']}
    current_by_name = {item['name']: item for item in last['objects']}
    require(len(previous_by_name) == len(current_by_name) == len(last['objects']) and
            previous_by_name.keys() == current_by_name.keys(), 'assembly_unique_name_roster_differs')
    object_fields = ('name', 'mesh_name', 'parent', 'native_matrix_world', 'matrix_world', 'modifiers',
                     'display', 'visible_get', 'evaluated', 'native')
    for name, old in previous_by_name.items():
        new = current_by_name[name]
"""
if code.count(before) != 1:
    raise ValueError('frozen_score_wrong_worker_order_assumption_missing')
exec(compile(code.replace(before, after), str(SOURCE), 'exec'), namespace)

bound_terminal = namespace['bound_terminal']
inspect_frame = namespace['inspect_frame']
evidence = namespace['evidence']
grade = namespace['grade']
read, write = namespace['read'], namespace['write']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('evidence', 'grade'))
    parser.add_argument('--claims', type=Path)
    arguments = parser.parse_args()
    if arguments.action == 'evidence':
        write(HERE / 'FORMAL_EVIDENCE.json', evidence())
    else:
        write(HERE / 'QUALITY.json', grade(read(HERE / 'FORMAL_EVIDENCE.json'),
                                            read(arguments.claims) if arguments.claims else {}))
