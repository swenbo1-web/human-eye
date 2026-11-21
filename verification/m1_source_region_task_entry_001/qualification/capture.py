"""Recover the pinned Assembly Transfer native host capture without Blender."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from zipfile import ZipFile


V = Path(__file__).resolve().parents[2]
SLOT = Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/P1')
INDEX = '39fd39cdad162bbe7e5eb68243881d39bb67d285:verification/m4_cross_scale_assembly_transfer_001/RUNTIME_INDEX.json'
HISTORICAL_BINDING = '8bfc832e6e4a9198147bce3bdcffe2e9d56f2811:verification/m4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
TERMINAL_SHA = 'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90'
ARCHIVE_SHA = 'bf7be101396593b151411e567b05af32e0e0754ac18dc733a6a10191fcae3627'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pinned_capture():
    index = json.loads(subprocess.check_output(['git', 'show', INDEX], cwd=V.parent))
    archive = Path(index['archive']['path'])
    require(sha256(archive.read_bytes()).hexdigest() == index['archive']['sha256'] == ARCHIVE_SHA,
            'assembly_source_archive_changed')
    indexed = {entry['path']: entry for entry in index['files']}
    members = {}
    with ZipFile(archive) as sealed:
        def member(relative, expected=None):
            name = 'slots/P1/' + relative
            archived = sealed.read(name)
            raw = (SLOT / relative).read_bytes()
            identity = sha256(raw).hexdigest()
            require(raw == archived and indexed[name]['sha256'] == identity
                    and indexed[name]['bytes'] == len(raw) and (expected is None or identity == expected),
                    'assembly_original_member_changed/' + relative)
            members[relative] = {'sha256': identity, 'bytes': len(raw)}
            return raw

        member('native/input.blend', ASSET_SHA)
        terminal = json.loads(member('TERMINAL_SOURCE.json', TERMINAL_SHA))
        binding = json.loads(member('product_full/call_001/SERVICE_RESULT.json'))['binding']
        for path in sorted((SLOT/'native/WIRE').glob('[0-9]*/*.bin')):
            member(path.relative_to(SLOT).as_posix())
    require(terminal['source']['asset_sha256'] == ASSET_SHA and terminal['source']['scale_length'] == 1,
            'wrong_sealed_assembly_units_or_asset')
    history = json.loads(subprocess.check_output(['git', 'show', HISTORICAL_BINDING], cwd=V.parent))
    require(history['source_sha256'] == binding['runtime_source_sha256'] ==
            'ea93acca1a4ba0bcd527f9702657e9180bac05e2cb126e10474fb525b7fa1ca7',
            'wrong_historical_host_installation')
    if history['dependency_root'] not in sys.path:
        sys.path.append(history['dependency_root'])
    capture_reader = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    audit = capture_reader['Audit']()
    captures, commands = capture_reader['decode_captures'](SLOT, history, audit)
    capture = capture_reader['current_capture'](captures, binding, audit)
    meshes = capture['meshes']
    require((len(meshes), sum(len(row['vertices']) for row in meshes), sum(len(row['faces']) for row in meshes))
            == (28, 416, 744) and capture['display_snapshot']['status'] == 'captured',
            'wrong_complete_assembly_scope')
    for mesh, evaluated, display in zip(meshes, terminal['objects'], capture['display_snapshot']['objects'], strict=True):
        require((mesh['name'], mesh['object_id'], mesh['vertices'], mesh['faces'])
                == (evaluated['name'], evaluated['object_id'], evaluated['evaluated']['vertices_world_m'],
                    evaluated['evaluated']['triangles'])
                and capture['host_identity']['object_instances'][mesh['object_id']] == evaluated['instance_id']
                and display['visible_get'] == evaluated['visible_get'],
                'assembly_host_and_terminal_mesh_disagree/' + mesh['name'])
    return capture, {'archive_sha256': ARCHIVE_SHA, 'terminal_sha256': TERMINAL_SHA, 'asset_sha256': ASSET_SHA,
                     'members': members, 'commands': commands, 'objects': 28, 'points': 416, 'triangles': 744}
