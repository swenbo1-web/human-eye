"""Bind the four closed scoring inputs to the two original committed archives."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUN = Path('D:/he_m4_source_region_score_admission_001')
PRODUCT = 'e800667077a6c390dbc1f49aa46ba9a01b153de5'
LABELS = ('N1', 'P1')
ASSETS = {
    'assembly': {'root': Path('D:/he_m4_assembly_cross_asset_product_native_001'),
                 'evidence': HERE.parent/'m4_assembly_cross_asset_product_native_001',
                 'git': '4bc6b7d6da32a4204f57465f4311723e0836faff',
                 'members': 963},
    'yanyite': {'root': Path('D:/he_m4_yanyite_opposite_direction_product_native_001'),
                 'evidence': HERE.parent/'m4_yanyite_opposite_direction_product_native_001',
                 'git': '75f75b920c9e21a0148cfca110ae04e75b8641d6',
                 'members': 817},
}


def require(condition, why):
    if not condition:
        raise ValueError(why)


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, 'duplicate_custody_json_key/'+key)
        obj[key] = value
    return obj


def json_bytes(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def read(path):
    return json_bytes(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        count = stream.tell()
    require(path.stat().st_size == count, 'custody_file_size_changed/'+str(path))
    return {'path':str(path),'bytes':count,'sha256':digest}


def git_file(path, git):
    relative = path.relative_to(REPO).as_posix()
    expected = subprocess.check_output(['git','show',git+':'+relative],cwd=REPO)
    require(path.read_bytes() == expected, 'historical_result_source_changed/'+relative)
    return pin(path)


def member_path(root, name):
    path = PurePosixPath(name)
    require(bool(path.parts) and not path.is_absolute() and path.as_posix()==name
            and '..' not in path.parts and '\\' not in name and ':' not in name,
            'invalid_historical_archive_member/'+name)
    loose = root.joinpath(*path.parts)
    real = loose.resolve(strict=True)
    require(str(real)==str(loose) and real.is_relative_to(root) and real.is_file(),
            'archived_loose_member_not_in_registered_root/'+name)
    return real


def verify_members(root, bundle, listing, count):
    members = listing['members']
    require(count == listing['member_count'] == len(members)
            and len({name.casefold() for name in members}) == count, 'raw_index_population_changed')
    rows = {}
    with ZipFile(bundle) as pack:
        files = pack.infolist()
        require(len(files)==count and set(info.filename for info in files)==members.keys(),
                'original_archive_population_changed')
        for info in files:
            name = info.filename
            require(not info.is_dir(), 'non_file_historical_archive_member/'+name)
            indexed = members[name]
            real = member_path(root, name)
            # Reading to EOF authenticates the member CRC as well as the SHA-256.
            # In particular, raw stdout is never decoded or parsed here.
            with pack.open(info) as stream:
                digest = hashlib.file_digest(stream,'sha256').hexdigest()
                length = stream.tell()
            identity = {'bytes':length,'sha256':digest}
            require(info.file_size==length and identity==indexed, 'original_archive_member_changed/'+name)
            actual = pin(real)
            require(actual=={'path':str(real),**identity}, 'closed_loose_input_changed/'+name)
            rows[name] = actual
    return rows


def bound_record(record, members, *, prefix=None, named=None):
    name = record['archive_member']
    require((named is None or name==named) and (prefix is None or name.startswith(prefix))
            and members.get(name)=={k:record[k] for k in ('path','bytes','sha256')},
            'published_member_binding_failed/'+name)
    return {'archive_member':name,**members[name]}


def slots(asset, result, members):
    assembly = asset=='assembly'
    mapped = {}
    for label in LABELS:
        row = result['arms'][label]
        prefix = f'slots/{label}/'
        answer = bound_record(row['final_answer' if assembly else 'exact_final'],members,
                              named=prefix+'consumer/PUBLIC_FINAL.txt')
        claims = bound_record(row['unchanged_claims' if assembly else 'literal_claims'],members,
                              named=f'score/{label}_CLAIMS.json')
        publication = bound_record(row['publication' if assembly else 'slot_publication'],members,
                                   named=prefix+'SLOT_PUBLICATION.json')
        original = bound_record(row['original_frozen_score' if assembly else 'full_score'],members,
                                named=f'score/{label}_SCORE.json')
        expected = (bound_record(row['derived_score'],members,named=f'score/{label}_DERIVED_SCORE.json')
                    if assembly else original)
        result_path = members[prefix+'SLOT_RESULT.json']
        closure = members[prefix+'RUNTIME_CLOSE.json']
        stdout = members[prefix+'consumer/stdout.raw.bin']
        signed_answer = read(result_path['path'])
        published = read(publication['path'])
        transcribed = read(claims['path'])
        require(signed_answer['label']==published['label']==transcribed['slot']==label
                and signed_answer['status']==published['status']=='completed'
                and published['result_sha256']==result_path['sha256']
                and signed_answer['freeze_sha256']==result['freeze_sha256']
                and signed_answer['independent_before_after']['passed'] is True
                and signed_answer['closure_verification']['passed'] is True
                and transcribed['answer_sha256']==answer['sha256'],
                'historical_closed_slot_not_bound/'+asset+'/'+label)
        image_rows = row['final_images' if assembly else 'images']
        images = {name:{kind:bound_record(pair[kind],members,prefix=prefix)
                        for kind in ('PNG','NPZ')} for name,pair in image_rows.items()}
        require(len(images)==2, 'expected_two_original_answer_images/'+asset+'/'+label)
        mapped[label] = {
            'slot_path':str(Path(result_path['path']).parent),
            'claims_path':claims['path'],
            'original_score_path':original['path'],
            'expected_score_path':expected['path'],
            'claims':claims,'answer':answer,'publication':publication,
            'result':result_path,'runtime_close':closure,'stdout_hash_only':stdout,
            'original_score':original,'expected_score':expected,'images':images,
        }
    return mapped


def manifest():
    receipts, pins = {}, {}
    for asset, spec in ASSETS.items():
        root = spec['root'].resolve(strict=True)
        result_path = spec['evidence']/'RESULT.json'
        historical_freeze = spec['evidence']/'FROZEN.json'
        sources = [git_file(path,spec['git']) for path in (result_path,historical_freeze)]
        result = read(result_path)
        require((result.get('installed_product') or result['product'])['commit']==PRODUCT
                and sources[1]['sha256']==result['freeze_sha256'], 'historical_product_or_freeze_changed/'+asset)
        index = root/'sealed/RAW_INDEX.json'
        bundle = root/'sealed/ORIGINAL_RUNTIME.zip'
        index_pin,bundle_pin = pin(index),pin(bundle)
        listing = read(index)
        require(listing['archive']==result['raw_archive']['archive']==bundle_pin
                and result['raw_archive']['member_count']==spec['members'], 'original_archive_identity_changed/'+asset)
        members = verify_members(root,bundle,listing,spec['members'])
        require(pin(bundle)==bundle_pin and pin(index)==index_pin, 'archive_changed_during_member_replay/'+asset)
        receipts[asset] = {
            'root':str(root),'evidence_commit':spec['git'],'historical_result':sources[0],
            'historical_freeze':sources[1],'archive':bundle_pin,'index':index_pin,
            'members_checked':len(members),'slots':slots(asset,result,members),
        }
        for row in (*sources,index_pin,bundle_pin,*members.values()):
            require(row['path'] not in pins, 'duplicate_original_custody_path/'+row['path'])
            pins[row['path']] = row
    return {'passed':True,'installed_product_commit':PRODUCT,'assets':receipts,
            'source_pins':sorted(pins.values(),key=lambda r:r['path'])}


def verify_manifest(record):
    require(manifest()==record, 'original_custody_manifest_changed')
    return True
