"""Decode the held-out real Blender capture and bind it to the reopened asset."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


V = Path(__file__).resolve().parents[2]
FIXTURE = Path('D:/he_m4_m5_source_region_001/fixture')
ASSET_SHA = 'b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9'
READBACK_SHA = '70baebb4994c57a13c145a79627abb0671aafb161f4837e793ac869e6fd9c62c'
TERMINAL_SHA = 'd16b1787bfd3eaa36519677c801ce21d1da5ea3967357b2300f453efa8238342'
ARCHIVE_SHA = 'fef71aa0e06b589e386783f800ee67f507cc10b8a78bcd69de29d3b02f93810c'
SLOT = Path('D:/he_perf050_source_scope_rank_transfer_recovery_001/slots/P1')
INDEX = V/'perf050_source_scope_rank_transfer_recovery_001/RUNTIME_INDEX.json'
HISTORICAL_BINDING = V/'m1_joint_full_task_tail_scope_001/install/PRODUCT_RUN_BINDING.json'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pinned_capture():
    asset = (FIXTURE/'main.blend').read_bytes()
    reopened = (FIXTURE/'READBACK_AFTER_RELOAD.json').read_bytes()
    require(sha256(asset).hexdigest() == ASSET_SHA and sha256(reopened).hexdigest() == READBACK_SHA,
            'held_out_asset_or_reopened_geometry_identity_changed')
    index = json.loads(INDEX.read_bytes())
    archive = Path(index['archive']['path'])
    require(sha256(archive.read_bytes()).hexdigest() == index['archive']['sha256'] == ARCHIVE_SHA,
            'held_out_archive_identity_changed')
    indexed = {row['path']: row for row in index['files']}
    members = {}
    with ZipFile(archive) as bundle:
        def member(relative, expected=None):
            name = 'slots/P1/' + relative
            raw = (SLOT/relative).read_bytes()
            digest = sha256(raw).hexdigest()
            require(raw == bundle.read(name) and indexed[name]['sha256'] == digest
                    and indexed[name]['bytes'] == len(raw) and expected in (None, digest),
                    'held_out_archive_member_changed/' + relative)
            members[relative] = {'bytes': len(raw), 'sha256': digest}
            return raw

        require(member('native/input.blend', ASSET_SHA) == asset, 'archived_asset_copy_changed')
        terminal = json.loads(member('TERMINAL_SOURCE.json', TERMINAL_SHA))
        binding = json.loads(member('product_full/call_001/SERVICE_RESULT.json'))['binding']
        for wire in sorted((SLOT/'native/WIRE').glob('[0-9]*/*.bin')):
            member(wire.relative_to(SLOT).as_posix())
    history = json.loads(HISTORICAL_BINDING.read_bytes())
    require(binding['runtime_source_sha256'] == history['source_sha256']
            == 'a436539e9f5389b9ebaa5ccacc0a4845d53d2429923b4443b15e3f49e2a6e846'
            and terminal['source']['asset_sha256'] == ASSET_SHA and terminal['source']['scale_length'] == 1,
            'held_out_host_source_identity_changed')
    if history['dependency_root'] not in sys.path:
        sys.path.append(history['dependency_root'])
    decoder = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    audit = decoder['Audit']()
    captures, commands = decoder['decode_captures'](SLOT, history, audit)
    capture = decoder['current_capture'](captures, binding, audit)
    poses = capture['display_snapshot']
    meshes = capture['meshes']
    require((len(meshes), sum(len(row['vertices']) for row in meshes), sum(len(row['faces']) for row in meshes))
            == (11, 64, 62) and poses['status'] == 'captured', 'held_out_complete_host_scope_changed')
    source = {row['name']: row for row in terminal['objects']}
    on_reopen = {row['name']: row['evaluated'] for row in json.loads(reopened)['objects']}
    by_host_id = {row['host_id']: row for row in poses['objects']}
    require({mesh['name'] for mesh in meshes} == set(source) == set(on_reopen) and len(by_host_id) == 11,
            'held_out_mesh_rosters_disagree')
    for mesh in meshes:
        row = source[mesh['name']]
        evaluated = row['evaluated']
        reopened_mesh = on_reopen[mesh['name']]
        display = by_host_id[mesh['object_id']]
        require(mesh['object_id'] == row['object_id']
                and capture['host_identity']['object_instances'][mesh['object_id']] == row['instance_id']
                and display['visible_get'] == row['visible_get']
                and mesh['vertices'] == evaluated['vertices_world_m'] == reopened_mesh['vertices_world']
                and mesh['faces'] == evaluated['triangles'] == reopened_mesh['triangles'],
                'held_out_archived_geometry_or_display_mismatch/' + mesh['name'])
    return capture, {'objects': 11, 'points': 64, 'triangles': 62, 'archive_sha256': ARCHIVE_SHA,
                     'asset_sha256': ASSET_SHA, 'reopen_sha256': READBACK_SHA, 'terminal_sha256': TERMINAL_SHA,
                     'commands': commands, 'members': members}
