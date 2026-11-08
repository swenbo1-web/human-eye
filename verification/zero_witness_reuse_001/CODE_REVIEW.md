# ZERO-WITNESS-REUSE-001 code review

Read-only integration review of the three product files below. No tests, imports,
models, Blender, or RPC were run for this review. The reviewer authored the four
producer lines; consumer validation and task/cache wiring were reviewed separately
from their author. This is source review, not runtime or performance acceptance.

| Product source | SHA256 |
| --- | --- |
| `human_eye_plugin/surface_geometry.py` | `f0c81f1aa7ed406bbe574cfeb697d07a3c83a6c5e493bfaa806f7809a3fc1bd8` |
| `human_eye_plugin/surface_proximity.py` | `b9f537d4f40b8a98a826017f1fe972d0399d58fde0b97753945cf20ceb02a593` |
| `human_eye_plugin/task_query.py` | `2b42ca8bb03d6dc8316e17b03612097078963f2390f1b6c21e2b1ece4d609f0a` |

No blocking code defect found in the inspected internal same-query call path.

- **Provenance/frame:** `surface_geometry.py:454` captures only a nonempty exact
  cross-surface intersection, after both shells passed embedded validation and
  before transverse/touching/unknown classification. Triangle ordinals are
  unchanged by `_closed_topology`. The contact holds the exact preparation tuple;
  that tuple carries the common origin/factor and original ordered mesh references.
  Prior contact is cleared at classifier entry (`:428`).
- **Consumer admission/membership:** `surface_proximity.py:508` requires tuple
  identity, exact coordinate types and in-range triangle ordinals. It checks the
  point lies on both triangle planes and within all three projected closed edges.
  Nonzero normals make the largest-normal-axis projection nondegenerate. `:549`
  also requires preparation records to reference the current left/right objects;
  a mismatch admits fresh geometry and ignores the contact. Invalid or bounded
  predicate evidence falls back to normal nearest traversal.
- **No label shortcut:** only validated contact skips `_nearest` (`:558`). A
  penetrating label/containment without a boundary intersection cannot supply the
  holder field. A later honest closed unknown can retain the independently valid
  boundary point without changing the closed result or reason.
- **Cache/public boundary:** `task_query.py:434` allocates a new holder only for a
  dual-fact query. A closed cache hit leaves it empty; a surface miss then computes
  normally. A surface cache hit returns the existing detached serialized result.
  Pair and contact stay in local compute options and never enter measurement or
  public fact dictionaries. `scene_cache.py:394` caches only serialized results,
  keyed by complete ordered mesh content and evaluator options.
- **Cancellation/publication:** the new checkpoint is outside the helper's
  `_DomainError` fallback catch; cancellation exceptions are not newly swallowed.
  Existing publish and completion checkpoints remain. Zero uses the existing
  contact descriptor, `_rounded_distance`, `_witness`, and `_publish_points`
  paths (`surface_proximity.py:566-599`), including finite world coordinates,
  absolute witness error, displacement error, and undefined zero direction.

Limits: this private API assumes the admitted preparation and mesh objects are
not mutated during the synchronous query. A reused real contact may differ from
the point chosen by nearest traversal, so targeted large-translation/publication
tests and the preregistered actual A/B gates still determine acceptance; source
review alone does not prove identical publication availability or timing.
