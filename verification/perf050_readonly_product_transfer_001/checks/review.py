"""Review delivered original PNGs and measured task facts in the new pair."""

import argparse
import json
from pathlib import Path
import runpy
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import FORMAL, HERE, NS, V, checked, frame_geometry, library, measure_body, pin, read, same_geometry


P3 = runpy.run_path(str(V / 'perf050_source_region_final_image_p3/checks/review.py'))
RUN = Path('D:/he_perf050_readonly_product_transfer_001')
TRUTH = NS / 'truth/TRUTH.json'
LABELS = ('N1', 'P1')


def actual(path, digest, slot):
    path = Path(path)
    checked(path.is_absolute() and path.resolve(strict=True) == path and path.is_relative_to(slot),
            'image_or_wire_path_not_current_slot')
    receipt = pin(path)
    checked(receipt['sha256'] == digest, 'image_or_wire_bytes_changed')
    return receipt, path.read_bytes()


def view_frames(slot, terminal, truth):
    delivered = FORMAL['delivered_images'](slot)
    ledger = read(slot / 'DEVICE_EVIDENCE.json')
    result = []
    for frame in ledger['frames']:
        deliveries = delivered.get(frame['ref'])
        if not deliveries:
            continue
        row = {'ref': frame['ref'], 'origin': frame['origin'], 'view': frame['view'],
               'frame_identity': frame['frame_identity'], 'deliveries': deliveries}
        result.append(row)
        try:
            png, image = actual(frame['PNG'], frame['PNG_sha256'], slot)
            npz, arrays = actual(frame['NPZ'], frame['NPZ_sha256'], slot)
            checked(all(item['PNG_sha256'] == png['sha256'] and
                        item['frame_identity'] in (None, frame['frame_identity']) for item in deliveries),
                    'model_delivered_png_not_this_frame')
            row.update(PNG=png, NPZ=npz, **frame_geometry(frame, terminal, image, arrays, truth))
        except Exception as error:
            row['error'] = str(error)
    return result


def final_matches(answer, attachments, frames, closed):
    paths = [row['PNG']['path'] for row in frames if 'PNG' in row]
    authored = P3['final_reference_kinds'](answer, paths) + attachments
    candidates = []
    for item in authored:
        path = item.get('destination')
        is_local = item.get('local_markdown') or item['kind'] == 'structured_media'
        for frame in frames:
            if not is_local or not closed or not frame.get('qualifies'):
                continue
            same_path = (isinstance(path, str) and Path(path).is_absolute()
                         and '..' not in Path(path).parts and Path(path) == Path(frame['PNG']['path']))
            same_media = item['kind'] == 'structured_media' and item.get('PNG_sha256') == frame['PNG']['sha256']
            if same_path or same_media:
                candidates.append({**frame['PNG'], 'reference_kind': item['kind'], 'frame_ref': frame['ref'],
                                   'view': frame['view'], 'origin': frame['origin'],
                                   'authored_destination': path, 'post_close_bytes_verified': True})
    return authored, list({(row['path'], row['frame_ref']): row for row in candidates}.values())


def task_evidence(slot, attempts, terminal, meshes):
    measurements, errors = [], []
    identities = {row['name']: row['object_id'] for row in terminal['objects']}
    for attempt in attempts:
        if attempt.get('CLI_binding') != 'content_and_envelope_match' or not attempt.get('stdio_RX'):
            continue
        receipt = attempt['stdio_RX']
        try:
            _, wire = actual(receipt['path'], receipt['sha256'], slot)
            wire = json.loads(wire)
            if wire.get('result', {}).get('isError') or attempt['tool'] != 'human_eye_scene_observe':
                continue
            for text in (row['text'] for row in wire['result']['content'] if row['type'] == 'text'):
                try:
                    body = json.loads(text)
                except json.JSONDecodeError:
                    continue
                joints = [body] if body.get('result_kind') == 'task_query' else [body.get('task_result')]
                for value in joints:
                    if not isinstance(value, dict) or value.get('result_kind') != 'task_query':
                        continue
                    indexed = value['binding']['objects']
                    if [row.get('name') for row in indexed] != ['M09', 'M03']:
                        continue
                    checked(all(identities[row['name']] == row['object_id'] for row in indexed),
                            'successful_task_objects_are_not_this_terminal_scope')
                    audit = measure_body(value, meshes)
                    measurements.append({'attempt': attempt['attempt'], 'original_reply': receipt,
                                         'query': attempt['arguments'].get('query'), **audit})
        except Exception as error:
            errors.append({'attempt': attempt['attempt'], 'reason': str(error), 'type': type(error).__name__})
    return measurements, errors


def review_slot(slot, costs, truth):
    row = {'label': slot.name, 'status': costs['status'], 'reopen_candidates': []}
    if not slot.is_dir() or costs['status'] != 'completed':
        row['reason'] = costs.get('host_errors') or costs.get('consumer_status') or 'no_completed_slot'
        return row
    try:
        terminal = read(slot / 'TERMINAL_SOURCE.json')
        meshes = same_geometry(None, terminal)
        summary = read(slot / 'SLOT_RESULT.json')
        closed = (summary['closure_verification']['passed'] is True and
                  summary['closure_verification']['status'] == 'ready_closed')
        checked(summary['result_sha256'] == costs['result_sha256'] if 'result_sha256' in summary else
                pin(slot / 'SLOT_RESULT.json')['sha256'] == costs['result_sha256'],
                'slot_result_not_the_original_costs_receipt')
        frames = view_frames(slot, terminal, truth)
        answer, final, media = P3['final_item'](slot)
        refs, candidates = final_matches(answer, media, frames, closed)
        task, errors = task_evidence(slot, costs['actual_requests'], terminal, meshes)
        row.update(frames=frames, closed=closed, final=final, authored_references=refs,
                   reopen_candidates=candidates, product_whole_measurements=task, tool_evidence_errors=errors)
    except Exception as error:
        row.update(evidence_error=str(error), evidence_error_type=type(error).__name__)
    return row


def review(run, costs_path):
    library()
    truth, costs = read(TRUTH), read(costs_path)
    checked(truth['passed'] and [row['label'] for row in costs['slots']] == list(LABELS),
            'review_truth_or_current_denominator_changed')
    return {'schema': 'perf050-readonly-product-transfer-structural-review-v1', 'truth': pin(TRUTH),
            'costs': pin(costs_path),
            'slots': [review_slot((run / 'slots' / row['label']).resolve(), row, truth) for row in costs['slots']],
            'desktop_open': 'record actual editor or file-tool opens separately',
            'human_click': 'unobserved', 'final_semantic_scores': 'apply frozen RUBRIC.md to each unchanged answer'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--costs', type=Path, default=NS / 'consumer/COSTS.json')
    parser.add_argument('--output', type=Path, default=HERE / 'EVIDENCE.json')
    args = parser.parse_args()
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(review(args.runtime, args.costs), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
