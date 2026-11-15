"""Fetch the six authorized archives and preserve selected source bytes and metadata."""

import hashlib
import json
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
NAMES = ("horse", "camel", "face", "head", "cat", "lion")
PAGE = "https://people.csail.mit.edu/sumner/research/deftransfer/data.html"
ROOT = "https://people.csail.mit.edu/sumner/research/deftransfer/data/"
ARCHIVE_LIMIT = 256 * 1024**2
DISK_LIMIT = 2 * 1024**3


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def natural(value):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def parse_obj(data):
    vertices, normals, faces, normal_ids = [], [], [], []
    for line in data.decode("utf-8-sig").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "v":
            vertices.append([float(x) for x in fields[1:4]])
        elif fields[0] == "vn":
            normals.append([float(x) for x in fields[1:4]])
        elif fields[0] == "f":
            if len(fields) != 4:
                raise ValueError("source_face_is_not_triangle")
            corners = [part.split("/") for part in fields[1:]]
            face = [int(part[0]) for part in corners]
            faces.append([i - 1 if i > 0 else len(vertices) + i for i in face])
            normal_ids.append([int(part[2]) - 1 if len(part) > 2 and part[2] else -1 for part in corners])
    result = dict(vertices=np.asarray(vertices, dtype=np.float64), faces=np.asarray(faces, dtype=np.int64),
                  source_normals=np.asarray(normals, dtype=np.float64).reshape(-1, 3),
                  face_normal_ids=np.asarray(normal_ids, dtype=np.int64))
    if result["faces"].min() < 0 or result["faces"].max() >= len(vertices):
        raise ValueError("source_vertex_index_out_of_range")
    return result


def disk_bytes():
    return sum(path.stat().st_size for path in HERE.rglob("*") if path.is_file())


def main():
    started, cpu = time.perf_counter(), time.process_time()
    private = HERE / "private"
    for name in ("archives", "source", "source_notes"):
        (private / name).mkdir(parents=True, exist_ok=True)
    initial_path = HERE / "ACQUISITION.json"
    initial = json.loads(initial_path.read_bytes()) if initial_path.exists() else None
    if initial and not initial["errors"]:
        raise RuntimeError("acquisition_already_recorded")
    report = dict(cycle_id="M6-PERCEPTION-DATA-001", archives=[], selected=[], documents=[], errors=[],
                  archive_http_bytes=initial["archive_http_bytes"] if initial else 0,
                  network_requests=initial["network_requests"] if initial else [], package_terms_review="pending_manual_read",
                  recovery="retain original attempt, accept OBJ-syntax reference .pose extension, reuse already downloaded bytes" if initial else None)

    def fetch(url, path, archive=False):
        if path.exists():
            if not initial:
                raise RuntimeError("refuse_download_overwrite")
            return dict(url=url, path=path.relative_to(HERE).as_posix(), bytes=path.stat().st_size,
                        sha256=sha(path.read_bytes()), reused_initial_download=True)
        request_started = time.perf_counter()
        count = 0
        try:
            with urllib.request.urlopen(url, timeout=60) as response, path.open("xb") as output:
                if archive and int(response.headers.get("Content-Length", 0)) + report["archive_http_bytes"] > ARCHIVE_LIMIT:
                    raise RuntimeError("archive_content_length_exceeds_budget")
                while block := response.read(1024 * 256):
                    count += len(block)
                    if archive:
                        report["archive_http_bytes"] += len(block)
                    if report["archive_http_bytes"] > ARCHIVE_LIMIT or disk_bytes() + len(block) > DISK_LIMIT:
                        raise RuntimeError("network_or_disk_budget_exceeded")
                    output.write(block)
                headers = dict(response.headers)
            return dict(url=url, path=path.relative_to(HERE).as_posix(), bytes=count,
                        sha256=sha(path.read_bytes()), headers=headers)
        finally:
            report["network_requests"].append(dict(url=url, transferred_body_bytes=count,
                                                   wall_s=time.perf_counter() - request_started))

    try:
        report["source_page"] = fetch(PAGE, private / "source_notes/data.html")
        for asset in NAMES:
            archive = private / "archives" / (asset + "-poses.zip")
            row = fetch(ROOT + archive.name, archive, True)
            with zipfile.ZipFile(archive) as package:
                entries = [entry for entry in package.infolist() if not entry.is_dir()]
                row["members"] = [dict(name=entry.filename, bytes=entry.file_size, crc32=entry.CRC) for entry in entries]
                obj_names = sorted([entry.filename for entry in entries if entry.filename.lower().endswith((".obj", ".pose"))], key=natural)
                references = [name for name in obj_names if "-reference" in name.lower()]
                if len(references) != 1:
                    raise ValueError("expected_exactly_one_reference_" + asset)
                first_pose = next((name for name in obj_names if name != references[0]), None)
                row["obj_files_natural_order"] = obj_names
                for entry in entries:
                    if not entry.filename.lower().endswith((".obj", ".pose")) and entry.file_size < 1024 * 1024:
                        data = package.read(entry)
                        path = private / "source_notes" / (asset + "__" + Path(entry.filename).name)
                        path.write_bytes(data)
                        report["documents"].append(dict(asset=asset, member=entry.filename, path=path.relative_to(HERE).as_posix(),
                                                        sha256=sha(data), bytes=len(data), text=data.decode("utf8", errors="replace")))
                reference_vertices = None
                reference_faces = None
                for slot, name in enumerate([references[0]] + ([first_pose] if first_pose else [])):
                    data = package.read(name)
                    source_id = asset + ("_reference" if slot == 0 else "_pose1")
                    obj_path = private / "source" / (source_id + ".obj")
                    obj_path.write_bytes(data)
                    arrays = parse_obj(data)
                    array_path = private / "source" / (source_id + ".npz")
                    np.savez_compressed(array_path, **arrays)
                    vertices, faces = arrays["vertices"], arrays["faces"]
                    item = dict(id=source_id, asset=asset, posture="reference" if slot == 0 else "pose1", member=name,
                                archive_sha256=row["sha256"], obj_sha256=sha(data), obj_path=obj_path.relative_to(HERE).as_posix(),
                                array_path=array_path.relative_to(HERE).as_posix(), array_sha256=sha(array_path.read_bytes()),
                                vertex_count=len(vertices), triangle_count=len(faces), source_normal_count=len(arrays["source_normals"]),
                                finite_vertices=int(np.isfinite(vertices).all(axis=1).sum()),
                                bounds_min=vertices.min(axis=0).tolist(), bounds_max=vertices.max(axis=0).tolist(),
                                bbox_diagonal=float(np.linalg.norm(np.ptp(vertices, axis=0))))
                    if slot == 0:
                        reference_vertices, reference_faces = vertices, faces
                    item["coordinates_identical_to_reference"] = np.array_equal(vertices, reference_vertices)
                    item["topology_identical_to_reference"] = np.array_equal(faces, reference_faces)
                    report["selected"].append(item)
            report["archives"].append(row)
            write_json(HERE / "ACQUISITION_PROGRESS.json", report)
            print(asset, row["bytes"], [(r["id"], r["vertex_count"], r["triangle_count"]) for r in report["selected"] if r["asset"] == asset], flush=True)
    except Exception as error:
        report["errors"].append(dict(type=type(error).__name__, message=str(error)))
        raise
    finally:
        report.update(wall_s_before_write=time.perf_counter() - started, process_cpu_s_before_write=time.process_time() - cpu,
                      new_disk_bytes_before_write=disk_bytes())
        write_json(HERE / "ACQUISITION.json", report)


if __name__ == "__main__":
    main()
