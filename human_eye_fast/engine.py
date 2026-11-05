"""Persistent, trusted-input triangle facts and task views.

The caller owns topology and change declarations. A frame update copies only
declared changed vertices and recomputes their incident faces. Queries read
resident arrays; there are no source proofs, hashes, deadlines, ledgers,
round trips, input validation, or conservative coordinate-error rejection.
All vertices use the same metric coordinate system. ``bounds`` applies to
each frame's current coordinates and selects whole intersecting triangles.
"""
from dataclasses import dataclass

import numpy as np

from .kernels import prepare_reference, deformation_metrics, triangle_box_mask


_STATE_NAMES = ("measured", "collapsed", "undefined")
_EXTREMA_NAMES = ("max_stretch", "min_stretch", "min_area", "max_area")


@dataclass
class _Frame:
    vertices: np.ndarray
    stretches: np.ndarray
    area_ratio: np.ndarray
    states: np.ndarray
    lower: np.ndarray
    upper: np.ndarray


class FastSession:
    """A fixed reference mesh with any number of resident current frames.

    Arrays are copied at ingestion, so the session owns its cache. Callers
    explicitly call ``set_frame`` after edits; omitting a changed vertex
    deliberately leaves the corresponding resident value unchanged. Replace
    the session when topology or reference geometry changes.
    """

    def __init__(self, reference_vertices, triangles):
        self.reference_vertices = np.array(reference_vertices, dtype=np.float64, copy=True)
        self.triangles = np.array(triangles, dtype=np.int64, copy=True).reshape(-1, 3)
        self.reference = prepare_reference(self.reference_vertices, self.triangles)
        self._all_faces = np.arange(len(self.triangles), dtype=np.int64)
        # CSR vertex -> original face adjacency, built once. A repeated
        # vertex within a face is harmless: dirty lookup uniquifies faces.
        flat_vertices = self.triangles.ravel()
        order = np.argsort(flat_vertices, kind="stable")
        self._vertex_faces = (order // 3).astype(np.int64, copy=False)
        counts = np.bincount(flat_vertices, minlength=len(self.reference_vertices))
        self._vertex_offsets = np.concatenate(([0], np.cumsum(counts)))
        self.frames = {}

    def _incident_faces(self, vertices):
        starts = self._vertex_offsets[vertices]
        lengths = self._vertex_offsets[vertices + 1] - starts
        total = int(lengths.sum())
        positions = (np.repeat(starts, lengths) + np.arange(total)
                     - np.repeat(np.cumsum(lengths) - lengths, lengths))
        return np.unique(self._vertex_faces[positions])

    def set_frame(self, label, vertices, *, changed_vertices=None):
        """Install a full frame or apply an explicit dirty-vertex update.

        ``vertices`` is the full coordinate array in both cases. A first
        insertion always initializes all faces. With a float64 ndarray input,
        later dirty updates cost O(dirty vertices + incident faces), apart
        from sorting that incident set; no full mesh hashing, traversal, or
        coordinate copy is performed. Other inputs incur array conversion.
        """
        incoming = np.asarray(vertices, dtype=np.float64)
        fresh = label not in self.frames
        full = fresh or changed_vertices is None
        if fresh:
            count = len(self.triangles)
            frame = _Frame(incoming.copy(), np.empty((count, 2)), np.empty(count),
                           np.empty(count, dtype=np.uint8), np.empty((count, 3)),
                           np.empty((count, 3)))
            self.frames[label] = frame
        else:
            frame = self.frames[label]
        if full:
            if not fresh:
                frame.vertices[:] = incoming
            faces = self._all_faces
            changed_count = len(incoming)
        else:
            changed = np.unique(np.asarray(changed_vertices, dtype=np.int64))
            frame.vertices[changed] = incoming[changed]
            faces = self._incident_faces(changed)
            changed_count = len(changed)

        if len(faces):
            metrics = deformation_metrics(self.reference, frame.vertices, faces)
            frame.stretches[faces] = metrics["stretches"]
            frame.area_ratio[faces] = metrics["area_ratio"]
            valid = np.isfinite(metrics["stretches"]).all(axis=1) & np.isfinite(metrics["area_ratio"])
            frame.states[faces] = np.where(valid, np.where(metrics["area_ratio"] == 0, 1, 0), 2)
            points = frame.vertices[self.triangles[faces]]
            frame.lower[faces] = points.min(axis=1)
            frame.upper[faces] = points.max(axis=1)
        return {"label": label, "update": "full" if full else "sparse",
                "vertices_updated": int(changed_count), "faces_recomputed": len(faces),
                "total_faces": len(self.triangles)}

    def _members(self, frame, bounds):
        if bounds is None:
            return self._all_faces
        low, high = np.asarray(bounds, dtype=np.float64)
        candidates = np.flatnonzero(np.all(frame.upper >= low, axis=1)
                                   & np.all(frame.lower <= high, axis=1))
        points = frame.vertices[self.triangles[candidates]]
        return candidates[triangle_box_mask(points, low, high)]

    def _summary(self, frame, members, threshold_high, threshold_low):
        state = frame.states[members]
        counts = np.bincount(state, minlength=3)
        valid_ids = members[state != 2]
        mixed = members[(state == 0) & (frame.stretches[members, 0] >= threshold_high)
                        & (frame.stretches[members, 1] <= threshold_low)]
        extrema = dict.fromkeys(_EXTREMA_NAMES)
        witnesses = dict.fromkeys(_EXTREMA_NAMES)
        if len(valid_ids):
            values = (frame.stretches[valid_ids, 0], frame.stretches[valid_ids, 1],
                      frame.area_ratio[valid_ids], frame.area_ratio[valid_ids])
            for name, value, pick in zip(_EXTREMA_NAMES, values,
                                         (np.argmax, np.argmin, np.argmin, np.argmax)):
                local = int(pick(value))
                extrema[name] = float(value[local])
                witnesses[name] = int(valid_ids[local])
        summary = {"core_count": len(members),
                   "states": {name: int(counts[index]) for index, name in enumerate(_STATE_NAMES)},
                   "mixed": True if len(mixed) else None if counts[2] else False,
                   "extrema": extrema, "extrema_triangles": witnesses}
        undefined = members[state == 2]
        return summary, mixed, undefined

    def _row(self, frame, index):
        state = int(frame.states[index])
        return {"triangle": int(index), "state": _STATE_NAMES[state],
                "stretches": frame.stretches[index].tolist() if state != 2 else None,
                "area_ratio": float(frame.area_ratio[index]) if state != 2 else None}

    def rows(self, label, indices):
        """Read selected original-face facts directly from resident arrays."""
        frame = self.frames[label]
        return [self._row(frame, index) for index in indices]

    def query(self, labels, *, bounds=None, threshold_high=1.1, threshold_low=0.9,
              max_witnesses=4, details=None):
        """Produce complete core summaries and a compact cross-frame view.

        ``max_witnesses`` is an automatic output-selection preference, not a
        resource or permission gate. Explicit ``details`` are always retained
        and consume that preference first. ``None`` allows all automatic
        candidates. Insufficient room for positive-frame witnesses is exposed
        in ``uncovered_labels`` rather than refusing the task or hiding facts.
        Degenerate-reference/nonfinite metrics are ``undefined``; an original
        version's conservative source/precision unknown is not reproduced.
        """
        labels = tuple(labels)
        summaries, memberships, positive, undefined = {}, {}, {}, {}
        for label in labels:
            frame = self.frames[label]
            members = self._members(frame, bounds)
            summary, mixed, missing = self._summary(frame, members, threshold_high, threshold_low)
            summaries[label] = summary
            memberships[label] = members
            positive[label] = mixed
            undefined[label] = missing

        selected = set() if details is None else set(map(int, details))
        limit = len(self.triangles) if max_witnesses is None else max_witnesses
        missing_labels = [label for label in labels if len(positive[label])
                          and not selected.intersection(positive[label])]
        # Greedy multi-frame coverage chooses the face explaining the largest
        # number of still-uncovered positive frames. Stable IDs break ties.
        while missing_labels and len(selected) < limit:
            candidates, counts = np.unique(np.concatenate([positive[label] for label in missing_labels]),
                                           return_counts=True)
            chosen = int(candidates[np.argmax(counts)])
            selected.add(chosen)
            missing_labels = [label for label in missing_labels if chosen not in positive[label]]

        for label in labels:
            optional = ([int(undefined[label][0])] if len(undefined[label]) else [])
            optional += [index for index in summaries[label]["extrema_triangles"].values() if index is not None]
            for index in optional:
                if len(selected) >= limit:
                    break
                selected.add(index)

        selected = sorted(selected)
        witnesses = []
        for index in selected:
            rows = {}
            for label in labels:
                row = self._row(self.frames[label], index)
                row.pop("triangle")
                members = memberships[label]
                position = np.searchsorted(members, index)
                row["in_core"] = bool(position < len(members) and members[position] == index)
                rows[label] = row
            witnesses.append({"triangle": index, "frames": rows})
        return {"schema": "human-eye-fast-task-v1", "threshold_high": float(threshold_high),
                "threshold_low": float(threshold_low),
                "bounds": None if bounds is None else np.asarray(bounds).tolist(),
                "selected_triangles": selected, "uncovered_labels": missing_labels,
                "frames": summaries, "witnesses": witnesses}
