"""Local provenance negatives and exact midpoint boundary refinement."""
import copy

from verification.nonplanar_patch_fixtures import source,cases,audit_cases


def split_edge(native,edges,edge):
    target=native['objects'][0];a,b=edge
    incident=[i for i,f in enumerate(target['faces']) if a in f and b in f]
    assert len(incident)==1
    index=incident[0];face=target['faces'][index];vertices=target['world_vertices']
    midpoint=len(vertices);vertices.append([(vertices[a][k]+vertices[b][k])/2 for k in range(3)])
    for j in range(3):
        x,y=face[j],face[(j+1)%3]
        if {x,y}=={a,b}:break
    third=next(v for v in face if v not in (a,b))
    target['faces'][index:index+1]=[[x,midpoint,third],[midpoint,y,third]]
    position=edges.index(list(edge));edges[position:position+1]=[[a,midpoint],[midpoint,b]]


def sampling_case():
    return dict(cases()[1],id='visible_edge_vote_bias',blocker=[-.015,.015,-.15,.15],want=False,pairs=6)


def local_cases():
    values=[dict(case,known_failure=False) for case in audit_cases()]
    values.append(sampling_case())
    values.append(dict(sampling_case(),id='same_surface_split_edges',split_edges=True))
    values.append(dict(cases()[1],id='hidden_original_boundary',occluding_shells=True,want=False,pairs=12))
    return values


def local_source(case):
    native,edges=source(case)
    if case.get('split_edges'):
        for edge in ([5,6],[7,4]):split_edge(native,edges,edge)
    if case.get('occluding_shells'):
        target=native['objects'][0];points=copy.deepcopy(target['world_vertices']);faces=copy.deepcopy(target['faces'])
        for direction in (-1,1):
            begin=len(target['world_vertices'])
            target['world_vertices'] += [[x+direction*.005,y,z] for x,y,z in points]
            target['faces'] += [[v+begin for v in face] for face in faces]
    return native,edges
