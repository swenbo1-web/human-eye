"""Check current geometry, exact scope ownership, actual pixels and original paths."""

from functools import lru_cache
import json
from pathlib import Path
from runpy import run_path
from types import FunctionType, SimpleNamespace

HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
RECOVERY = V/'m1_region_task_first_packet_consumption_holdout_recovery_001/checks/evidence.py'
WITNESS = V/'m1_region_task_witness_image_path_001/checks/evidence.py'
DENSE_NATIVE = V/'perf050_dense_micro_surface_holdout_001/qualification/native.py'
ORACLE = V/'m4_cross_scale_discovery_001/oracle/check_saved.py'
TRUTH = V/'m1_region_task_first_packet_consumption_holdout_001/fixture/TRUTH.json'
INSTALL = V/'m3_whole_object_rounded_witness_compat_001/install/PRODUCT_RUN_BINDING.json'


@lru_cache(maxsize=None)
def module(path):
    return run_path(str(path))


E = module(RECOVERY)
W = module(WITNESS)
require,read,pin,digest = (E[key] for key in ('require','read','pin','digest'))


@lru_cache(maxsize=1)
def truth():
    require(digest(TRUTH.read_bytes())=='b44d0a75376667b7abf8c12d023dd67180086b5fba77653e3972edd84f7ee5f8',
            'sealed_dense_truth_sha_changed')
    return E['normalize_truth'](TRUTH)


def current_capture(slot, binding, source, *, capture=None, installed=None):
    installed = read(INSTALL) if installed is None else installed
    oracle = module(ORACLE)
    audit = oracle['Audit']()
    if capture is None:
        captures,_ = oracle['decode_captures'](slot,installed,audit)
        capture = oracle['current_capture'](captures,binding,audit)
    require(capture['capture_state']==binding['capture_state']
            and capture['revision']==binding['scene_revision']
            and capture['host_identity']['document_epoch']==binding['document_epoch'],
            'closed_product_source_is_not_current_capture')
    oracle['source_binding_checks'](capture,binding,installed,audit)
    rows = E['verify_source'](source,truth())
    meshes = capture['meshes']
    instances = capture['host_identity']['object_instances']
    require(len(meshes)==len(rows) and {mesh['name'] for mesh in meshes}==rows.keys(),
            'product_discovery_capture_full_current_source_required')
    for mesh in meshes:
        row = rows[mesh['name']]
        require(mesh['object_id']==row['object_id'] and instances[row['object_id']]==row['instance_id']
                and mesh['vertices']==row['evaluated']['vertices_world_m']
                and mesh['faces']==row['evaluated']['triangles'],
                'product_current_evaluated_mesh_binding_changed/'+mesh['name'])
    return capture


def verify_product_frame(slot, row, target, producer, source, *, capture=None, installed=None, reply=None):
    capture = current_capture(slot,producer['binding'],source,capture=capture,installed=installed)
    checker = E['_RECOVERY']['verify_frame_proof']
    return checker(slot,row,producer,capture,source,target,truth(),public_read=reply)


def verify_product(slot, reply, producer, source, *, readback=None, require_paths=True, capture=None, installed=None):
    """Validate the compact public packet against its *own* producer, then qualify pixels."""
    slot = Path(slot).resolve(strict=True)
    # Resolve only product frames inventoried by the current owning device. Captions
    # from an actual readback are reconciled below as an independent second path.
    device = read(slot/'DEVICE_EVIDENCE.json')
    require(device['asset_sha256']==truth()['asset']['sha256'] and device['label']==slot.name,
            'product_frame_manifest_not_current_slot_or_asset')
    registered = {row['ref']:row for row in device['frames']}
    require(len(registered)==len(device['frames']),'duplicate_owned_frame_reference')
    paths = {}
    for frame in producer['frames']:
        row = registered[frame['image_ref']]
        require(row['origin']=='product' and row['frame_identity']==frame['frame_identity']
                and row['scope_id']==frame['scope_id'] and row['view_name']==frame['view_name']
                and row['PNG_sha256']==frame['image_sha256']
                and Path(row['PNG']).resolve(strict=True)==Path(frame['image_path']).resolve(strict=True),
                'product_path_registry_not_own_original_frame')
        paths[frame['image_ref']] = pin(row['PNG'],slot)
    public = W['verify_public_witnesses'](reply,producer,slot=slot,authoritative_paths=paths,
                                           require_paths=require_paths)
    original = E['verify_discovery']
    namespace = dict(original.__globals__,
                     producer_capture=lambda folder,binding,native:current_capture(
                         folder,binding,native,capture=capture,installed=installed))
    checked = FunctionType(original.__code__,namespace,original.__name__,
                           original.__defaults__,original.__closure__)
    checked.__kwdefaults__ = original.__kwdefaults__
    proof = checked(slot,reply,producer,source,truth(),expected='brief')
    proof['witness_paths'] = public['paths']
    proof['scoped_public_witnesses'] = public['public_witnesses']
    if readback is not None:
        refs = {item['ref'] for item in proof['witnesses'].values()}
        frames = [row for row in proof['delivered_frames'] if row['image_ref'] in refs]
        proof['readback'] = E['verify_readback'](slot,readback,frames)
        for row in public['paths']:
            require(proof['readback'][row['image_ref']]['PNG']==paths[row['image_ref']],
                    'explicit_readback_not_same_first_packet_PNG')
    return proof


def verify_native_frame(slot, row, target, source, *, reply=None):
    consumer = SimpleNamespace(runtime=SimpleNamespace(device=SimpleNamespace(by_ref={row['ref']:row})))
    return module(DENSE_NATIVE)['prove_image'](slot,consumer,row['ref'],target,content=reply,
                                               source=source,geometry=truth())


def verify_measurement(reply, producer, source, *, parent_binding=None):
    return E['verify_measurement'](reply,producer,producer['binding'] if parent_binding is None else parent_binding,
                                    source,truth())
