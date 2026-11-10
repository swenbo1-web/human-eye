"""Offline admin scoring only. Never invokes a host, model, or production API."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re

ROLES = ('near_right_upright_separator', 'left_short_locator_block', 'through_opening_probe_rod')
CLASSES = ('solid_overlap', 'within_contact_tolerance', 'separated', 'unknown')
BINDING_FILES = {'scene_sha256': 'scene.blend', 'catalog_sha256': 'CATALOG.json',
                 'initial_view_sha256': 'INITIAL.png', 'initial_camera_sha256': 'INITIAL_VIEW.json'}


def _load(value):
    if isinstance(value, (str, Path)):
        raw = Path(value).read_bytes()
        if len(raw) > 128*1024*1024:raise ValueError('JSON input byte limit')
        def unique(pairs):
            result = {}
            for key, child in pairs:
                if key in result:raise ValueError('duplicate JSON key: '+key)
                result[key] = child
            return result
        return json.loads(raw, object_pairs_hook=unique,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON'))), hashlib.sha256(raw).hexdigest()
    return value, None


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():yield from _walk(child)
    elif isinstance(value, list):
        for child in value:yield from _walk(child)


def _schema_errors(value, schema, root=None, path='$'):
    """Small validator for the actual frozen schema's used vocabulary."""
    root = schema if root is None else root
    errors = []
    if '$ref' in schema:
        target = root
        for key in schema['$ref'][2:].split('/'):target = target[key]
        return _schema_errors(value, target, root, path)
    kinds = {'object': lambda x: type(x) is dict, 'array': lambda x: type(x) is list,
             'string': lambda x: type(x) is str, 'null': lambda x: x is None,
             'number': lambda x: type(x) in (int, float) and math.isfinite(x),
             'integer': lambda x: type(x) is int, 'boolean': lambda x: type(x) is bool}
    if 'type' in schema and not kinds[schema['type']](value):return [path+': type']
    if 'const' in schema and value != schema['const']:errors.append(path+': const')
    if 'enum' in schema and value not in schema['enum']:errors.append(path+': enum')
    for branch in schema.get('allOf', []):errors += _schema_errors(value, branch, root, path)
    if 'anyOf' in schema and not any(not _schema_errors(value, branch, root, path) for branch in schema['anyOf']):errors.append(path+': anyOf')
    if 'if' in schema:
        branch = 'else' if _schema_errors(value, schema['if'], root, path) else 'then'
        errors += _schema_errors(value, schema.get(branch, {}), root, path)
    if type(value) is dict:
        errors += [path+': missing '+key for key in schema.get('required', []) if key not in value]
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False:
            errors += [path+': extra '+key for key in value if key not in properties]
        for key, child in value.items():
            if key in properties:errors += _schema_errors(child, properties[key], root, path+'.'+key)
    elif type(value) is list:
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')):errors.append(path+': item count')
        if schema.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):errors.append(path+': duplicate item')
        if 'items' in schema:
            for index, child in enumerate(value):errors += _schema_errors(child, schema['items'], root, path+'['+str(index)+']')
        if 'contains' in schema:
            count = sum(not _schema_errors(child, schema['contains'], root, path) for child in value)
            if not schema.get('minContains', 1) <= count <= schema.get('maxContains', float('inf')):errors.append(path+': contains count')
    elif type(value) is str:
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', float('inf')):errors.append(path+': string length')
        if 'pattern' in schema and re.search(schema['pattern'], value) is None:errors.append(path+': pattern')
    elif type(value) in (int, float):
        if not math.isfinite(value):errors.append(path+': nonfinite')
        if value < schema.get('minimum', -float('inf')):errors.append(path+': minimum')
    return errors


def manifest_binding(manifest, manifest_root=None):
    manifest, _ = _load(manifest)
    entries = manifest.get('files', manifest.get('inputs', []))
    if not isinstance(entries, list):raise ValueError('manifest files must be a list')
    binding = {};seen = set()
    for entry in entries:
        name = Path(entry['path']).name
        if entry['path'] in seen:raise ValueError('duplicate manifest path')
        seen.add(entry['path'])
        if not re.fullmatch('[a-f0-9]{64}', entry['sha256']):raise ValueError('invalid manifest SHA')
        if manifest_root is not None:
            path = Path(entry['path'])
            if not path.is_absolute():path = Path(manifest_root)/path
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != entry['sha256']:raise ValueError('manifest file SHA mismatch: '+entry['path'])
        for field, filename in BINDING_FILES.items():
            if name == filename:
                if field in binding:raise ValueError('ambiguous binding file: '+filename)
                binding[field] = entry['sha256']
    if set(binding) != set(BINDING_FILES):raise ValueError('four source binding files required')
    return binding


def _record_nodes(records, binding):
    return [node for record in records.get('records', [])
            if record.get('returned') is True and record.get('received') is True
            and record.get('source_binding') == binding
            for node in _walk(record.get('payload')) if isinstance(node, dict)]


def _image_valid(image_ref, records, binding):
    for record in records.get('records', []):
        if not (record.get('returned') is True and record.get('received') is True
                and record.get('source_binding') == binding):continue
        for image in record.get('images', []):
            if image.get('image_ref') != image_ref:continue
            if (image.get('returned', True) is not True or image.get('received', True) is not True
                    or image.get('source_binding', binding) != binding):continue
            digest = image.get('sha256')
            if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):continue
            for node in _walk(record.get('payload')):
                if not isinstance(node, dict):continue
                data = node.get('image_base64', node.get('data'))
                if not isinstance(data, str):continue
                try:raw = base64.b64decode(data, validate=True)
                except (ValueError, TypeError):continue
                if raw.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(raw).hexdigest() == digest:return True
    return False


def _evidence_check(evidence, pair, geometry, records, binding):
    errors = [];references = 0;nodes = _record_nodes(records, binding)
    if not isinstance(evidence, dict):return {'validated': False, 'errors': ['missing evidence'], 'sufficiency': 'manual_pending'}
    for feature in evidence.get('source_features', []):
        identity = feature['object_id'];indices = feature['triangle_indices']
        if identity not in pair:errors.append('feature outside requested pair');continue
        triangles = geometry.get(identity, {}).get('triangles', [])
        if not triangles or any(type(index) is not int or not 0 <= index < len(triangles) for index in indices):
            errors.append('source triangle outside range');continue
        present = any(node.get('object_id') == identity and
                      set(indices) <= set(node.get('triangle_indices', node.get('face_indices', [])))
                      for node in nodes)
        if not present:errors.append('source feature absent from received payload')
        else:references += 1
    for point in evidence.get('witness_points', []):
        if point['object_id'] not in pair:errors.append('witness outside requested pair');continue
        present = any(node.get('object_id') == point['object_id'] and
                      node.get('world_m') == point['world_m'] for node in nodes)
        if not present:errors.append('witness absent from received payload')
        else:references += 1
    for image_ref in evidence.get('image_refs', []):
        if not _image_valid(image_ref, records, binding):errors.append('image not received or hash/source/payload mismatch')
        else:references += 1
    if references == 0:errors.append('no validated observation reference')
    return {'validated': references > 0 and not errors, 'errors': errors,
            'validated_references': references, 'locality': 'manual_pending', 'sufficiency': 'manual_pending'}


def score_answer(answer, manifest, oracle, catalog, world_geometry, records, *, manifest_root=None):
    """Manifest/oracle/catalog/geometry must be files; root and seals are mandatory.

    Answer/records may be parsed JSON. Pass manifest_root=QUAL002 root. Evidence score
    certifies reference provenance/ranges only; spatial sufficiency stays manual.
    """
    result = {'schema': 'offline-spatial-score-v1', 'result_kind': 'admin_offline_scoring',
              'valid_submission': False, 'validation_errors': [], 'not_a_consumer_result': True,
              'records_provenance': 'unverified_caller_supplied',
              'delivery_attestation': 'returned_received_flags_not_independently_authenticated'}
    try:
        if manifest_root is None:raise ValueError('unverified: manifest_root is required')
        for label, value in (('manifest', manifest), ('oracle', oracle), ('catalog', catalog), ('geometry', world_geometry)):
            if not isinstance(value, (str, Path)):raise ValueError('unverified: '+label+' exact-byte file path required')
        answer, _ = _load(answer);manifest, _ = _load(manifest);oracle, oracle_sha = _load(oracle)
        catalog, catalog_sha = _load(catalog);world_geometry, geometry_sha = _load(world_geometry)
        records, _ = _load(records);binding = manifest_binding(manifest, manifest_root)
        seal = manifest.get('oracle_bindings', {}).get('ORACLE_PRIVATE.json')
        if not seal or oracle_sha != seal:raise ValueError('oracle frozen exact-byte seal mismatch')
        schema_entries = [entry for entry in manifest.get('files', manifest.get('inputs', []))
                          if Path(entry['path']).name == 'ANSWER_SCHEMA.json']
        if len(schema_entries) != 1:raise ValueError('frozen ANSWER_SCHEMA hash required')
        schema, schema_sha = _load(Path(manifest_root)/'shared/ANSWER_SCHEMA.json')
        if schema_sha != schema_entries[0]['sha256']:raise ValueError('frozen ANSWER_SCHEMA exact bytes mismatch')
        task = manifest.get('task_id', manifest.get('task'))
        if not task or answer.get('task_id') != task or oracle.get('task_id') != task:raise ValueError('task binding mismatch')
        if answer.get('source_binding') != binding or oracle.get('source_binding') != binding:raise ValueError('source binding mismatch')
        if catalog_sha and catalog_sha != binding['catalog_sha256']:raise ValueError('catalog exact bytes mismatch')
        if geometry_sha and oracle.get('world_geometry_sha256') != geometry_sha:raise ValueError('oracle geometry SHA mismatch')
        if catalog.get('source_sha256') != binding['scene_sha256'] or world_geometry.get('source_sha256') != binding['scene_sha256']:
            raise ValueError('catalog/geometry scene source mismatch')
        if manifest_root is not None:
            try:
                import jsonschema
            except ImportError:
                errors = _schema_errors(answer, schema)
                result['schema_validator'] = 'bounded_used_vocabulary_validator'
            else:
                errors = [str(error) for error in jsonschema.Draft202012Validator(schema).iter_errors(answer)]
                result['schema_validator'] = 'jsonschema.Draft202012Validator'
            if errors:raise ValueError('schema: '+'; '.join(errors[:12]))
        if any(type(value) is float and not math.isfinite(value) for value in _walk(answer)):raise ValueError('nonfinite answer')
        ids = {obj['object_id'] for obj in catalog['objects']}
        if any(not re.fullmatch('N[0-9]{2}', identity) for identity in ids):raise ValueError('catalog ID format')
        rows = answer.get('relations', [])
        if len(rows) != 3 or sorted(row.get('neighbor_role', '') for row in rows) != sorted(ROLES):raise ValueError('exactly three unique neighbor roles required')
        target = answer.get('target_id')
        if target is not None and target not in ids:raise ValueError('target outside catalog')
        for row in rows:
            if row.get('neighbor_id') is not None and row['neighbor_id'] not in ids:raise ValueError('neighbor outside catalog')
            if row.get('relation') not in CLASSES:raise ValueError('unknown relation vocabulary')
            if row['relation'] != 'unknown' and (target is None or row.get('neighbor_id') is None):raise ValueError('known relation requires target and neighbor')
        truth = {row['neighbor_role']: row for row in oracle['relations']}
        if len(oracle['relations']) != 3 or set(truth) != set(ROLES):raise ValueError('oracle role binding invalid')
        if oracle['target_id'] not in ids or any(row['neighbor_id'] not in ids or row['relation'] not in CLASSES[:3] for row in truth.values()):raise ValueError('oracle IDs/truth invalid')
        geometry = {obj['object_id']: obj for obj in world_geometry['objects']}
        target_correct = target == oracle['target_id'];scored = []
        for row in rows:
            expected = truth[row['neighbor_role']]
            neighbor_correct = row.get('neighbor_id') == expected['neighbor_id']
            bound = target_correct and neighbor_correct;known = row['relation'] != 'unknown'
            evidence = _evidence_check(row.get('evidence'), {target, row.get('neighbor_id')}, geometry, records, binding)
            scored.append({'neighbor_role': row['neighbor_role'], 'neighbor_id_correct': neighbor_correct,
                           'canonical_pair_bound': bound, 'prediction': row['relation'], 'truth': expected['relation'],
                           'correct': bound and known and row['relation'] == expected['relation'],
                           'known_claim': known, 'evidence': evidence})
        known_bound = [row for row in scored if row['canonical_pair_bound'] and row['known_claim']]
        fp = sum(row['prediction'] == 'solid_overlap' and row['truth'] != 'solid_overlap' for row in known_bound)
        fn = sum(row['prediction'] != 'solid_overlap' and row['truth'] == 'solid_overlap' for row in known_bound)
        result.update(valid_submission=True, task_id=task, source_binding=binding,
            synthetic_offline_fixture=records.get('synthetic_offline_fixture') is True,
            manifest_files_verified=True, oracle_seal_verified=True, answer_schema_seal_verified=True,
            target={'correct': int(target_correct), 'total': 1, 'unknown': target is None},
            relations={'correct': sum(row['correct'] for row in scored), 'total': 3,
                       'known_claims': sum(row['known_claim'] for row in scored),
                       'canonical_known_coverage': len(known_bound), 'unknown': sum(not row['known_claim'] for row in scored),
                       'neighbor_ids_correct': sum(row['neighbor_id_correct'] for row in scored), 'rows': scored},
            evidence={'validated': sum(row['canonical_pair_bound'] and row['evidence']['validated'] for row in scored),
                      'total': 3, 'scope': 'received_reference_provenance_and_ranges_only',
                      'record_origin': 'caller_supplied_not_a_verified_host_or_model_delivery_attestation',
                      'locality': 'manual_pending', 'argument_sufficiency': 'manual_pending'},
            overlap={'false_positive': fp, 'false_negative': fn,
                     'unknown_on_oracle_overlap': sum(not row['known_claim'] and row['truth'] == 'solid_overlap' for row in scored),
                     'identity_unresolved': sum(not row['canonical_pair_bound'] for row in scored)},
            refusal={'reported': answer.get('answer_status') == 'refused', 'counts_as_task_answer': False})
    except (ValueError, KeyError, TypeError, OSError, RecursionError) as exc:
        result['validation_errors'].append(str(exc))
    return result


def summarize_ledger(events):
    """Count evaluations, unique pairs, constructions and deliveries separately."""
    pairs = [];constructed = set();received = set();returned = set();unknown = 0
    for index, event in enumerate(events):
        kind = event.get('kind')
        if kind == 'pair_evaluation':
            for pair in event['pairs']:
                if len(pair) != 2 or pair[0] == pair[1]:raise ValueError('invalid evaluated pair')
                pairs.append(tuple(sorted(pair)))
        elif kind == 'image_constructed':
            identity = event.get('construction_id')
            if not identity:raise ValueError('construction_id required')
            constructed.add(identity)
        elif kind in ('image_received', 'image_returned'):
            identity = event.get('delivery_id')
            if not identity:raise ValueError('delivery_id required')
            (received if kind == 'image_received' else returned).add(identity)
        elif kind == 'image_construction_unknown':unknown += 1
    return {'pair_evaluations': len(pairs), 'unique_pairs': len(set(pairs)),
            'images_constructed': len(constructed), 'images_received': len(received),
            'images_returned': len(returned), 'unknown_constructions': unknown}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('answer', 'freeze', 'oracle', 'catalog', 'geometry', 'records'):parser.add_argument('--'+key, required=True)
    parser.add_argument('--manifest-root', required=True);parser.add_argument('--output')
    args = parser.parse_args(argv)
    result = score_answer(args.answer, args.freeze, args.oracle, args.catalog, args.geometry,
                          args.records, manifest_root=args.manifest_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    if args.output:Path(args.output).write_text(rendered, encoding='utf8')
    else:print(rendered, end='')
    return 0 if result['valid_submission'] else 2


if __name__ == '__main__':raise SystemExit(main())
