"""Trace the unchanged P2 answer to actual wire data and current evaluated geometry."""

import argparse
import base64
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from itertools import accumulate
import json
from pathlib import Path
import runpy
import sys


ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
SOURCE = 'eaccba2ec88abc035c62841a765f99ecae5f50e34dd8e7867b09dc17cb6d9dc9'
INSTALL = Path('D:/he_m1_target_observation_first_image_path_windows_001/staging/install/PRODUCT_RUN_BINDING.json')
TARGET, OTHER = 'M09', 'M03'
PAIR = {TARGET, OTHER}
PRODUCER_FIELDS = {'runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(data):
    return sha256(data).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode())


def packed_rows(table):
    return [dict(zip(table['columns'], row, strict=True)) for row in table['rows']]


class Review:
    def __init__(self, repo, slot, install):
        self.repo, self.slot = repo, slot.resolve()
        self.prior = repo / 'verification/perf050_readonly_product_transfer_001'
        self.files = set()
        self.install = self.json(install)
        sys.path.insert(0, self.install['dependency_root'])
        sys.path.insert(0, str(self.prior / 'checks'))
        import evidence
        self.evidence = evidence
        self.old_review = runpy.run_path(str(self.prior / 'checks/review.py'))
        self.oracle = evidence.ORACLE
        self.truth = self.json(self.prior / 'truth/TRUTH.json')
        self.region = self.truth['region']
        self.older = runpy.run_path(str(self.oracle['OLDER'] / 'oracle.py'))
        _, self.exact = self.older['helpers']()
        self.decoder = runpy.run_path(str(repo / 'verification/m4_cross_scale_discovery_001/oracle/check_saved.py'))
        self.calls, self.raw_captures, self.errors = [], None, []
        self.frame_paths = []
        self.final = self.old_review['P3']

    def bytes(self, path, expected=None, in_slot=False):
        path = Path(path)
        require(not in_slot or path.is_absolute() and path.resolve(strict=True).is_relative_to(self.slot),
                'original_path_outside_slot')
        self.files.add(path)
        data = path.read_bytes()
        require(expected is None or digest(data) == expected, 'original_bytes_digest_changed')
        return data

    def json(self, path, expected=None, in_slot=False):
        return json.loads(self.bytes(path, expected, in_slot))

    def pin(self, path):
        path = Path(path)
        data = self.bytes(path)
        return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}

    def check_source(self):
        self.status = self.json(self.slot / 'SLOT_RESULT.json')
        published = self.json(self.slot / 'SLOT_PUBLICATION.json')
        require(published['result_sha256'] == self.pin(self.slot / 'SLOT_RESULT.json')['sha256'],
                'unbound_publication_result')
        self.closed = self.status['closure_verification']['passed'] and (
            self.status['closure_verification']['status'] == 'ready_closed'
            and self.status['independent_before_after']['passed'])
        require(self.closed and self.status['asset_sha256'] == ASSET, 'slot_source_or_closure_invalid')
        require(digest(self.bytes(self.slot / 'native/input.blend')) == ASSET, 'slot_asset_changed')
        self.terminal = self.json(self.slot / 'TERMINAL_SOURCE.json', self.status['terminal_source']['sha256'], True)
        initial = self.json(self.slot / 'initial_capture/TERMINAL_SOURCE.json', self.status['initial_source']['sha256'], True)
        require(initial['objects'] == self.terminal['objects']
                and initial['display_object_mask'] == self.terminal['display_object_mask']
                and self.terminal['source']['asset_sha256'] == ASSET, 'before_after_geometry_or_display_differ')
        self.meshes = self.evidence.same_geometry(None, self.terminal)
        self.full = sorted(self.meshes.values(), key=lambda item: item['name'])
        self.by_name = {row['name']: row for row in self.terminal['objects']}
        self.by_id = {row['object_id']: row for row in self.terminal['objects']}
        require(self.truth['passed'] and self.terminal['source']['scale_length'] == 1, 'unsupported_truth_or_units')
        require(self.install['source_sha256'] == SOURCE or self.slot.parent.parent.name in {
            'he_perf050_readonly_product_transfer_001', 'he_perf050_source_region_final_image_p3'},
            'unexpected_candidate_source')

    def collect_calls(self):
        archive = self.json(self.slot / 'consumer/BUSINESS_SOURCE_BINDING.json')
        stdout = self.slot / 'consumer/stdout.raw.bin'
        self.files.add(stdout)
        raw_items = {row['item']['id']: row['item'] for row in self.final['lines'](stdout)
                     if row.get('type') == 'item.completed' and row.get('item', {}).get('type') == 'mcp_tool_call'}
        by_attempt = defaultdict(list)
        for rx in (self.slot / 'consumer/attachments').glob('bridge_*/*/RX.bin'):
            receipt = self.json(rx.with_name('RECEIPT.json'))
            if receipt.get('attempt'):
                by_attempt[receipt['attempt']].append(rx)
        for contract in sorted(archive['result_contracts'], key=lambda row: row['attempt']):
            attempt = contract['attempt']
            try:
                rx, = by_attempt[attempt]
                request = self.json(rx.with_name('TX.bin'), contract['TX_sha256'], True)
                response = self.json(rx, contract['RX_sha256'], True)
                owner = self.slot / 'owner' / f'tool_{attempt:02d}'
                cli = raw_items[contract['caller_identity']['CLI_event_item_id']]
                require(contract['matched'] and contract['reason'] == 'content_and_envelope_match'
                        and request == self.json(owner / 'REQUEST.json')
                        and response == self.json(owner / 'RESPONSE.json')
                        and request['params']['name'] == cli['tool']
                        and request['params']['arguments'] == cli['arguments']
                        and response['result']['content'] == cli['result']['content'],
                        'attempt_cli_owner_wire_mismatch')
                result = response['result']
                texts, images = [], []
                for index, content in enumerate(result['content']):
                    if content['type'] == 'text':
                        try:
                            texts.append(json.loads(content['text']))
                        except json.JSONDecodeError:
                            texts.append(content['text'])
                    elif content['type'] == 'image':
                        require(content['mimeType'] == 'image/png', 'image_content_mime_mismatch')
                        image = base64.b64decode(content['data'], validate=True)
                        images.append((index, image))
                require(len(images) == contract['CLI_images'], 'cli_image_count_mismatch')
                row = {'attempt': attempt, 'owner': owner, 'tool': cli['tool'], 'args': cli['arguments'],
                       'cli_id': cli['id'], 'cli_received_ns': contract['CLI_received_ns'], 'rx': self.pin(rx),
                       'images': images, 'texts': texts, 'error': result['isError']}
                if (owner / 'PRODUCT_RECEIPT.json').is_file():
                    product = self.json(owner / 'PRODUCT_RECEIPT.json')
                    wire = self.slot / 'mcp' / f"rpc_{product['receipt']['index']:02d}"
                    require(self.json(wire / 'RX.bin', product['receipt']['RX_sha256'], True)['result']
                            == self.json(owner / 'PRODUCT_RESPONSE.json')['result'] == result
                            and self.json(wire / 'TX.bin') == self.json(owner / 'PRODUCT_REQUEST.json')
                            and self.json(wire / 'TX.bin')['params']['arguments'] == cli['arguments'],
                            'candidate_inner_actual_tool_delivery_unbound')
                    saved = product.get('producer_archive')
                    if saved:
                        row['producer'] = self.json(saved['path'], saved['sha256'], True)
                        row['producer_pin'] = self.pin(saved['path'])
                self.calls.append(row)
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.errors.append({'attempt': attempt, 'error': str(error)})

    def native_sources(self):
        if self.raw_captures is None:
            audit = self.decoder['Audit']()
            self.raw_captures, self.commands = self.decoder['decode_captures'](self.slot, self.install, audit)
            for item in self.commands:
                self.files.update((self.slot / 'native/WIRE' / f"{item['wire_sequence']:03d}").glob('*.bin'))
        return self.raw_captures

    def current_product(self, binding):
        captures = [
            capture for capture in self.native_sources()
            if capture['revision'] == binding['scene_revision']
            and capture['capture_state'] == binding['capture_state']
            and capture['host_identity']['document_epoch'] == binding['document_epoch']
            and capture['host_identity']['capture_scope'] == binding['capture_scope']
        ]
        require(captures, 'no_independently_bound_product_capture')
        capture = captures[0]
        self.evidence.same_geometry(capture, self.terminal)
        ordered = [{
            'object_index': index, 'host_id': mesh['object_id'], 'object_name': mesh['name'],
            'instance_id': capture['host_identity']['object_instances'][mesh['object_id']],
        } for index, mesh in enumerate(capture['meshes'])]
        require(ordered == binding['objects']
                and binding['runtime_source_sha256'] == self.install['source_sha256']
                and binding['source_status'] == 'loaded_generation'
                and binding['coordinate_frame'] == 'world' and binding['unit'] == 'm'
                and all(self.by_id[row['host_id']]['instance_id'] == row['instance_id'] for row in ordered),
                'product_current_source_or_roster_mismatch')
        if binding['capture_scope'] == 'target_observation_meshes':
            target = capture['observation_target']
            complete = target['full_scene_identity']['object_instances']
            require(complete == {key: item['instance_id'] for key, item in self.by_id.items()}
                    and set(target['retained_object_ids']) | set(target['excluded_object_ids']) == set(complete),
                    'target_scope_not_bound_to_full_current_scene')
        return capture

    def product_frame(self, log, calls):
        bound = [row for row in calls if row.get('producer') and any(
            frame['image_ref'] == log['ref'] for frame in row['producer'].get('frames', []))]
        require(bound, 'frame_producer_not_in_actual_delivery')
        packet = bound[0]['producer']
        producer, = (frame for frame in packet['frames'] if frame['image_ref'] == log['ref'])
        parent = packet['binding']
        binding = next((item['binding'] for item in packet.get('scopes', [])
                        if item['scope_id'] == log['scope_id']), parent)
        self.current_product(parent)
        require(log['producer'] == producer and log['source_ref'] == 'product-binding:' + binding['binding_sha256']
                and producer['host_binding_sha256'] == binding['binding_sha256']
                and producer['frame_identity'] == log['frame_identity']
                and producer['pose'] == log['pose'] and producer['image_sha256'] == log['PNG_sha256']
                and producer['arrays_sha256'] == log['NPZ_sha256']
                and str(Path(producer['image_path']).resolve()) == log['PNG']
                and str(Path(producer['arrays_path']).resolve()) == log['NPZ'],
                'frame_producer_pose_digest_or_path_mismatch')
        if binding['schema'] == 'active-observation-host-source-v1':
            base = {key: val for key, val in binding.items() if key not in PRODUCER_FIELDS | {'binding_sha256'}}
            require(fingerprint(base) == binding['binding_sha256'], 'ordinary_product_binding_digest_failed')
        rows = binding['objects']
        require(log['object_ids'] == [row['host_id'] for row in rows]
                and log['object_instance_ids'] == [row['instance_id'] for row in rows]
                and log['object_names'] == [row['object_name'] for row in rows],
                'frame_producer_source_mismatch')
        return binding['capture_scope']

    def native_frame(self, log, sources):
        row, = [source for source in sources if source['source_ref'] == log['source_ref']]
        source = self.json(row['path'], row['sha256'], True)
        require(source['source']['asset_sha256'] == ASSET, 'native_raster_wrong_current_asset')
        for mesh in source['objects']:
            terminal = self.by_id[mesh['object_id']]
            require(mesh['name'] == terminal['name'] and mesh['instance_id'] == terminal['instance_id']
                    and mesh['vertices'] == terminal['evaluated']['vertices_world_m']
                    and mesh['triangles'] == terminal['evaluated']['triangles']
                    and mesh['visible_get'] == terminal['visible_get'], 'native_raster_geometry_display_changed')
        require(set(log['object_ids']) <= {mesh['object_id'] for mesh in source['objects']},
                'native_raster_scope_unbound')
        return 'complete_bounded_native_geometry'

    def frame_proof(self, log, raw, arrays):
        import numpy as np
        from PIL import Image

        scope = [self.by_id[host] for host in log['object_ids']]
        offsets = [0, *accumulate(len(row['evaluated']['triangles']) for row in scope)]
        require(log['object_names'] == [row['name'] for row in scope]
                and log['object_instance_ids'] == [row['instance_id'] for row in scope]
                and len(scope) == len(set(log['object_ids']))
                and log['source_face_offsets'] == offsets
                and log['display_object_mask'] == [row['visible_get'] for row in scope],
                'frame_identity_offsets_or_display_mismatch')
        if TARGET not in log['object_names']:
            return {'qualifies': False, 'reason': 'target_absent_from_frame_source'}
        direction, pose = log['direction_rational'], log['pose']
        require(direction == pose['direction_rational'] and log['view'] == pose['name'],
                'raster_camera_pose_direction_mismatch')
        with np.load(BytesIO(arrays), allow_pickle=False) as vals, Image.open(BytesIO(raw)) as image:
            require(image.format == 'PNG' and image.size == (512, 512) and
                    np.array_equal(np.asarray(image.convert('RGB')), vals['color'][:, :, :3]),
                    'original_image_is_not_same_RGB_buffer')
            if 'display_object_mask' in vals:
                require(vals['display_object_mask'].tolist() == log['display_object_mask'],
                        'frame_buffer_display_mismatch')
            if 'face_patch_offsets' in vals:
                require(vals['face_patch_offsets'].tolist() == offsets, 'frame_array_offsets_changed')
            surface, boundary, corners = self.evidence.FORMAL['pixels'](log, self.region, {'objects': scope}, vals)
            index = log['object_names'].index(TARGET)
            ids, owners = vals['triangle_ids'], vals['owners']
            found = self.evidence.PIXELS['split_pixels'](vals['color'][:, :, :3], owners, ids - offsets[index],
                                                         self.region['source_triangle_indices'], index)
            require((surface, boundary) == (found['surface'], found['contrast']), 'independent_pixel_counts_differ')
            occupied = owners >= 0
            require(np.all(owners[occupied] < len(scope)) and np.all(ids[~occupied] == -1)
                    and np.isfinite(vals['depth'][occupied]).all(), 'frame_owner_or_depth_domain_invalid')
            for owner, (low, high) in enumerate(zip(offsets, offsets[1:])):
                require(np.all((ids[owners == owner] >= low) & (ids[owners == owner] < high)),
                        'frame_triangle_wrong_object_domain')
            mask = (owners == index) & np.isin(ids - offsets[index], self.region['source_triangle_indices'])
            clear_edges = not (mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())
        in_frame = bool(clear_edges and self.evidence.FORMAL['in_frame'](pose, corners, direction))
        front = self.oracle['dot'](self.region['plane_normal_integer'], direction) > 0
        blockers = self.older['occluders'](self.full, self.region, direction, self.exact) if front else None
        enough = surface >= 16 and boundary >= 4 and found['visible_source_ids'] == self.region['source_triangle_indices']
        return {'qualifies': front and blockers == [] and in_frame and enough, 'direction_rational': direction,
                'full_scene_checked_objects': len(self.full), 'scope_objects': len(scope),
                'source_triangles': found['visible_source_ids'], 'all_corners_in_frame': in_frame,
                'front_facing': front, 'full_scene_positive_area_blockers': blockers,
                'surface_pixels': surface, 'contrasting_boundary_pixels': boundary}

    def frames(self):
        ledger = self.json(self.slot / 'DEVICE_EVIDENCE.json')
        delivered = self.evidence.FORMAL['delivered_images'](self.slot)
        by_attempt = {row['attempt']: row for row in self.calls}
        entries = []
        require(ledger['asset_sha256'] == ASSET, 'image_device_wrong_asset')
        for log in ledger['frames']:
            occurrences = delivered.get(log['ref'])
            if not occurrences:
                continue
            row = {'ref': log['ref'], 'frame_identity': log['frame_identity'], 'origin': log['origin'],
                   'view': log['view'], 'scope_id': log['scope_id'], 'qualifies': False, 'deliveries': occurrences}
            entries.append(row)
            try:
                calls = [by_attempt[item['attempt']] for item in occurrences]
                scope = self.product_frame(log, calls) if log['origin'] == 'product' else self.native_frame(log, ledger['sources'])
                raw = self.bytes(log['PNG'], log['PNG_sha256'], True)
                npz = self.bytes(log['NPZ'], log['NPZ_sha256'], True)
                for occurrence in occurrences:
                    call = by_attempt[occurrence['attempt']]
                    block, = (image for idx, image in call['images'] if idx == occurrence['MCP_content_block'])
                    require(block == raw and occurrence['frame_identity'] in (None, log['frame_identity']),
                            'received_image_differs_from_current_frame')
                row.update(PNG=self.pin(log['PNG']), NPZ=self.pin(log['NPZ']), capture_scope=scope,
                           **self.frame_proof(log, raw, npz))
            except (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError) as error:
                row['evidence_error'] = str(error)
        return entries

    def target_witness(self, doc, image):
        block = image['native_content_block_index']
        images = packed_rows(doc['images'])
        require(type(block) is int and 1 <= block <= len(images) and images[block - 1] == image,
                'published_candidate_block_address_changed')
        regions = packed_rows(doc['regions'])
        pixels = packed_rows(doc['pixels'])
        objects = packed_rows(doc['objects'])
        for region_index, region in enumerate(regions):
            key = region['complete_witness_pixel_index']
            if type(key) is not int or not 0 <= key < len(pixels):
                continue
            pixel = pixels[key]
            if (objects[region['object_index']]['object_name'] == TARGET
                    and region['source_triangle_index_ranges'] == [[0, 1]]
                    and region['status'] == 'covered'
                    and pixel['image_index'] == block - 1 and pixel['region_index'] == region_index
                    and pixel['readable'] is True and pixel['front_facing'] is True
                    and pixel['visible_surface_pixels'] >= 16 and pixel['contrasting_boundary_pixels'] >= 4):
                return pixel
        return None

    def offers(self, frames):
        rows, first_target = [], None
        by_ref = {frame['ref']: frame for frame in frames}
        for call in self.calls:
            if call['error']:
                continue
            attempt = call['attempt']
            offers = []
            for doc in call['texts']:
                if not isinstance(doc, dict):
                    continue
                images = doc.get('images') or []
                frame_table = packed_rows(images) if isinstance(images, dict) else images
                schema = doc.get('schema')
                is_target = (schema == 'active-observation-brief-v5'
                             and doc.get('binding', {}).get('capture_scope') == 'target_observation_meshes')
                if is_target and first_target is None:
                    first_target = attempt
                offers.extend((image.get('image_ref'), image['local_image_path'], image.get('image_sha256'),
                               'candidate_target_brief' if is_target else 'source_region_or_other_brief',
                               image.get('native_content_block_index', image.get('image_block_index')),
                               self.target_witness(doc, image) if is_target else None)
                              for image in frame_table if image.get('local_image_path'))
                offers.extend((frame.get('image_ref'), frame['image_path'], frame.get('image_sha256'),
                               'existing_full_path', None, None)
                              for frame in doc.get('frames') or [] if frame.get('image_path'))
            if not call.get('producer'):
                receipt = self.json(call['owner'] / 'RECEIPT.json')
                caption_lines = {text.splitlines()[-1] for text in call['texts']
                                 if isinstance(text, str) and text.splitlines()}
                for item in receipt.get('local_image_delivery', []):
                    caption = {key: item[key] for key in ('local_image_path', 'image_sha256')}
                    require(json.dumps(caption, ensure_ascii=False) in caption_lines,
                            'ordinary_local_image_path_missing_in_actual_caption')
                    offers.append((item['ref'], item['local_image_path'], item['image_sha256'],
                                   'ordinary_image_path', None, None))
            for ref, path, hexdigest, route, block, witness in offers:
                frame = by_ref.get(ref)
                received = [] if not frame else [item for item in frame['deliveries'] if item['attempt'] == attempt
                                                and (block is None or block == item['MCP_content_block'])]
                path_obj = Path(path)
                valid = (bool(frame and frame.get('qualifies') and received)
                         and hexdigest == frame['PNG']['sha256'] and path_obj.is_absolute()
                         and path_obj.is_relative_to(self.slot) and path_obj == Path(frame['PNG']['path'])
                         and path_obj.resolve(strict=True).as_posix() == path_obj.as_posix())
                if valid and route == 'candidate_target_brief':
                    valid = bool(witness
                                 and witness['visible_surface_pixels'] == frame['surface_pixels']
                                 and witness['contrasting_boundary_pixels'] == frame['contrasting_boundary_pixels'])
                rows.append({'attempt': attempt, 'ref': ref, 'path': path, 'PNG_sha256': hexdigest, 'route': route,
                             'block': block, 'same_witness_received': valid, 'CLI_received_ns': call['cli_received_ns']})
        return first_target, rows

    def task_source(self, doc, producer):
        binding = doc['binding']
        source = binding.get('observation_source')
        if source is not None:
            parent = producer['binding']
            actual = self.current_product(parent)
            require(source['measurement_scope'] == 'whole_objects'
                    and source['parent_binding_sha256'] == parent['binding_sha256']
                    and source['parent_source_binding_sha256'] == parent['source_binding_sha256']
                    and source['parent_capture_scope'] == parent['capture_scope']
                    and all(source['capture_state'][key] == actual['capture_state'][key]
                            for key in ('instance_id', 'epoch', 'revision')),
                    'measurement_not_same_current_whole_object_parent')
            roster = {mesh['object_id']: (index, mesh) for index, mesh in enumerate(actual['meshes'])}
            for row in source['objects']:
                oid = row['object_id']
                original = self.by_id[oid]
                if oid in roster:
                    index, mesh = roster[oid]
                    require(row['observation_object_index'] == index, 'measurement_parent_object_index_changed')
                else:
                    parents = [capture for capture in self.native_sources()
                               if capture['host_identity']['document_epoch'] == parent['document_epoch']
                               and all(capture['capture_state'][key] == actual['capture_state'][key]
                                       for key in ('instance_id', 'epoch', 'revision'))
                               and capture['host_identity']['object_instances'].get(oid) == original['instance_id']
                               and any(item['object_id'] == oid for item in capture['meshes'])]
                    require(parents and row['observation_object_index'] is None,
                            'measurement_supplemental_capture_missing')
                    self.evidence.same_geometry(parents[0], self.terminal)
                    mesh, = (item for item in parents[0]['meshes'] if item['object_id'] == oid)
                count = len(original['evaluated']['triangles'])
                require(row['instance_id'] == original['instance_id'] and row['source_triangle_count'] == count
                        and row['source_triangle_index_ranges'] == [[0, count - 1]]
                        and row['ordered_geometry_sha256'] == fingerprint({
                            'vertices': mesh['vertices'], 'faces': mesh['faces']}), 'measurement_scope_incomplete')
            return 'observation_task_objects'
        host = binding['host_identity']
        for capture in self.native_sources():
            identity = capture['host_identity']
            if (capture['revision'] == binding['scene_revision'] and identity == host
                    and {mesh['name'] for mesh in capture['meshes']} >= PAIR):
                self.evidence.same_geometry(capture, self.terminal)
                require(all(identity['object_instances'][row['object_id']] == self.by_id[row['object_id']]['instance_id']
                            for row in binding['objects']), 'measurement_instance_mismatch')
                return identity['capture_scope']
        raise ValueError('measurement_not_bound_to_an_actual_whole_capture')

    def measurements(self):
        seen, records = set(), []
        for call in self.calls:
            if call['error'] or not call.get('producer'):
                continue
            for public in call['texts']:
                if not isinstance(public, dict):
                    continue
                doc = public if public.get('result_kind') == 'task_query' else public.get('task_result')
                if not isinstance(doc, dict) or doc.get('result_kind') != 'task_query':
                    continue
                pair = doc.get('binding', {}).get('objects', [])
                if not PAIR <= {row.get('name') for row in pair}:
                    continue
                attempt = call['attempt']
                key = (attempt, fingerprint(doc))
                if key in seen:
                    continue
                seen.add(key)
                try:
                    require(all(self.by_name[obj['name']]['object_id'] == obj['object_id'] for obj in pair),
                            'measurement_object_identity_mismatch')
                    narrowed = deepcopy(doc)
                    if len(pair) > 2:
                        target = pair[0]
                        require(target['name'] in PAIR and narrowed.get('pairs'), 'unordered_whole_object_pair')
                        wanted, = (row for row in pair if row['name'] in PAIR - {target['name']})
                        chosen, = (row for row in doc['pairs'] if row['object_id'] == wanted['object_id'])
                        narrowed['pairs'] = [{**chosen, 'candidate_index': 0}]
                        narrowed['binding']['objects'] = [target, wanted]
                    original_order = [row['name'] for row in narrowed['binding']['objects']]
                    facts = (narrowed['pairs'][0] if 'pairs' in narrowed else narrowed)['facts']
                    if original_order == [OTHER, TARGET]:
                        narrowed['binding']['objects'].reverse()
                        if 'pairs' in narrowed:
                            narrowed['pairs'][0]['object_id'] = narrowed['binding']['objects'][1]['object_id']
                        witness = facts['surface_proximity']['value']['nearest_witness']
                        witness['a'], witness['b'] = witness['b'], witness['a']
                        witness['direction_a_to_b'] = [-number for number in witness['direction_a_to_b']]
                    result = self.evidence.measure_body(narrowed, self.meshes)
                    scope = self.task_source(doc, call['producer'])
                    records.append({'attempt': attempt, 'scope': scope, 'reported_pair_order': original_order,
                                    'wire': call['rx'], 'query': call['args']['query'], **result})
                except (ValueError, KeyError, IndexError, TypeError, OSError) as error:
                    self.errors.append({'attempt': attempt, 'measurement': str(error)})
        return records

    def native_measurement_inputs(self):
        # Public scripts can use a solver, analytic geometry or independent bounds;
        # the rubric's semantic judgment is kept separate from evidence provenance.
        rows = []
        for call in self.calls:
            if call['tool'] not in ('execute_python', 'execute_blender_code'):
                continue
            rows.append({'attempt': call['attempt'], 'tool': call['tool'], 'wire': call['rx'],
                         'args': call['args'], 'returned': call['texts'], 'isError': call['error']})
        return rows

    def run(self):
        self.check_source()
        self.collect_calls()
        frames = self.frames()
        first_target, offers = self.offers(frames)
        measurements = self.measurements()
        answer, final, attachments = self.final['final_item'](self.slot)
        authored, candidates = self.old_review['final_matches'](answer, attachments, frames, self.closed)
        for row in candidates:
            matching = [item for item in offers if item['ref'] == row['frame_ref'] and item['same_witness_received']]
            row['actual_path_offers'] = matching
            row['first_known_path_route'] = matching[0]['route'] if matching else None
        images = defaultdict(dict)
        for frame in frames:
            if frame.get('qualifies'):
                for item in frame['deliveries']:
                    images[item['PNG_sha256']].setdefault(item['attempt'], frame['ref'])
        re_reads = []
        for hexdigest, deliveries in images.items():
            first = min(deliveries)
            for attempt, ref in sorted(deliveries.items()):
                if attempt > first:
                    tool = next(row['tool'] for row in self.calls if row['attempt'] == attempt)
                    re_reads.append({'initial_attempt': first, 'attempt': attempt, 'frame_ref': ref,
                                     'same_original_PNG': hexdigest, 'tool': tool})
        return {'schema': 'perf050-target-first-image-p2-structural-review-v1',
                'slot': self.slot.name, 'execution_status': self.status['status'], 'closure': self.closed,
                'installed_source_sha256': self.install['source_sha256'], 'asset_sha256': ASSET,
                'geometric_truth': {'region_source_triangles': self.region['source_triangle_indices'],
                                    'minimum_distance_m': '15/64', 'direction_world': [0, 0, 1]},
                'attempts': [{key: call[key] for key in ('attempt', 'tool', 'cli_id', 'cli_received_ns', 'args', 'rx', 'error')}
                             for call in self.calls],
                'frames': frames, 'first_actual_target_brief_attempt': first_target,
                'first_target_brief_has_verified_path': any(
                    offer['route'] == 'candidate_target_brief' and offer['attempt'] == first_target
                    and offer['same_witness_received'] for offer in offers),
                'offered_paths': offers, 'repeated_qualifying_png_deliveries': re_reads,
                'whole_measurements': measurements, 'ordinary_computation': self.native_measurement_inputs(),
                'final': final, 'authored_references': authored, 'reopen_candidates': candidates,
                'structural_errors': self.errors, 'human_click': 'unobserved',
                'semantic_rubric': 'Parent independently grades wording, complete claims and final path opening with the unchanged five-item rubric.',
                'source_pins': [self.pin(path) for path in sorted(self.files)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--slot', type=Path, required=True)
    parser.add_argument('--install', type=Path, default=INSTALL)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_minus_I_minus_B')
    records = Review(args.repo.resolve(), args.slot, args.install).run()
    with args.output.open('x', encoding='utf8', newline='\n') as out:
        json.dump(records, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write('\n')


if __name__ == '__main__':
    main()
