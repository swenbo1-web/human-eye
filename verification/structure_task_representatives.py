"""Procedural finite-domain shapes and analytic expectations, not imported assets."""
import math


def cases():
    vertices=[];faces=[]
    for i in range(16):
        u=2*math.pi*i/16
        for j in range(8):
            v=2*math.pi*j/8;r=1+.25*math.cos(v)
            vertices.append([r*math.cos(u),r*math.sin(u),.25*math.sin(v)])
    for i in range(16):
        for j in range(8):
            a=i*8+j;b=((i+1)%16)*8+j;c=((i+1)%16)*8+(j+1)%8;d=i*8+(j+1)%8
            faces.extend([[a,b,c],[a,c,d]])
    closed=dict(id='closed_triangulated_torus',vertices=vertices,polygons=faces,boundary_clusters=0,
        unknown_degeneracy=False,want_image=False)
    opened=dict(closed,id='torus_missing_cell',polygons=faces[2:],boundary_clusters=1,want_image=True)
    strip_vertices=[[i/8-1,j/4-.25,.3*math.sin(math.pi*i/16)+.15*(j/4-.25)*i/16]
        for i in range(17) for j in range(3)]
    strip_faces=[]
    for i in range(16):
        for j in range(2):
            a=i*3+j;b=(i+1)*3+j;c=b+1;d=a+1
            strip_faces.extend([[a,b,c],[a,c,d]])
    strip=dict(id='curved_triangulated_strip',vertices=strip_vertices,polygons=strip_faces,boundary_clusters=1,
        unknown_degeneracy=False,want_image=True)
    nonplanar=dict(id='nonplanar_legal_quad',vertices=[[0,0,0],[1,0,0],[1,1,.25],[0,1,0]],polygons=[[0,1,2,3]],
        boundary_clusters=1,unknown_degeneracy=True,want_image=True)
    reference=dict(id='reference_planar_aperture',boundary_clusters=2,unknown_degeneracy=False,want_image=True)
    return [closed,opened,strip,nonplanar,reference]
