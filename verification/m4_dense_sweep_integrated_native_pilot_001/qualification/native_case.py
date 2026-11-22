"""Compute the entire fixed brief from persistent ordinary current-scene arrays."""

meshes = {
    row[0]: (tuple(tuple(map(Fraction, point)) for point in row[4]),
             tuple(tuple(face) for face in row[5]))
    for row in qualification_rows
}
require(len(meshes) == COUNTS['objects'] and all(row[3] for row in qualification_rows),
        'current_complete_native_source_required')
regions = []
for name, mesh in meshes.items():
    components, normals = partition(mesh)
    for (normal, _), indices in components:
        if normal[2] < 0 or 16 * normal[2]**2 < 9 * dot(normal, normal):
            continue
        twice_area = tuple(sum(normals[i][axis] for i in indices) for axis in range(3))
        area_squared = dot(twice_area, twice_area) / 4
        if not Fraction(19,4096)**2 <= area_squared <= Fraction(21,4096)**2:
            continue
        rectangle = boundary_rectangle(*mesh, indices, twice_area)
        if rectangle is None:
            continue
        corners, _ = rectangle
        center = tuple((a+b)/2 for a,b in zip(corners[0],corners[2],strict=True))
        checks = {view: visibility(meshes,name,indices,corners,normal,direction)
                  for view,direction in DIRECTIONS.items()}
        regions.append({'object_name':name,'source_triangle_indices':indices,
                        'center_world_m':numeric_vector(center),'corners':corners,
                        'views':{view:{'status':row['status'],
                                       'blocker':next(iter(row['positive_area_occluders']),None)}
                                 for view,row in checks.items()}})

require(len(regions) == 3,'current_native_maximal_region_count_changed')
least = min(regions,key=lambda item:item['center_world_m'][0])
corners = least['corners']
axes = tuple(zip(*corners,strict=True))
selected_min = tuple(map(min, axes))
selected_max = tuple(map(max, axes))
reference = 'M4_Far_00'
points, faces = meshes[reference]
triangles = [tuple(points[i] for i in face) for face in faces]
bound = min(sum(max(Fraction(0),lo-max(axis),min(axis)-hi)**2
                for lo,hi,axis in zip(selected_min,selected_max,zip(*tri,strict=True),strict=True))
            for tri in triangles)

def contains(point, tri):
    a,b,c = tri
    n = cross(sub(b,a),sub(c,a))
    return any(n) and dot(n,sub(point,a)) == 0 and all(
        dot(n,cross(sub(y,x),sub(point,x))) >= 0 for x,y in pairs(tri))

a = min(corners,key=lambda point:(-point[2],point[0],point[1]))
b, z_gap = None, None
for z in sorted({p[2] for p in points if p[2] > a[2]}):
    candidate = (a[0],a[1],z)
    if (z-a[2])**2 == bound and any(contains(candidate, tri) for tri in triangles):
        b, z_gap = candidate, z-a[2]
        break
require(b is not None and z_gap > 0,'ordinary_current_reference_witness_unattained')
for region in regions:
    del region['corners']
print(json.dumps({
    'source_ref':qualification_capture['source_ref'],
    'regions':regions,
    'measurement':{'object_name':least['object_name'],'reference':reference,'distance_m':float(z_gap),
                   'a':numeric_vector(a),'b':numeric_vector(b),'direction_world':[0,0,1],
                   'squared_lower_bound':str(bound),'bound_reference_faces':len(triangles)},
    'dependencies':{'numpy':int(np.arange(4).sum()),
                    'shapely':float(Polygon([(0,0),(1,0),(1,1),(0,1)]).area)},
},separators=(',',':'),allow_nan=False))
