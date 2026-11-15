"""Independent fresh-process export from an actual saved mesh."""

import argparse
from pathlib import Path
import sys

import bpy
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--object-name', required=True)
parser.add_argument('--output', required=True)
options = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
target = bpy.data.objects[options.object_name]
mesh = target.data
native = np.array([tuple(v.co) for v in mesh.vertices], dtype=np.float32)
matrix = np.array(target.matrix_world, dtype=np.float64)
world = native.astype(np.float64)@matrix[:3, :3].T+matrix[:3, 3]
mesh.calc_loop_triangles()
faces = np.array([tuple(f.vertices) for f in mesh.loop_triangles], dtype=np.int64)
offsets = np.r_[0, np.cumsum([len(p.vertices) for p in mesh.polygons])]
polygon_vertices = np.array([v for p in mesh.polygons for v in p.vertices], dtype=np.int64)
path = Path(options.output)
assert not path.exists()
path.parent.mkdir(parents=True, exist_ok=True)
np.savez_compressed(path, vertices_local=native, vertices_world=world, matrix_world=matrix,
                    faces=faces, poly_offsets=offsets, poly_vertices=polygon_vertices)
print('independently_read_saved_mesh', len(native), len(faces))
