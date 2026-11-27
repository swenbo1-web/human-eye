"""Build only the fixed 044 pressure arrays inside the owned private GUI copy."""
import hashlib
import json
from pathlib import Path
import struct

import bpy

job = json.loads(Path(M6_044_PRESSURE_BUILD_JOB).read_bytes())
geometry_path = Path(job["geometry"]["path"])
raw = geometry_path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == job["geometry"]["sha256"]
geometry = json.loads(raw)
destination = Path(job["destination"])
assert destination.is_absolute() and not destination.exists()
assert destination.is_relative_to(Path(job["owned_root"]))
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for key in ("left", "right"):
    data = geometry[key]
    for vertex in data["vertices_world"]:
        for value in vertex:
            assert struct.pack("<d", struct.unpack("<f", struct.pack("<f", value))[0]) == struct.pack("<d", value)
    mesh = bpy.data.meshes.new(data["name"] + "_fixed_mesh")
    mesh.from_pydata(data["vertices_world"], [], data["faces"])
    mesh.update()
    obj = bpy.data.objects.new(data["name"], mesh)
    bpy.context.scene.collection.objects.link(obj)
bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 1.0
bpy.context.scene.frame_set(1, subframe=0.0)
bpy.context.view_layer.update()
bpy.context.preferences.filepaths.save_version = 0
result = bpy.ops.wm.save_as_mainfile(filepath=str(destination), copy=True, check_existing=False)
assert result == {"FINISHED"} and destination.is_file()
print("M6_044_PRESSURE_SAVED:" + json.dumps(dict(status="saved_once", destination=str(destination),
      bytes=destination.stat().st_size, sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
      open_filepath=bpy.data.filepath, names=[geometry[k]["name"] for k in ("left", "right")]), sort_keys=True))
