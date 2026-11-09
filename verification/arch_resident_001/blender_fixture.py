"""Owned background Blender fixture and loopback addon-shaped test server.

Only this test process accepts generic code; no production worker is changed.
"""
import contextlib
import io
import json
from pathlib import Path
import socket
import sys

import bpy


def cube(name, center, half):
    points = [(x * half[0], y * half[1], z * half[2])
              for x, y, z in ((-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                              (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1))]
    faces = [(0,2,3),(0,3,1),(4,5,7),(4,7,6),(0,1,5),(0,5,4),
             (2,6,7),(2,7,3),(0,4,6),(0,6,2),(1,3,7),(1,7,5)]
    mesh = bpy.data.meshes.new(name + 'Mesh')
    mesh.from_pydata(points, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = center
    return obj


def control(value):
    op = value['op']
    if op == 'translate':
        bpy.data.objects[value['name']].location.z += value['dz']
    elif op == 'mesh':
        obj = bpy.data.objects[value['name']]
        obj.data.vertices[0].co.z += value['dz']
        obj.data.update()
    elif op == 'rename':
        bpy.data.objects[value['name']].name = value['new_name']
    elif op == 'replace':
        obj = bpy.data.objects[value['name']]
        location = tuple(obj.location)
        bpy.data.objects.remove(obj, do_unlink=True)
        cube(value['name'], location, (.01,.01,.002))
    elif op == 'delete':
        bpy.data.objects.remove(bpy.data.objects[value['name']], do_unlink=True)
    elif op == 'units':
        bpy.context.scene.unit_settings.scale_length = value['scale']
    elif op == 'frame':
        bpy.context.scene.frame_set(value['frame'])
    elif op == 'undo':
        bpy.ops.ed.undo_push(message='Resident before temporary edit')
        bpy.data.objects['BluePart'].location.z += .1
        bpy.context.view_layer.update()
        bpy.ops.ed.undo_push(message='Resident temporary edit')
        bpy.ops.ed.undo()
    elif op == 'scene':
        for name in ('BluePart', 'GreyBase'):
            bpy.data.objects[name].name = 'FirstScene_' + name
        scene = bpy.data.scenes.new('SecondScene')
        bpy.context.window.scene = scene
        cube('BluePart', (0,0,.019), (.01,.01,.005))
        cube('GreyBase', (0,0,-.005), (.04,.04,.005))
    elif op == 'load':
        bpy.ops.wm.open_mainfile(filepath=value['path'])
    elif op == 'stats':
        found = []
        for name, module in tuple(sys.modules.items()):
            if name.startswith('_human_eye_mcp_resident_'):
                host = getattr(module, '_mcp_resident_host', None)
                if host:
                    found.append({'module': name, 'host': repr(host),
                                  'stats': host.residency_work() if hasattr(host, 'residency_work') else {}})
        return found
    else:
        raise ValueError(op)
    bpy.context.view_layer.update()
    return {'ok': True}


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    fixture, ready = map(Path, args[:2])
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.scene.unit_settings.scale_length = 1.
    cube('BluePart', (0,0,.009), (.01,.01,.005))
    cube('GreyBase', (0,0,-.005), (.04,.04,.005))
    for i in range(8):
        cube('Far%02d' % i, (1+i,0,0), (.01,.01,.01))
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(fixture))
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen()
    ready.write_text(json.dumps({'port': server.getsockname()[1]}), encoding='utf8')
    while True:
        client, _ = server.accept()
        with client:
            raw = bytearray()
            while True:
                raw.extend(client.recv(65536))
                try:
                    request = json.loads(raw)
                    break
                except json.JSONDecodeError:
                    continue
            try:
                if request['type'] == 'test_control':
                    result = control(request['params'])
                    response = {'control': result}
                else:
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        exec(request['params']['code'], {'bpy': bpy})
                    response = {'status': 'success', 'result': {'executed': True, 'result': output.getvalue()}}
            except Exception as exc:
                response = {'status': 'error', 'message': repr(exc)}
            client.sendall(json.dumps(response, allow_nan=False).encode('utf8'))


if __name__ == '__main__':
    main()
