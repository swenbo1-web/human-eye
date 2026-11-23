"""Archive-backed RNA for the isolated loopback preflight only."""

from itertools import product
from types import SimpleNamespace as RNA


def make_mesh(arrays, name=''):
    polygons = []
    loops = []
    for indices in arrays['polygons']:
        # The sealed device schema preserves the original polygon vertex order.
        if isinstance(indices, dict):
            indices = indices['vertices']
        polygons.append(RNA(vertices=tuple(indices), loop_start=len(loops),
                            loop_total=len(indices)))
        loops.extend(RNA(vertex_index=i) for i in indices)
    return RNA(name=name,
               vertices=[RNA(co=tuple(point)) for point in arrays['vertices']],
               polygons=polygons, loops=loops,
               loop_triangles=[RNA(vertices=tuple(face)) for face in arrays['triangles']],
               calc_loop_triangles=lambda: None)


def archive_as_bpy(archive):
    """Supply exact archived arrays and explicitly synthesized RNA extents."""
    source = archive['source']
    objects = []
    for row in archive['objects']:
        native = make_mesh(row['native'], row['mesh_name'])
        evaluated = make_mesh(row['evaluated'], row['mesh_name'])
        corners = tuple(product(*[(min(v.co[k] for v in evaluated.vertices),
                                   max(v.co[k] for v in evaluated.vertices))
                                  for k in range(3)]))
        obj = RNA(name=row['name'], name_full=row['name'], type='MESH',
                  session_uid=int(row['instance_id']), matrix_world=row['native_matrix_world'],
                  data=native, modifiers=[RNA(**m) for m in row['modifiers']],
                  children=[], parent=RNA(name=row['parent']) if row['parent'] else None,
                  hide_viewport=row['display']['hide_viewport'],
                  hide_render=row['display']['hide_render'],
                  visible_get=lambda *, view_layer, value=row['visible_get']: value,
                  hide_get=lambda *, view_layer=None, value=row['display']['hide_get']: value)
        ev = RNA(data=evaluated, is_evaluated=True, matrix_world=row['matrix_world'],
                 bound_box=corners, to_mesh=lambda value=evaluated: value,
                 to_mesh_clear=lambda: None)
        obj.evaluated_get = lambda graph, value=ev: value
        objects.append(obj)
    scene = RNA(name=source['scene'], objects=objects,
                session_uid=1 + max(obj.session_uid for obj in objects),
                frame_current=source['frame'], frame_subframe=source['subframe'],
                unit_settings=RNA(**source['unit_settings']))
    graph = RNA(scene_eval=scene, updates=(), object_instances=())
    layer = RNA(name=source['view_layer'], depsgraph=graph, update=lambda: None,
                as_pointer=lambda: int(source['view_layer_id'].removeprefix('rna:')))
    return RNA(context=RNA(scene=scene, view_layer=layer, evaluated_depsgraph_get=lambda: graph),
               app=RNA(driver_namespace={}, handlers=RNA(depsgraph_update_post=[], undo_post=[],
                       redo_post=[], load_post=[])),
               data=RNA(filepath=source['asset_copy']))
