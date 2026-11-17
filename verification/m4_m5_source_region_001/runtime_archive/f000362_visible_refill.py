"""One transactional annotation from the current automatic candidate pool.

Raw arrays belong to this observation, not a cache or visibility certificate.
The original priority plan, measured risks and all action evidence stay intact.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from time import perf_counter as _monotonic_counter

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from .local_view import _glyph_survives
from .scene_rendering import (_display_snapshot_signature, _label_box,
                              _label_leader_endpoint, stable_object_label)
from .task_labels import task_display_label
from .refill_budget import refill_budget_for_quad_size


MAX_RAW_BYTES = 6 * 1024 * 1024
MAX_FALLBACK_CANDIDATES = 8
_AUTOMATIC_REASONS = frozenset({'known_penetration', 'near_exact_clearance',
                              'potential_neighbor_lower_bound'})
_REASON_RANK = {'known_penetration': 0, 'near_exact_clearance': 2,
                'potential_neighbor_lower_bound': 3}


def visible_refill_clock():
    """Bound monotonic clock, independent of attention's stdlib clock mocks."""
    return _monotonic_counter()


@dataclass(frozen=True, slots=True, eq=False)
class VisibleRefillProposal:
    """Private operation-local patch, not a certificate or wire payload."""

    tile: Image.Image
    tile_core: object
    view_index: int
    object_id: str
    source_canvas: Image.Image
    source_metadata: dict

    def __reduce_ex__(self, protocol):
        raise TypeError('Visible refill proposals cannot be serialized or persisted')


def _rgb_equal(first, second):
    """Exact uint8 RGB equality without a slow three-element axis reduction."""
    return ((first[..., 0] == second[..., 0]) & (first[..., 1] == second[..., 1])
            & (first[..., 2] == second[..., 2]))


def _boundary_pixels(color, owners, usable):
    boundary = np.zeros(owners.shape, dtype=bool)
    for first, second in (((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                          ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
        difference = color[first].astype(np.int16) - color[second].astype(np.int16)
        contrast = np.einsum('ijk,ijk->ij', difference, difference, dtype=np.int32) >= 24 ** 2
        edge = contrast & (owners[first] != owners[second]) & usable[first] & usable[second]
        boundary[first] |= edge
        boundary[second] |= edge
    return boundary


def _usable_pixels(color, picture, metadata, pixels=None):
    size = picture.width
    safe = np.zeros((size, size), dtype=bool)
    safe[17:size - 15, 1:size - 1] = True
    layout = metadata.get('label_layout', {})
    for field in ('navigation_reserved_region_px', 'frame_reserved_region_px'):
        region = layout.get(field)
        if region is not None:
            if (type(region) is not list or len(region) != 4
                    or any(type(value) is not int for value in region)):
                raise ValueError('Invalid current annotation reservation')
            left, top, right, bottom = region
            safe[max(0, top):min(size, bottom), max(0, left):min(size, right)] = False
    # This also excludes real NAV outlines/markers and every old annotation.
    safe &= _rgb_equal(np.asarray(picture) if pixels is None else pixels, color)
    return safe


def _owner_boundary_pixels(color, owners, usable, owner):
    """Evaluate this owner's real boundary within its exact bbox plus halo.

    Every usable owner pixel is inside the bbox; a one-pixel halo retains
    both sides of all four-neighbour edges used by the full-image test.
    """
    target = usable & (owners == owner)
    ys, xs = np.nonzero(target)
    boundary = np.zeros(owners.shape, dtype=bool)
    if len(xs):
        region = (slice(max(0, int(ys.min()) - 1), min(owners.shape[0], int(ys.max()) + 2)),
                  slice(max(0, int(xs.min()) - 1), min(owners.shape[1], int(xs.max()) + 2)))
        boundary[region] = _boundary_pixels(color[region], owners[region], usable[region])
    return boundary, target, ys, xs


def _candidate_source_pixels(picture, metadata, color, owners, owner):
    """Exact candidate-safe evidence without converting an unrelated frame.

    The bbox contains every current raw owner pixel; its one-pixel halo
    contains both neighbours of every possible qualifying owner boundary.
    Global UI coordinates are retained while comparing this cropped tile.
    """
    ys, xs = np.nonzero(owners == owner)
    if not len(xs):
        return None
    size = picture.width
    left, top = max(0, int(xs.min()) - 1), max(0, int(ys.min()) - 1)
    right, bottom = min(size, int(xs.max()) + 2), min(size, int(ys.max()) + 2)
    region = (slice(top, bottom), slice(left, right))
    cropped_color, cropped_owners = color[region], owners[region]
    pixels = np.asarray(picture.crop((left, top, right, bottom)))
    xx, yy = np.arange(left, right)[None, :], np.arange(top, bottom)[:, None]
    usable = (yy >= 17) & (yy < size - 15) & (xx >= 1) & (xx < size - 1)
    for field in ('navigation_reserved_region_px', 'frame_reserved_region_px'):
        reserved = metadata.get('label_layout', {}).get(field)
        if reserved is not None:
            if (type(reserved) is not list or len(reserved) != 4
                    or any(type(value) is not int for value in reserved)):
                raise ValueError('Invalid current annotation reservation')
            x0, y0, x1, y1 = reserved
            usable &= ~((xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1))
    usable &= _rgb_equal(pixels, cropped_color)
    target = usable & (cropped_owners == owner)
    return region, usable, target, int(np.count_nonzero(target))


def _boxed_glyph_survives(picture, row, alias):
    """Run the same exact glyph verifier on only its bounded delivered box."""
    box = row.get('label_box_px')
    if (type(box) is not list or len(box) != 4
            or any(type(value) is not int for value in box)):
        return False
    left, top, right, bottom = box
    if not (0 <= left < right < picture.width and 0 <= top < bottom < picture.height):
        return False
    cropped = picture.crop((left, top, right + 1, bottom + 1))
    translated = dict(row, label_box_px=[0, 0, right - left, bottom - top])
    return _glyph_survives(cropped, translated, alias)


def _changed_neighborhood_in_region(changed, changed_box, region):
    """Exact four-neighbour dilation cropped to a bounded evidence region.

    The native RGB difference already establishes that no changed pixel is
    outside changed_box. Shift that complete local mask into the requested
    global region, clipping each shift without wrapping at frame edges.
    """
    rows, columns = region
    x0, y0, x1, y1 = changed_box
    result = np.zeros((rows.stop - rows.start, columns.stop - columns.start), dtype=bool)
    for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
        left, right = max(columns.start, x0 + dx), min(columns.stop, x1 + dx)
        top, bottom = max(rows.start, y0 + dy), min(rows.stop, y1 + dy)
        if left < right and top < bottom:
            result[top - rows.start:bottom - rows.start,
                   left - columns.start:right - columns.start] |= changed[
                       top - y0 - dy:bottom - y0 - dy,
                       left - x0 - dx:right - x0 - dx]
    return result


def _best_source_by_upper_bound(candidates, qualify):
    """Select the exact best qualified (safe-count, index) lazily.

    Raw counts are operation-owned same-raster upper bounds, not claims from
    an external caller. A tie can prune only if its view index cannot win.
    """
    options = [(raw, index, source) for raw, index, source in candidates
               if type(raw) is int and raw >= 16]
    best_key, best_result = None, None
    for raw, index, source in sorted(options, key=lambda value: (-value[0], value[1])):
        if best_key is not None and (-raw, index) >= best_key:
            break
        qualified = qualify(source)
        if qualified is None:
            continue
        safe_count, result = qualified
        if type(safe_count) is not int or not 16 <= safe_count <= raw:
            raise ValueError('Current safe count exceeds its same-raster raw upper bound')
        key = (-safe_count, index)
        if best_key is None or key < best_key:
            best_key, best_result = key, result
    return best_result


class VisibleRefillCollector:
    """Borrow up to three current raw views, then consume them once.

    The caller admits only a default overview. Explicit query/focus/section
    admission belongs to the router; visual focus is also rejected here.
    Own incremental method costs are accumulated, excluding mandatory raster
    time between callbacks. The caller supplies measured pool/setup overhead.
    """

    def __init__(self, plan, ordered_candidate_pool, *, scene_fingerprint, setup_cost_ms=0.0,
                 quad_size=None):
        started = visible_refill_clock()
        self._budget = refill_budget_for_quad_size(quad_size)
        self._cost_ms = 0.0
        self._views = {}
        self._seen_drawn = set()
        self._retained = 0
        self._peak = 0
        self._snapshot = None
        self._mesh_ids = None
        self._disabled = None
        self._consumed = False
        self._issued_proposal = None
        self._plan = copy.deepcopy(plan)
        self._pool = ordered_candidate_pool if type(ordered_candidate_pool) is tuple else ()
        self._fingerprint = scene_fingerprint
        self._considered = 0
        if (type(setup_cost_ms) not in (int, float) or not math.isfinite(setup_cost_ms)
                or setup_cost_ms < 0):
            self._disabled = 'invalid_refill_setup_cost'
        else:
            self._cost_ms = float(setup_cost_ms)
        if (type(plan) is not dict or plan.get('scene_fingerprint') != scene_fingerprint
                or plan.get('execution_authority') is not False
                or plan.get('max_related_labels') != 2
                or plan.get('visual_focus_object_ids')):
            self._disabled = 'default_automatic_plan_required'
        selected = plan.get('related_object_ids') if type(plan) is dict else None
        if (type(selected) is not list or len(selected) > 2
                or any(type(identity) is not str or not identity for identity in selected)
                or len(set(selected)) != len(selected)):
            self._disabled = 'default_automatic_plan_required'
            selected = []
        self._selected = tuple(selected)
        if (not self._selected or len(self._pool) <= len(self._selected)) and self._disabled is None:
            self._disabled = 'no_fallback_candidate'
        if (type(ordered_candidate_pool) is not tuple or len(self._pool) > 254
                or any(type(row) is not tuple or len(row) != 2
                or type(row[0]) is not str or not row[0] or type(row[1]) is not str
                or row[1] not in _AUTOMATIC_REASONS
                for row in self._pool)):
            self._disabled = 'automatic_candidate_pool_required'
        elif self._disabled is None:
            candidate_ids = [identity for identity, _ in self._pool]
            reason_counts = {reason: sum(row[1] == reason for row in self._pool)
                             for reason in _AUTOMATIC_REASONS if any(row[1] == reason for row in self._pool)}
            if (len(set(candidate_ids)) != len(candidate_ids)
                    or self._pool != tuple(sorted(self._pool, key=lambda row: (_REASON_RANK[row[1]], row[0])))
                    or len(self._pool) != plan.get('related_candidate_count')
                    or reason_counts != plan.get('candidate_reason_counts')
                    or candidate_ids[:len(self._selected)] != list(self._selected)
                    or {identity: reason for identity, reason in self._pool[:len(self._selected)]}
                        != plan.get('related_reasons')):
                self._disabled = 'candidate_pool_priority_binding_changed'
        self._cost_ms += max(0., (visible_refill_clock() - started) * 1000.)
        if self._cost_ms > self._budget.incremental_ms:
            self._disabled = 'refill_setup_budget_exceeded'

    def _release(self):
        self._views.clear()
        self._retained = 0

    def _disable(self, reason):
        self._disabled = reason
        self._release()

    def observe_view(self, view_index, picture, metadata, meshes, color, depth, owners):
        """Private end-of-render observer; takes no raw array copies."""
        started = visible_refill_clock()
        try:
            if self._disabled or self._consumed or view_index not in (0, 1, 2):
                return
            if self._cost_ms >= self._budget.incremental_ms:
                return self._disable('refill_capture_budget_exceeded')
            self._seen_drawn.update(row['object_id'] for row in metadata.get('projected_labels', ()))
            if set(self._selected).issubset(self._seen_drawn):
                return self._disable('priority_selected_already_drawn')
            size = picture.width
            if self._budget.quad_size is not None and size != self._budget.quad_size:
                return self._disable('current_refill_resolution_changed')
            if (view_index in self._views or size < 128 or picture.mode != 'RGB'
                    or picture.size != (size, size) or color.shape != (size, size, 3)
                    or color.dtype != np.uint8 or owners.shape != (size, size)
                    or owners.dtype != np.int32 or depth.shape != (size, size)
                    or int(owners.min()) < -1 or int(owners.max()) >= len(meshes)
                    or np.any((owners >= 0) & ~np.isfinite(depth))):
                return self._disable('invalid_current_raw_view')
            needed = color.nbytes + owners.nbytes
            if needed > MAX_RAW_BYTES - self._retained:
                return self._disable('refill_raw_retention_limit')
            ids = tuple(mesh.object_id for mesh in meshes)
            if (len(set(ids)) != len(ids)
                    or not set(self._plan['core_object_ids']).issubset(ids)
                    or any(identity not in ids for identity, _ in self._pool)):
                return self._disable('current_display_namespace_changed')
            if self._snapshot is None:
                self._snapshot = _display_snapshot_signature(meshes)
                self._mesh_ids = ids
            elif ids != self._mesh_ids:
                return self._disable('current_display_namespace_changed')
            color.setflags(write=False)
            owners.setflags(write=False)
            picture.readonly = 1
            self._views[view_index] = (picture, picture.im, copy.deepcopy(metadata), color, owners)
            self._retained += needed
            self._peak = max(self._peak, self._retained)
        except Exception:
            self._disable('refill_capture_unavailable')
        finally:
            self._cost_ms += max(0., (visible_refill_clock() - started) * 1000.)
            if self._disabled is None and self._cost_ms > self._budget.incremental_ms:
                self._disable('refill_capture_budget_exceeded')

    def claim_proposal(self, proposal, *, canvas, metadata):
        """Consume this collector's issued patch once, rejecting ordinary COW.

        Identity and read-only core checks bind a trusted internal operation;
        they are not cryptographic protection against arbitrary Python code.
        """
        issued = self._issued_proposal
        self._issued_proposal = None
        try:
            size = metadata.get('quad_size') if type(metadata) is dict else None
            return bool(type(proposal) is VisibleRefillProposal and proposal is issued
                and proposal.source_canvas is canvas and proposal.source_metadata is metadata
                and type(size) is int and size >= 128
                and isinstance(canvas, Image.Image) and canvas.mode == 'RGB'
                and canvas.size == (size * 2, size * 2)
                and type(proposal.view_index) is int and 0 <= proposal.view_index < 3
                and type(proposal.object_id) is str and bool(proposal.object_id)
                and isinstance(proposal.tile, Image.Image) and proposal.tile.mode == 'RGB'
                and proposal.tile.size == (size, size) and proposal.tile.readonly
                and proposal.tile.im is proposal.tile_core)
        except Exception:
            return False

    def finish(self, canvas, metadata, meshes, *, scene_fingerprint, remaining_budget_ms,
               proposal_only=False):
        """Consume a canvas using independent incremental and shared windows.

        Setup/collection was paid before this entry. It counts against the
        cumulative local limit, while only time after entry consumes the
        caller's remaining shared allowance. The router checks both complete
        windows again after claiming and composing a proposal.
        """
        started = visible_refill_clock()
        receipt = {'applied': False, 'status': 'skipped', 'reason': 'not_attempted',
            'attempted': False, 'candidate_raster_count': 0, 'additional_cost_ms': self._cost_ms,
            'budget_ms': self._budget.incremental_ms, 'budget_policy': self._budget.descriptor(),
            'priority_selected_object_ids': list(self._selected),
            'incremental_cost_before_finish_ms': self._cost_ms, 'finish_elapsed_ms': 0.0,
            'shared_remaining_budget_ms': None, 'budget_failure_scope': None,
            'budget_checkpoint': None, 'budget_exceeded': [],
            'actual_base_drawn_selected_object_ids': [], 'donor_object_id': None,
            'donor_reason': None, 'new_readable_object_ids': [], 'candidate_count': 0,
            'raw_retained_bytes_peak': self._peak, 'raw_retention_cap_bytes': MAX_RAW_BYTES,
            'retained_bytes_peak': self._peak,
            'retained_storage_scope': 'raw_color_owners_only_not_total_heap_or_RSS',
            'picture_reference_payload_bytes_estimate': sum(value[0].width * value[0].height * 3
                                                          for value in self._views.values()),
            'retained_metadata_view_count': len(self._views),
            'execution_authority': False, 'model_quality_gain_proven': False,
            'cost_scope': 'pool_setup_raw_collection_qualification_annotation_composition_excludes_PNG',
            'deadline_scope': 'cooperative_checkpoints_not_interruptible_kernel_deadline'}

        def account():
            # One clock sample attributes the two windows at the same point.
            duration = max(0., (visible_refill_clock() - started) * 1000.)
            receipt.update(finish_elapsed_ms=duration,
                           additional_cost_ms=self._cost_ms + duration)

        def budget_failure(exceeded, checkpoint, *, invalid=False):
            receipt.update(budget_failure_scope=('invalid' if invalid else
                'both' if len(exceeded) == 2 else exceeded[0]),
                budget_checkpoint=checkpoint, budget_exceeded=list(exceeded))

        def stop(reason, status='skipped'):
            self._issued_proposal = None
            self._release()
            account()
            receipt.update(reason=reason, status=status, candidate_count=self._considered)
            if receipt['budget_failure_scope'] is None and reason in (
                    'refill_setup_budget_exceeded', 'refill_capture_budget_exceeded'):
                budget_failure(['local'], 'setup' if reason == 'refill_setup_budget_exceeded'
                               else 'capture')
            return canvas, metadata, receipt

        def late(checkpoint):
            account()
            exceeded = []
            if receipt['additional_cost_ms'] > self._budget.incremental_ms:
                exceeded.append('local')
            if receipt['finish_elapsed_ms'] > receipt['shared_remaining_budget_ms']:
                exceeded.append('shared')
            if exceeded:
                budget_failure(exceeded, checkpoint)
            return bool(exceeded)

        if self._consumed:
            return stop('refill_context_already_consumed', 'unavailable')
        self._consumed = True
        try:
            if type(proposal_only) is not bool:
                return stop('invalid_visible_refill_proposal_mode', 'unavailable')
            if proposal_only:
                receipt['cost_scope'] = ('pool_setup_raw_collection_qualification_annotation_proposal_'
                    'excludes_router_claim_canvas_composition_and_PNG')
            if self._disabled:
                return stop(self._disabled)
            try:
                remaining = (float(remaining_budget_ms)
                    if type(remaining_budget_ms) in (int, float) else float('nan'))
            except (OverflowError, ValueError):
                remaining = float('nan')
            if not math.isfinite(remaining) or remaining < 0:
                budget_failure([], 'before_qualification', invalid=True)
                return stop('shared_refill_budget_unavailable')
            receipt['shared_remaining_budget_ms'] = remaining
            if remaining == 0:
                budget_failure(['shared'], 'before_qualification')
                return stop('shared_refill_budget_unavailable')
            if late('before_qualification'):
                return stop('refill_budget_exhausted_before_qualification', 'hold')
            if (scene_fingerprint != self._fingerprint or type(metadata) is not dict
                    or metadata.get('task_labels') != self._plan
                    or metadata.get('raster_schedule', {}).get('canvas_complete', True) is not True
                    or type(metadata.get('views')) is not list or len(metadata['views']) != 4
                    or any(view.get('render_status') == 'deferred' for view in metadata['views'])):
                return stop('current_refill_binding_changed', 'unavailable')
            size = metadata.get('quad_size')
            if (type(size) is not int or size < 128 or not isinstance(canvas, Image.Image)
                    or self._budget.quad_size is not None and size != self._budget.quad_size
                    or canvas.mode != 'RGB' or canvas.size != (2 * size, 2 * size)
                    or metadata.get('canvas_size') != list(canvas.size)
                    or metadata.get('supplemental_views') or metadata.get('diagnostic_panel')):
                return stop('complete_original_canvas_required', 'unavailable')
            drawn = {row['object_id'] for view in metadata['views'] for row in view.get('projected_labels', ())}
            drawn_selected = set(self._selected) & drawn
            receipt['actual_base_drawn_selected_object_ids'] = sorted(drawn_selected)
            donors = [identity for identity in self._selected if identity not in drawn]
            if not donors or len(drawn_selected) + 1 > self._plan['max_related_labels']:
                return stop('priority_selected_already_drawn')
            if (self._snapshot is None or not self._views
                    or tuple(mesh.object_id for mesh in meshes) != self._mesh_ids
                    or _display_snapshot_signature(meshes) != self._snapshot):
                return stop('current_display_snapshot_changed', 'unavailable')
            by_id = {identity: index for index, identity in enumerate(self._mesh_ids)}
            if len(by_id) != len(self._mesh_ids) or any(identity not in by_id for identity, _ in self._pool):
                return stop('current_display_namespace_changed', 'unavailable')
            source_headers, source_cache = [], {}
            for index, (picture, core, view, color, owners) in sorted(self._views.items()):
                if (picture.im is not core or not picture.readonly or picture.size != (size, size)
                        or metadata['views'][index] != view):
                    return stop('current_source_view_changed', 'unavailable')
                source_headers.append((index, picture, view, color, owners))
            pool = [(identity, reason) for identity, reason in self._pool
                    if identity not in self._selected][:MAX_FALLBACK_CANDIDATES]
            candidate = None
            for identity, reason in pool:
                self._considered += 1
                donor = next((value for value in donors if self._plan['related_reasons'][value] == reason), None)
                if identity in drawn or donor is None:
                    continue
                owner = by_id[identity]
                def qualify_source(source):
                    index, picture, view, color, owners = source
                    data = source_cache.get((index, owner))
                    if data is None:
                        evidence = _candidate_source_pixels(picture, view, color, owners, owner)
                        if evidence is None:
                            return None
                        region, cropped_usable, cropped_target, count = evidence
                        data = (index, picture, view, color, owners, region,
                                cropped_usable, cropped_target, count)
                        source_cache[(index, owner)] = data
                    raw_count = view.get('object_visible_pixels', {}).get(identity, 0)
                    if type(raw_count) is not int or data[8] > raw_count:
                        raise ValueError('Current safe count exceeds its same-raster raw upper bound')
                    if data[8] < 16:
                        return None
                    region, cropped_usable = data[5], data[6]
                    boundary = _boundary_pixels(data[3][region], data[4][region], cropped_usable)
                    if np.count_nonzero(boundary & (data[4][region] == owner)) >= 4:
                        return data[8], (data, boundary)
                    return None

                qualified = _best_source_by_upper_bound([
                    (source[2].get('object_visible_pixels', {}).get(identity, 0), source[0], source)
                    for source in source_headers], qualify_source)
                if qualified is not None:
                    data, boundary = qualified
                    candidate = (identity, reason, donor, owner, data, boundary)
                if candidate is not None:
                    break
                if late('during_qualification'):
                    return stop('refill_budget_exceeded_during_qualification', 'hold')
            if candidate is None:
                return stop('no_same_priority_readable_candidate')
            identity, reason, donor, owner, data, cropped_boundary = candidate
            index, picture, view, color, owners, source_region, _, cropped_target, safe_count = data
            receipt.update(attempted=True, donor_object_id=donor, donor_reason=reason,
                candidate_object_id=identity, source_view_index=index,
                candidate_count=self._considered)
            if late('before_annotation'):
                return stop('refill_budget_exceeded_before_annotation', 'hold')
            offset = ((index % 2) * size, (index // 2) * size)
            current_tile = canvas.crop((offset[0], offset[1], offset[0] + size, offset[1] + size))
            if current_tile.tobytes() != picture.tobytes():
                return stop('current_source_pixels_changed', 'unavailable')
            before = np.asarray(picture)
            usable = _usable_pixels(color, picture, view, before)
            counts = np.bincount(owners[usable & (owners >= 0)], minlength=len(meshes))
            if int(counts[owner]) != safe_count:
                return stop('current_candidate_surface_changed', 'unavailable')
            ys, xs = np.nonzero(cropped_target)
            ys, xs = ys + source_region[0].start, xs + source_region[1].start
            center = (float(xs.mean()), float(ys.mean()))
            nearest = int(np.argmin((xs - center[0]) ** 2 + (ys - center[1]) ** 2))
            anchor = [int(xs[nearest]), int(ys[nearest])]
            original_rows = view.get('projected_labels', ())
            occupied = [tuple(row['label_box_px']) for row in original_rows]
            core_indices = tuple(by_id[value] for value in self._plan['core_object_ids'])
            alias = task_display_label(identity, self._plan)
            output_tile = picture.copy()
            draw = ImageDraw.Draw(output_tile)
            reserved = view.get('label_layout', {}).get('navigation_reserved_region_px')
            # Core surfaces are forbidden ink. A very large layout penalty
            # selects any legal zero-core option before final exact checking.
            penalty = (owners >= 0).astype(np.float32)
            penalty[(owners == core_indices[0]) | (owners == core_indices[1])] = 1e9
            box = _label_box(draw, alias, anchor, size, occupied, penalty,
                surface_bounds=(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
                owners=owners, protected_owner_indices=core_indices,
                protected_visible_counts=tuple(max(1, int(counts[value])) for value in core_indices),
                caption_reserved_region=reserved)
            if box is None:
                return stop('no_nonoverlapping_refill_box')
            endpoint = _label_leader_endpoint(anchor, box)
            draw.line((anchor[0], anchor[1], endpoint[0], endpoint[1]), fill=(245, 218, 135), width=1)
            # Existing boxes retain their exact delivered pixels, even when a
            # new leader passes behind one. No old label is relaid out.
            for left, top, right, bottom in occupied:
                region = (left, top, right + 1, bottom + 1)
                output_tile.paste(picture.crop(region), (left, top))
            draw = ImageDraw.Draw(output_tile)
            draw.rectangle(box, fill=(18, 22, 30), outline=(150, 145, 110))
            draw.text((box[0] + 3, box[1]), alias, fill=(255, 245, 180))
            row = {'object_id': identity, 'mark_label': meshes[owner].mark_label,
                'stable_label': stable_object_label(identity), 'display_label': alias,
                'projected_center_px': anchor, 'label_box_px': list(box),
                'leader_endpoint_px': list(endpoint), 'surface_visible_pixels': int(counts[owner]),
                'anchor_source': 'current_full_scene_depth_winner',
                'display_source': 'visible_candidate_refill'}
            # A native whole-image difference proves where *all* actual ink
            # changed, then only that exact region needs an RGB conversion.
            difference = ImageChops.difference(picture, output_tile)
            changed_box = difference.getbbox()
            if changed_box is None:
                return stop('refill_annotation_unchanged', 'hold')
            left, top, right, bottom = changed_box
            changed_region = (slice(top, bottom), slice(left, right))
            changed_local = np.any(np.asarray(difference.crop(changed_box)) != 0, axis=2)
            changed_owners = owners[changed_region]
            core_changed = int(np.count_nonzero(changed_local & (
                (changed_owners == core_indices[0]) | (changed_owners == core_indices[1]))))
            for box_left, box_top, box_right, box_bottom in occupied:
                overlap_left, overlap_right = max(left, box_left), min(right, box_right + 1)
                overlap_top, overlap_bottom = max(top, box_top), min(bottom, box_bottom + 1)
                if (overlap_left < overlap_right and overlap_top < overlap_bottom
                        and np.any(changed_local[overlap_top - top:overlap_bottom - top,
                                                 overlap_left - left:overlap_right - left])):
                    return stop('original_label_pixels_changed', 'hold')
            if core_changed:
                receipt['core_new_changed_pixels'] = core_changed
                return stop('refill_would_cover_core_surface', 'hold')
            # Exclude every boundary touching a changed pixel, conservatively
            # keeping only real original two-sided contrasting geometry. The
            # source bbox plus halo contains every qualifying owner edge.
            near_change = _changed_neighborhood_in_region(changed_local, changed_box, source_region)
            owner_boundary = cropped_boundary & (owners[source_region] == owner)
            final_pixels = int(counts[owner]) - int(np.count_nonzero(
                changed_local & usable[changed_region] & (changed_owners == owner)))
            final_edges = int(np.count_nonzero(owner_boundary & ~near_change))
            glyph = _boxed_glyph_survives(output_tile, row, alias)
            receipt['readability'] = {'raw_safe_surface_pixels': int(counts[owner]),
                'raw_contrasting_boundary_pixels': int(np.count_nonzero(owner_boundary)),
                'final_unmodified_surface_pixels': final_pixels,
                'final_unmodified_boundary_pixels': final_edges,
                'anchor_exact_owner': bool(owners[anchor[1], anchor[0]] == owner),
                'complete_final_glyph': glyph}
            if final_pixels < 16 or final_edges < 4 or not glyph:
                return stop('refill_readability_not_delivered', 'hold')
            if late('after_annotation'):
                return stop('refill_budget_exceeded_after_annotation', 'hold')
            # Only this view is mutated. Copy its complete subtree while
            # sharing the other read-only facts, cameras and CONTACT view.
            visual = dict(metadata)
            visual['views'] = list(metadata['views'])
            visual['views'][index] = copy.deepcopy(metadata['views'][index])
            added_view = visual['views'][index]
            added_view['projected_labels'].append(row)
            added_view['label_layout']['displayed_label_count'] = len(added_view['projected_labels'])
            layout = added_view['label_layout']
            prior_omission = next((value for value in layout['omitted_objects']
                                   if value['object_id'] == identity), None)
            # Every current unselected, >=16-pixel source candidate was omitted
            # as outside focus, including entries beyond the diagnostic cap.
            omission_reason = prior_omission['reason'] if prior_omission else 'outside_task_label_focus'
            if (layout['omitted_object_count'] < 1
                    or layout['omitted_reason_counts'].get(omission_reason, 0) < 1):
                return stop('current_candidate_omission_binding_changed', 'unavailable')
            layout['omitted_object_count'] -= 1
            layout['omitted_reason_counts'][omission_reason] -= 1
            if layout['omitted_reason_counts'][omission_reason] == 0:
                del layout['omitted_reason_counts'][omission_reason]
            layout['omitted_objects'] = [value for value in layout['omitted_objects']
                                         if value['object_id'] != identity]
            layout['omitted_objects_truncated'] = layout['omitted_object_count'] - len(layout['omitted_objects'])
            receipt['prior_candidate_omission'] = {'object_id': identity, 'reason': omission_reason,
                                                   'scope': 'original_pre_refill_history'}
            added_view['label_layout']['visible_candidate_refill'] = {
                'object_id': identity, 'donor_object_id': donor, 'reason': reason,
                'scope': 'add_only_display_of_same_rank_existing_evidence', 'execution_authority': False}
            # Only the verified changed pixels can alter this same-raster
            # statistic; retain its exact original count everywhere else.
            changed_owned = owners[changed_region][changed_local] >= 0
            original_rgb = color[changed_region][changed_local]
            old_equal = _rgb_equal(before[changed_region][changed_local], original_rgb)
            after_local = np.asarray(output_tile.crop(changed_box))
            new_equal = _rgb_equal(after_local[changed_local], original_rgb)
            added_view['geometry_pixels_unchanged_by_annotations'] = (
                view['geometry_pixels_unchanged_by_annotations']
                - int(np.count_nonzero(changed_owned & old_equal))
                + int(np.count_nonzero(changed_owned & new_equal)))
            if not proposal_only:
                output = canvas.copy()
                output.paste(output_tile, offset)
            receipt.update(candidate_readable_object_ids=[identity],
                core_new_changed_pixels=0,
                new_changed_pixels=int(np.count_nonzero(changed_local)),
                new_changed_foreground_pixels=int(np.count_nonzero(changed_owned)),
                actual_delivered_default_related_count=len(drawn_selected) + (not proposal_only))
            if late('before_commit'):
                return stop('refill_budget_exceeded_before_commit', 'hold')
            self._release()
            if late('during_release'):
                return stop('refill_budget_exceeded_during_release', 'hold')
            if proposal_only:
                output_tile.readonly = 1
                output = VisibleRefillProposal(output_tile, output_tile.im, index, identity, canvas, metadata)
                self._issued_proposal = output
                if late('before_proposal_commit'):
                    return stop('refill_budget_exceeded_before_proposal_commit', 'hold')
            if proposal_only:
                receipt.update(applied=False, status='proposal_ready', reason='qualified_single_view_proposal',
                    new_readable_object_ids=[], candidate_readable_object_ids=[identity])
            else:
                receipt.update(applied=True, status='applied', reason='one_same_priority_identity_added',
                    new_readable_object_ids=[identity])
            return output, visual, receipt
        except Exception:
            return stop('visible_candidate_refill_unavailable', 'unavailable')
