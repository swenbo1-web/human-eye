"""Freeze the one local production qualification after the installed preflight."""

from base64 import b64decode
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output
from runpy import run_path
import sys
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qualification import BASE, CANDIDATE, CHECK, EXTRAS, HERE, V, launch, read, require, save


FROZEN = HERE / 'FROZEN.json'
PRODUCTS = ('8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b', '24b8855746dfe9eeee7fa7d374bec2da86c21a2e')
PLAN = 'c5c2c3a89c545020a86559795c82bc80e28367a1:docs/M1_REGION_TASK_FIRST_PACKET_PROJECTION_001_PLAN.md'
PRIOR_NAME = 'm1_region_task_brief_client_profile_recovery_001'
PRIOR_READBACK = 'preflight/QB/direct/03_same_name_scopes_read'


def prior_public_evidence():
    """Verify sealed public read_images evidence in its own historical scope."""
    index = V / PRIOR_NAME / 'RAW_INDEX.json'
    items = read(index)
    archive = index.with_name(items['archive']['name'])
    zip_pin = launch.pin(archive)
    require(all(zip_pin[key] == items['archive'][key] for key in ('bytes', 'sha256')), 'prior_public_archive_changed')
    originals = []
    root = Path('D:/he_' + PRIOR_NAME)
    response = read(root / PRIOR_READBACK / 'RESPONSE.json')
    pictures = [json.loads(block['text'].split('\n', 1)[1])['local_image_path']
                for block in response['result']['content'] if block['type'] == 'text']
    members = (f'{PRIOR_READBACK}/REQUEST.json', f'{PRIOR_READBACK}/RESPONSE.json',
               'preflight/QB/direct/OUTER_CLOSE.json', *(Path(path).relative_to(root).as_posix() for path in pictures))
    with ZipFile(archive) as package:
        for member in members:
            path = Path('D:/he_' + PRIOR_NAME) / member
            binding = launch.pin(path)
            require(all(binding[key] == items['members'][member][key] for key in ('bytes', 'sha256'))
                    and package.read(member) == path.read_bytes(), 'prior_public_readback_member_changed/' + member)
            originals.append(path)
    return index, archive, *originals


def check_prior_public_readback(result):
    _, _, request, response, close, *paths = prior_public_evidence()
    call, receipt, shutdown = read(request), read(response), read(close)
    require(receipt['id'] == call['id'] and receipt['result']['isError'] is False
            and call['params']['name'] == 'read_images' and shutdown['confirmed']
            and shutdown['exit_code'] == 0, 'prior_public_readback_or_close_unproven')
    brief = json.loads(result['content'][0]['text'])
    frames, scopes = brief['frames'], brief['scopes']
    rows = [dict(zip(frames['columns'], row, strict=True)) for row in frames['rows']]
    require([row['image_ref'] for row in rows] == call['params']['arguments']['refs']
            and len(rows) == len(paths) == 3, 'historical_read_images_different_scope_or_order')
    content = receipt['result']['content']
    require(len(content) == 6, 'historical_read_images_content_count_changed')
    details = []
    for row, caption, image, path in zip(rows, content[::2], content[1::2], paths, strict=True):
        title, body = caption['text'].split('\n', 1)
        metadata = json.loads(body)
        original = path.read_bytes()
        require(caption['type'] == 'text' and title.startswith(row['image_ref'] + ' ')
                and Path(metadata['local_image_path']).resolve(strict=True) == path.resolve(strict=True)
                and metadata['image_sha256'] == row['image_sha256'] == sha256(original).hexdigest()
                and image == result['content'][row['native_content_block_index']]
                and b64decode(image['data'], validate=True) == original, 'historical_read_images_png_or_frame_changed')
        details.append({'scope_id': scopes['rows'][row['scope_index']][0], 'frame_identity': row['frame_identity'],
                        'view': row['view_name'], 'ref': row['image_ref'], 'sha256': row['image_sha256'],
                        'bytes': len(original)})
    return {'matched_archived_public_reads': details, 'closed_slot_path_bytes_verified': True,
            'readback_receipt': launch.pin(response), 'scope': 'sealed historical public consumer, not a new tool'}


def fixed_installs():
    for path, git in zip((BASE, CANDIDATE), PRODUCTS, strict=True):
        binding = read(path)
        require(binding['preparation_git'] == git and len(binding['source_manifest']) == 143,
                'fixed_installed_product_changed')
        yield path
        wheel = Path(binding['wheel_path'])
        require(launch.pin(wheel)['sha256'] == binding['wheel_sha256'], 'frozen_wheel_digest_changed')
        yield wheel
        for source in binding['source_manifest']:
            file = Path(binding['install_root']) / source['path']
            require(launch.pin(file)['sha256'] == source['sha256'], 'frozen_runtime_source_changed/' + source['path'])
            yield file


def create():
    require(not FROZEN.exists() and not (launch.EXTERNAL / 'qualification').exists(), 'qualification_already_registered')
    preflight = launch.EXTERNAL / 'production_preflight'
    require(read(preflight / 'PREFLIGHT.json')['passed'], 'actual_production_preflight_required')
    require(check_output(['git', 'show', PLAN], cwd=V.parent) == (HERE / 'PLAN.md').read_bytes(),
            'fixed_plan_content_changed')
    paths = [HERE / name for name in ('PLAN.md', 'freeze.py', 'launch.py', 'qualification.py', 'build_install.py',
                                     'install/BUILD_INSTALL.json')]
    comparator = run_path(str(V / 'm4_dense_region_brief_001/checks/brief_schema.py'))
    policy = run_path(str(comparator['POLICY_PATH']))
    paths.extend((CHECK, BASE.with_name('TOOLS_SCHEMA.json'), CHECK.with_name('product_replay.py'), Path(sys.executable),
                  V / 'm4_source_region_display_001/harness/reused/stdio_checks.py',
                  Path(comparator['__file__']), Path(comparator['TYPED_PATH']), Path(comparator['POLICY_PATH']),
                  policy['PRIOR'] / 'client_budget_replay.py', policy['PRIOR'] / 'CLIENT_BUDGET_REVIEW.json'))
    # Bind the exact comparator dependencies and actual completed production preflight.
    paths.extend(fixed_installs())
    paths.extend(prior_public_evidence())
    paths.extend(path for path in preflight.rglob('*') if path.is_file())
    pins = {row['path']: row for row in map(launch.pin, paths)}
    batches = {launch.FORMAL, launch.RETAINED['PREDICTION'], launch.RETAINED['TARGET'],
               *(row[1] for row in EXTRAS)}
    for batch in sorted(batches):
        for row in launch.RETAINED['archive_scope'](batch)[4]:
            pins[row['path']] = row
    _, terminal = launch.archived(launch.FORMAL, 'slots', 'P3', 'TERMINAL_SOURCE.json')
    pins[terminal['path']] = terminal
    for slot in ('P2', 'P3'):
        for record in launch.fixtures(slot, EXTRAS if slot == 'P3' else ()).values():
            pins.update((row['path'], row) for row in record['pins'])
    for case in run_path(str(CHECK))['archived_cases']().values():
        for member in case['provenance']['original_members']:
            row = launch.pin(launch.RETAINED['archive_scope'](launch.FORMAL)[0] / member.removeprefix('runtime/'))
            pins[row['path']] = row
    save(FROZEN, {'plan': PLAN, 'product_git': PRODUCTS, 'preflight': str(preflight),
                  'registration': {'primary_slots': ['P2', 'P3'],
                                   'editions': ['base_standard', 'candidate_standard', 'candidate_isolated'],
                                   'expiration_controls': 3, 'registered_cells': 9, 'replacements': 0,
                                   'model_starts': 0, 'Blender_starts': 0, 'new_rasters': 0},
                  'pins': [pins[path] for path in sorted(pins)]})
    print('Qualification frozen', verify(), len(pins), 'pins')


def verify():
    frozen = read(FROZEN)
    require(frozen['plan'] == PLAN and tuple(frozen['product_git']) == PRODUCTS
            and frozen['registration']['registered_cells'] == 9, 'frozen_qualification_identity_changed')
    for pinned in frozen['pins']:
        require(launch.pin(Path(pinned['path'])) == pinned, 'frozen_input_changed/' + pinned['path'])
    return sha256(FROZEN.read_bytes()).hexdigest()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_interpreter_required')
    create()
