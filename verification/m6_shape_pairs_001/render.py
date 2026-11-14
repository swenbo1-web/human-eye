"""Render actual local triangle coordinates for the frozen shape-pair cases.

The fixed PNGs use an orthographic camera and a per-pixel depth buffer.  The
self-contained HTML uses WebGL depth testing and the same original triangles.
Reference coordinates are read here only for display and error annotation.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _font(size, bold=False):
    path = Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf")
    if path.exists():
        return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _unit(vector):
    length = float(np.linalg.norm(vector))
    if not np.isfinite(length) or length == 0:
        raise ValueError("invalid_camera_vector")
    return vector / length


def _camera(normal):
    normal = _unit(np.asarray(normal, dtype=np.float64))
    up_hint = np.array([0., 0., 1.])
    up = up_hint - np.dot(up_hint, normal) * normal
    if np.linalg.norm(up) < 1e-8:
        up_hint = np.array([0., 1., 0.])
        up = up_hint - np.dot(up_hint, normal) * normal
    up = _unit(up)
    tangent = _unit(np.cross(up, normal))
    view = _unit(normal + tangent)
    right = _unit(np.cross(up, view))
    up = _unit(np.cross(view, right))
    return np.stack((right, up, view))


def _raster(vertices, faces, roi_face, basis, origin, frame, size):
    width, height = size
    transformed = (vertices - origin) @ basis.T
    low, high = (np.asarray(value, dtype=float) for value in frame)
    span = high - low
    scale = min((width - 16) / span[0], (height - 16) / span[1])
    midpoint = (low + high) / 2
    screen = transformed.copy()
    screen[:, 0] = (transformed[:, 0] - midpoint[0]) * scale + width / 2
    screen[:, 1] = height / 2 - (transformed[:, 1] - midpoint[1]) * scale
    pixels = np.full((height, width, 3), (247, 249, 250), dtype=np.uint8)
    depth = np.full((height, width), -np.inf)
    light = _unit(np.array([-.35, .55, 1.]))
    for ordinal, face in enumerate(faces):
        points = screen[face]
        x0 = max(0, int(math.floor(points[:, 0].min())))
        x1 = min(width - 1, int(math.ceil(points[:, 0].max())))
        y0 = max(0, int(math.floor(points[:, 1].min())))
        y1 = min(height - 1, int(math.ceil(points[:, 1].max())))
        if x1 < x0 or y1 < y0:
            continue
        a, b, c = points
        denominator = ((b[1] - c[1]) * (a[0] - c[0]) +
                       (c[0] - b[0]) * (a[1] - c[1]))
        if abs(denominator) < 1e-14:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        xx = xx + .5
        yy = yy + .5
        first = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / denominator
        second = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / denominator
        third = 1 - first - second
        z = first * a[2] + second * b[2] + third * c[2]
        visible = (first >= -1e-10) & (second >= -1e-10) & (third >= -1e-10)
        current = depth[y0:y1 + 1, x0:x1 + 1]
        visible &= z > current
        normal = np.cross(transformed[face[1]] - transformed[face[0]],
                          transformed[face[2]] - transformed[face[0]])
        length = float(np.linalg.norm(normal))
        if length == 0:
            continue
        brightness = .26 + .74 * abs(float(np.dot(normal / length, light)))
        base = np.array([83., 163., 177.]) if roi_face[ordinal] else np.array([165., 175., 183.])
        color = np.clip(base * brightness, 0, 255).astype(np.uint8)
        pixels[y0:y1 + 1, x0:x1 + 1][visible] = color
        current[visible] = z[visible]
    return Image.fromarray(pixels, "RGB")


def _path(base, value):
    path = Path(value)
    return path if path.is_absolute() else base / path


def _comparison(states, rows, faces, roi_face, basis, origin, frames, path):
    panel_width, panel_height = 330, 310
    left, gap, top = 30, 12, 110
    row_height = 405
    width = left * 2 + 8 * panel_width + 7 * gap
    height = top + 2 * row_height + 70
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((left, 18), "Native local surface - fixed camera and scale", font=_font(27, True), fill="#102c3a")
    draw.text((left, 56), "Teal = permitted region; grey = crossing-face context. ROI RMSE uses all 410 permitted vertices.",
              font=_font(18), fill="#425969")
    for row_index, (radius, sequence) in enumerate(rows):
        y = top + row_index * row_height
        draw.text((left, y), f"radius / D = {radius:.2f}", font=_font(21, True), fill="#173a49")
        for column, (key, label) in enumerate(sequence):
            x = left + column * (panel_width + gap)
            state = states[key]
            draw.text((x, y + 34), label, font=_font(18, True), fill="#173a49")
            if state["vertices"] is None:
                image = Image.new("RGB", (panel_width, panel_height), "#f3f5f6")
                ImageDraw.Draw(image).text((22, 120), "No reconstruction output", font=_font(17), fill="#90432c")
            else:
                image = _raster(state["vertices"], faces, roi_face, basis, origin, frames,
                                (panel_width * 2, panel_height * 2)).resize((panel_width, panel_height), Image.Resampling.LANCZOS)
            canvas.paste(image, (x, y + 64))
            rmse = "unavailable" if state["rmse_m"] is None else f"{1000 * state['rmse_m']:.3f} mm"
            draw.text((x, y + 379), f"ROI RMSE {rmse}", font=_font(17), fill="#425969")
    draw.text((left, height - 38), "Each surface is drawn from its actual coordinates. Normal reconstruction uses the same method as damaged cases.",
              font=_font(18), fill="#425969")
    canvas.save(path)
    return {"path": str(path), "pixels": [width, height], "camera": "orthographic", "supersampling": 2}


def _html_viewer(path, states, local_ids, local_faces, roi_face, basis, origin):
    entries = []
    for state in states.values():
        if state["vertices"] is None:
            continue
        points = state["vertices"][local_ids] - origin
        entries.append({"label": state["label"], "vertices": points.tolist(), "rmse_m": state["rmse_m"]})
    radius = max(float(np.linalg.norm(np.asarray(row["vertices"]), axis=1).max()) for row in entries) * 1.08
    data = json.dumps({"states": entries, "faces": local_faces.tolist(), "roi_faces": roi_face.tolist(),
                       "basis": basis.tolist(), "radius": radius}, separators=(",", ":"), allow_nan=False)
    html = """<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Yanyite local shape comparison</title>
<style>
body {
  margin: 0;
  background: #eef3f5;
  color: #143340;
  font: 15px Inter, Arial, sans-serif;
}
header {
  padding: 18px 24px;
  background: white;
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}
h1 { font-size: 19px; margin: 0; }
select, button {
  font: inherit;
  padding: 8px;
  border: 1px solid #a9bec7;
  border-radius: 5px;
  background: white;
  color: #143340;
}
canvas {
  display: block;
  width: 100vw;
  height: calc(100vh - 122px);
  touch-action: none;
}
p { margin: 0; padding: 14px 24px; background: white; }
#metric { font-variant-numeric: tabular-nums; }
</style>
<header><h1>Native local surface</h1><select id="state"></select><button id="reset">Reset view</button><span id="metric"></span></header>
<canvas id="mesh"></canvas><p>Drag to rotate. Wheel to zoom. Actual source triangles and coordinates; display uses WebGL float32. This local surface view does not assess whole-character quality.</p>
<script>
const data = __DATA__;
const canvas = document.getElementById('mesh');
const select = document.getElementById('state');
const metric = document.getElementById('metric');
const gl = canvas.getContext('webgl', { antialias: true });
if (!gl) {
  document.body.textContent = 'WebGL is unavailable. Open COMPARISON.png for the fixed-camera comparison.';
  throw Error('WebGL unavailable');
}
const vertexSource = `
  attribute vec3 position;
  attribute vec3 normal;
  attribute vec3 color;
  uniform mat3 rotation;
  uniform vec2 scale;
  uniform float depth;
  varying float shade;
  varying vec3 tone;
  void main() {
    vec3 point = rotation * position;
    vec3 direction = normalize(rotation * normal);
    shade = 0.26 + 0.74 * abs(dot(direction, normalize(vec3(-0.35, 0.55, 1.0))));
    tone = color;
    gl_Position = vec4(point.x * scale.x, point.y * scale.y, -point.z / depth, 1.0);
  }
`;
const fragmentSource = `
  precision mediump float;
  varying float shade;
  varying vec3 tone;
  void main() {
    gl_FragColor = vec4(tone * shade, 1.0);
  }
`;
function createShader(type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw Error(gl.getShaderInfoLog(shader));
  }
  return shader;
}
const program = gl.createProgram();
gl.attachShader(program, createShader(gl.VERTEX_SHADER, vertexSource));
gl.attachShader(program, createShader(gl.FRAGMENT_SHADER, fragmentSource));
gl.linkProgram(program);
if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
  throw Error(gl.getProgramInfoLog(program));
}
gl.useProgram(program);
const positionLocation = gl.getAttribLocation(program, 'position');
const normalLocation = gl.getAttribLocation(program, 'normal');
const colorLocation = gl.getAttribLocation(program, 'color');
const rotationLocation = gl.getUniformLocation(program, 'rotation');
const scaleLocation = gl.getUniformLocation(program, 'scale');
const depthLocation = gl.getUniformLocation(program, 'depth');
function triangleBuffer(state) {
  const values = [];
  data.faces.forEach((face, faceIndex) => {
    const first = state.vertices[face[0]];
    const second = state.vertices[face[1]];
    const third = state.vertices[face[2]];
    const edgeA = second.map((value, axis) => value - first[axis]);
    const edgeB = third.map((value, axis) => value - first[axis]);
    const normal = [
      edgeA[1] * edgeB[2] - edgeA[2] * edgeB[1],
      edgeA[2] * edgeB[0] - edgeA[0] * edgeB[2],
      edgeA[0] * edgeB[1] - edgeA[1] * edgeB[0]
    ];
    const color = data.roi_faces[faceIndex]
      ? [83 / 255, 163 / 255, 177 / 255]
      : [165 / 255, 175 / 255, 183 / 255];
    for (const point of [first, second, third]) {
      values.push(...point, ...normal, ...color);
    }
  });
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(values), gl.STATIC_DRAW);
  return { buffer, count: values.length / 9 };
}
const meshes = data.states.map(triangleBuffer);
data.states.forEach((state, index) => {
  const option = document.createElement('option');
  option.value = index;
  option.textContent = state.label;
  select.appendChild(option);
});
let yaw = 0;
let pitch = 0;
let zoom = 1;
function multiply(first, second) {
  return first.map(row => [0, 1, 2].map(column =>
    row.reduce((sum, value, index) => sum + value * second[index][column], 0)));
}
function cameraRotation() {
  const cosineYaw = Math.cos(yaw);
  const sineYaw = Math.sin(yaw);
  const cosinePitch = Math.cos(pitch);
  const sinePitch = Math.sin(pitch);
  const aroundUp = [[cosineYaw, 0, sineYaw], [0, 1, 0], [-sineYaw, 0, cosineYaw]];
  const aroundRight = [[1, 0, 0], [0, cosinePitch, -sinePitch], [0, sinePitch, cosinePitch]];
  return multiply(aroundUp, multiply(aroundRight, data.basis));
}
function draw() {
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(canvas.clientWidth * pixelRatio);
  const height = Math.round(canvas.clientHeight * pixelRatio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  gl.viewport(0, 0, width, height);
  gl.enable(gl.DEPTH_TEST);
  gl.disable(gl.CULL_FACE);
  gl.clearColor(.969, .976, .98, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const rotation = cameraRotation();
  gl.uniformMatrix3fv(rotationLocation, false, new Float32Array([
    rotation[0][0], rotation[1][0], rotation[2][0],
    rotation[0][1], rotation[1][1], rotation[2][1],
    rotation[0][2], rotation[1][2], rotation[2][2]
  ]));
  const extent = data.radius / zoom;
  gl.uniform2f(scaleLocation, Math.min(width, height) / width / extent,
             Math.min(width, height) / height / extent);
  gl.uniform1f(depthLocation, data.radius * 3);
  const index = Number(select.value);
  const mesh = meshes[index];
  gl.bindBuffer(gl.ARRAY_BUFFER, mesh.buffer);
  gl.enableVertexAttribArray(positionLocation);
  gl.vertexAttribPointer(positionLocation, 3, gl.FLOAT, false, 36, 0);
  gl.enableVertexAttribArray(normalLocation);
  gl.vertexAttribPointer(normalLocation, 3, gl.FLOAT, false, 36, 12);
  gl.enableVertexAttribArray(colorLocation);
  gl.vertexAttribPointer(colorLocation, 3, gl.FLOAT, false, 36, 24);
  gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
  metric.textContent = 'ROI RMSE ' + (1000 * data.states[index].rmse_m).toFixed(3) + ' mm';
}
let drag = null;
canvas.addEventListener('pointerdown', event => {
  drag = [event.clientX, event.clientY];
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => {
  if (!drag) return;
  yaw += (event.clientX - drag[0]) * .008;
  pitch += (event.clientY - drag[1]) * .008;
  drag = [event.clientX, event.clientY];
  draw();
});
canvas.addEventListener('pointerup', () => { drag = null; });
canvas.addEventListener('pointercancel', () => { drag = null; });
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  zoom = Math.max(.3, Math.min(5, zoom * Math.exp(-event.deltaY * .001)));
  draw();
}, { passive: false });
select.addEventListener('change', draw);
document.getElementById('reset').addEventListener('click', () => {
  yaw = 0;
  pitch = 0;
  zoom = 1;
  draw();
});
window.addEventListener('resize', draw);
draw();
</script></html>"""
    path.write_text(html.replace("__DATA__", data), encoding="utf8", newline="\n")


def render_preview(manifest_path):
    started = time.perf_counter()
    manifest_path = Path(manifest_path).resolve()
    base = manifest_path.parent
    manifest = json.loads(manifest_path.read_bytes())
    reference = np.load(_path(base, manifest["reference_npy"]), allow_pickle=False)
    triangles = np.load(_path(base, manifest["triangles_npy"]), allow_pickle=False)
    region = np.asarray(manifest["region_ids"], dtype=np.int64)
    center_id = int(manifest["center_vertex_id"])
    origin = reference[center_id].copy()
    basis = _camera(manifest["center_normal"])
    region_set = set(region.tolist())
    selected_faces = triangles[np.any(np.isin(triangles, region), axis=1)]
    roi_face = np.array([all(int(index) in region_set for index in face) for face in selected_faces])
    local_ids = np.unique(selected_faces)
    local_map = np.full(len(reference), -1, dtype=np.int64)
    local_map[local_ids] = np.arange(len(local_ids))
    local_faces = local_map[selected_faces]
    states = {"reference": {"vertices": reference, "label": "Normal reference", "rmse_m": 0.}}
    normal_case = next(case for case in manifest["cases"] if float(case.get("amplitude_ratio", 0)) == 0.)
    normal_repaired = normal_case.get("repaired_npy")
    def add_state(key, path, label):
        value = np.load(_path(base, path), allow_pickle=False) if path else None
        if value is not None and (value.shape != reference.shape or not np.isfinite(value).all()):
            raise ValueError("invalid_preview_coordinate_array")
        rmse = None if value is None else float(np.sqrt(np.mean(np.sum((value[region] - reference[region])**2, axis=1))))
        states[key] = {"vertices": value, "label": label, "rmse_m": rmse}
    add_state("normal_repaired", normal_repaired, "Normal control - reconstructed")
    rows = []
    radii = sorted({float(case["radius_ratio"]) for case in manifest["cases"] if case.get("radius_ratio") is not None})
    for radius in radii:
        sequence = [("reference", "Normal reference"), ("normal_repaired", "Normal rebuilt")]
        cases = sorted([case for case in manifest["cases"] if case.get("radius_ratio") is not None and float(case["radius_ratio"]) == radius],
                       key=lambda case: float(case["amplitude_ratio"]))
        if len(cases) != 3:
            raise ValueError("preview_requires_three_amplitudes_per_radius")
        for case in cases:
            ratio = float(case["amplitude_ratio"])
            damaged_key, repaired_key = case["id"] + "_damaged", case["id"] + "_repaired"
            add_state(damaged_key, case["abnormal_npy"], f"r/D {radius:.2f}, a/r {ratio:.2f} - damaged")
            add_state(repaired_key, case.get("repaired_npy"), f"r/D {radius:.2f}, a/r {ratio:.2f} - reconstructed")
            sequence.extend(((damaged_key, f"Dent a/r {ratio:.2f}"), (repaired_key, f"Rebuilt a/r {ratio:.2f}")))
        rows.append((radius, sequence))
    if len(rows) != 2:
        raise ValueError("preview_requires_two_radii")
    projected = np.concatenate([(state["vertices"][local_ids] - origin) @ basis.T
                                for state in states.values() if state["vertices"] is not None])
    lower, upper = projected[:, :2].min(0), projected[:, :2].max(0)
    padding = .08 * np.maximum(upper - lower, .001)
    frame = [(lower - padding).tolist(), (upper + padding).tolist()]
    outputs = [_comparison(states, rows, selected_faces, roi_face, basis, origin, frame, base / "COMPARISON.png")]
    detail_frame = [[-.036, -.036], [.036, .036]]
    outputs.append(_comparison(states, rows, selected_faces, roi_face, basis, origin, detail_frame, base / "DETAIL.png"))
    _html_viewer(base / "VIEWER.html", states, local_ids, local_faces, roi_face, basis, origin)
    outputs.append({"path": str(base / "VIEWER.html"), "kind": "self_contained_webgl", "external_dependencies": 0})
    for output in outputs:
        data = Path(output["path"]).read_bytes()
        output.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    normal = _unit(np.asarray(manifest["center_normal"]))
    return {"outputs": outputs, "wall_s": time.perf_counter() - started,
            "camera": {"origin_world_m": origin.tolist(), "basis_right_up_view": basis.tolist(),
                       "oblique_angle_from_reference_center_normal_deg": 45., "projection_frame_m": frame,
                       "detail_frame_m": detail_frame, "framing": "common union of actual local states; detail is a common fixed center window"},
            "geometry": {"source_vertices_used": len(local_ids), "source_triangles_used": len(selected_faces),
                         "region_vertices": len(region), "reference_normal_radial_dot_m": float(normal @ (origin - reference[region].mean(0)))},
            "scope": "Actual local source triangle rendering. PNG has depth buffering; HTML uses WebGL depth testing. No artistic correction acceptance implied."}


if __name__ == "__main__":
    import sys
    print(json.dumps(render_preview(sys.argv[1]), indent=2, allow_nan=False))
