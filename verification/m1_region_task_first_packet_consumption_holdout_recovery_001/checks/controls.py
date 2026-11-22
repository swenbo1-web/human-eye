"""Replay the sealed QA once and challenge its corrected scope lookup offline."""

import argparse
from copy import deepcopy
from pathlib import Path
from runpy import run_path
import sys
import traceback
from zipfile import ZipFile
import json


CHECK = Path(__file__).resolve().parent
OLD = CHECK.parents[1] / 'm1_region_task_first_packet_consumption_holdout_001'
OLD_SLOT = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001/slots/QA')
FREEZE_SHA = '2342ecb10d104ee000999b1d0d67e35545cf2516b50a45ac642a7ed6d54b14fc'
ZIP_SHA = 'e4e1ce943c3a0fdbd96100d8fbcb7269b849f62de4146d5743d4d5dfca75c6aa'
QA_SHA = '60b8226ac165ff5d0086833ed3f7e21571fb4706275b20dec9ab99527bdfda9e'
E = run_path(str(CHECK / 'evidence.py'))
require, read, digest, pin = (E[name] for name in ('require', 'read', 'digest', 'pin'))


def verify_original_seal(slot):
    freeze = pin(OLD / 'FROZEN.json')
    index_path = OLD / 'RAW_INDEX.json'
    index = read(index_path)
    zip_path = OLD / index['archive']['name']
    require(freeze['sha256'] == index['freeze_sha256'] == FREEZE_SHA
            and pin(zip_path)['sha256'] == index['archive']['sha256'] == ZIP_SHA,
            'frozen_original_qualification_archive_changed')
    original = read(slot / 'SLOT_RESULT.json')
    publication = read(slot / 'SLOT_PUBLICATION.json')
    require(publication['result_sha256'] == pin(slot / 'SLOT_RESULT.json')['sha256'] == QA_SHA
            and original['freeze_sha256'] == FREEZE_SHA
            and slot.resolve() == OLD_SLOT.resolve()
            and not (slot.parent.parent / 'preflight/QA_CLOSED_GATE.json').exists(),
            'frozen_QA_publication_or_original_gate_changed')
    members = index['members']
    names = ['SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'RUNTIME_CLOSE.json', 'QUALIFICATION_PENDING.json',
             'initial_capture/TERMINAL_SOURCE.json', 'TERMINAL_SOURCE.json', 'DEVICE_EVIDENCE.json']
    names.extend(f'client/call_{n:02d}/{name}' for n in range(1,6)
                 for name in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
    names.extend(f'product_full/call_{n:03d}/SERVICE_RESULT.json' for n in range(1,4))
    checked = []
    with ZipFile(zip_path) as archive:
        require(len(members) == index['member_count'] and set(archive.namelist()) == set(members),
                'original_qualification_archive_roster_changed')
        for name in names:
            member = 'runtime/slots/QA/' + name
            raw = archive.read(member)
            receipt = members[member]
            require((digest(raw),len(raw)) == (receipt['sha256'],receipt['bytes'])
                    and raw == (slot / name).read_bytes(), 'old_qualification_raw_member_changed/'+name)
            checked.append({'archive_member':member,**receipt})
    return {'freeze':freeze,'ZIP':pin(zip_path),'index':pin(index_path),'raw_member_pins':checked}


def reproduce_old(slot, raw):
    old = run_path(str(OLD / 'qualification/closed.py'))['verify']
    try:
        old(slot, raw)
    except ValueError as error:
        terminal = traceback.extract_tb(error.__traceback__)[-1]
        require(str(error) == 'not enough values to unpack (expected 1, got 0)'
                and terminal.name == 'verify_discovery' and 'observation, =' in terminal.line,
                'original_gate_failure_did_not_reproduce_exactly')
        return {'message':str(error),'original_line':terminal.lineno,'original_statement':terminal.line}
    raise ValueError('original_gate_must_still_fail')


def change(container, **kwargs):
    container.update(kwargs)


def mutations(producer):
    """Change only archived producer witness structures for deterministic negative tests."""
    target, = [row for row in producer['facts']['region_task']['rows'] if row['object_name']=='Component_582']
    witness = target['complete_witness']
    identity = witness['frame_identity']
    globe, = [row for row in producer['frames'] if row['scope_id']=='global' and row['view_name']=='SCENE']
    require(globe['frame_identity']!=identity and witness['view_name']=='SCENE',
            'real_same_named_different_scope_control_absent')

    def construct(name, mutation, reason):
        p,w = deepcopy(producer),deepcopy(witness)
        scope, = [item for item in p['scopes'] if item['scope_id']==w['scope_id']]
        frame, = [item for item in p['frames'] if item['frame_identity']==identity]
        observation, = [item for item in scope['facts']['observations'] if item['frame_identity']==identity]
        obs,refs = scope['facts']['observations'],scope['frame_refs']
        pixel = observation['pixel_rows'][w['pixel_row_index']]
        mutation(p,w,scope,frame,observation,obs,refs,pixel)
        try:
            E['scoped_witness_pixel'](p,w,target['roi_id'])
        except ValueError as error:
            require(str(error)==reason,'actual_negative_rejected_for_wrong_reason/'+name+'/'+str(error))
            return {'case':name,'rejected_for':str(error)}
        raise ValueError('mutated_scope_or_frame_was_accepted/'+name)

    cases = [
        ('same_named_global_scope_retains_local_frame',
         lambda p,w,*_:change(w,scope_id='global'),'witness_frame_not_uniquely_registered_in_scope'),
        ('same_named_global_frame_retains_local_scope',
         lambda p,w,*_:change(w,frame_identity=globe['frame_identity']),'witness_frame_not_uniquely_registered_in_scope'),
        ('missing_selected_scope',lambda p,w,s,*_:p['scopes'].remove(s),'witness_scope_missing_or_ambiguous'),
        ('duplicate_selected_scope',lambda p,w,s,*_:p['scopes'].append(deepcopy(s)),'witness_scope_missing_or_ambiguous'),
        ('scope_revision_changed',lambda p,w,s,*_:change(s['binding']['capture_state'],revision=300),
         'witness_scope_capture_generation_mismatch'),
        ('scope_document_epoch_changed',lambda p,w,s,*_:change(s['binding'],document_epoch='0'*64),
         'witness_scope_capture_generation_mismatch'),
        ('scope_capture_absent',lambda p,w,s,*_:change(s['binding'],capture_state=None),
         'witness_scope_capture_generation_mismatch'),
        ('wrong_local_parent',lambda p,w,s,*_:change(s['binding'],parent_binding_sha256='0'*64),
         'witness_local_parent_binding_mismatch'),
        ('frame_unregistered_in_scope',lambda p,w,s,f,o,a,refs,*_:refs.clear(),
         'witness_frame_not_uniquely_registered_in_scope'),
        ('duplicate_frame_ref_in_scope',lambda p,w,s,f,o,a,refs,*_:refs.append(identity),
         'witness_frame_not_uniquely_registered_in_scope'),
        ('duplicate_producer_frame',lambda p,w,s,f,*_:p['frames'].append(deepcopy(f)),
         'witness_producer_frame_missing_or_ambiguous'),
        ('missing_producer_frame',lambda p,w,s,f,*_:p['frames'].remove(f),
         'witness_producer_frame_missing_or_ambiguous'),
        ('wrong_original_reference',lambda p,w,*_:change(w,image_ref=globe['image_ref']),
         'witness_frame_ref_view_or_binding_mismatch'),
        ('wrong_witness_view',lambda p,w,*_:change(w,view_name='TOP'),'witness_frame_ref_view_or_binding_mismatch'),
        ('missing_scoped_observation',lambda p,w,s,f,o,a,*_:a.remove(o),'witness_scoped_observation_missing_or_ambiguous'),
        ('duplicate_scoped_observation',lambda p,w,s,f,o,a,*_:a.append(deepcopy(o)),
         'witness_scoped_observation_missing_or_ambiguous'),
        ('same_named_wrong_png',lambda p,w,s,f,o,*_:change(o,image_sha256=globe['image_sha256']),
         'witness_scoped_observation_ref_view_or_png_mismatch'),
        ('same_named_wrong_image_path',lambda p,w,s,f,o,*_:change(o,image_path=globe['image_path']),
         'witness_scoped_observation_ref_view_or_png_mismatch'),
        ('observation_view_changed',lambda p,w,s,f,o,*_:change(o,view_name='TOP'),
         'witness_scoped_observation_ref_view_or_png_mismatch'),
        ('wrong_roi',lambda p,w,s,f,o,a,refs,pix:change(pix,roi_id='wrong_roi'),
         'witness_pixel_row_roi_view_or_readability_mismatch'),
        ('pixel_row_nonreadable',lambda p,w,s,f,o,a,refs,pix:change(pix,readable=False),
         'witness_pixel_row_roi_view_or_readability_mismatch'),
    ]
    for label,index in (('negative',-1),('too_large',100000),('boolean',False),('float',0.0)):
        cases.append(('pixel_index_'+label,lambda p,w,*_,i=index:change(w,pixel_row_index=i),
                      'witness_pixel_row_index_invalid'))
    out = [construct(*case) for case in cases]
    fixture = deepcopy(producer)
    fixture['facts']['observations'].clear()
    pixel = E['scoped_witness_pixel'](fixture,witness,target['roi_id'])
    require(pixel['visible_surface_pixels'] == 49929 and pixel['contrasting_boundary_pixels'] == 926,
            'local_producer_compatibility_still_depends_on_global_observation')
    return out,{'top_global_removed_still_returns_local':True,'original_pixel_counts':[49929,926]}


def replay(slot=OLD_SLOT):
    """Replay the old gate only; record the provenance of the five actual calls."""
    slot = Path(slot).resolve(strict=True)
    source = verify_original_seal(slot)
    raw = read(slot/'SLOT_RESULT.json')
    calibration = run_path(str(OLD/'harness/common.py'))
    product = read(calibration['PRODUCT_BINDING'])
    dependencies = read(calibration['SEAL']/'SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(OLD/'harness'),str(OLD/'qualification'),
                    product['dependency_root'],dependencies['dependency_root']]
    original_failure = reproduce_old(slot,raw)
    fixed = E['verify_qualification'](slot,raw)
    producer = read(slot/'product_full/call_001/SERVICE_RESULT.json')
    rejected, independent = mutations(producer)
    # Swap the two true same-name PNG byte blocks, preserving their metadata.
    altered = deepcopy(read(slot/'client/call_02/RESPONSE.json'))
    content = altered['result']['content']
    content[1],content[2] = content[2],content[1]
    try:
        E['verify_discovery'](slot,altered,producer,read(slot/'TERMINAL_SOURCE.json'),OLD/'fixture/TRUTH.json',expected='full')
    except ValueError as error:
        require(str(error)=='actual_discovery_image_block_frame_or_path_mismatch',
                'raw_same_view_PNG_swap_not_rejected_for_expected_reason/'+str(error))
        rejected.append({'case':'swap_two_real_same_name_PNG_blocks','rejected_for':str(error)})
    else:
        raise ValueError('raw_same_view_PNG_swap_accepted')
    return {'passed':True,'scope':'offline replay; no original gate or denominator was changed',
            'source_archive':source,'original_gate_reproduced':original_failure,
            'actual_closed_full_brief_and_measurement':fixed,'negative_controls':rejected,
            'passed_negative_controls':len(rejected),'independence_from_global_observation':independent,
            'new_Blender_starts':0,'new_model_starts':0}


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--old-slot',type=Path,default=OLD_SLOT)
    arguments.add_argument('--output',type=Path)
    options = arguments.parse_args()
    report = replay(options.old_slot)
    if options.output:
        with options.output.open('x',encoding='utf8',newline='\n') as file:
            file.write(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'passed':report['passed'],'negative_controls':report['passed_negative_controls'],
                      'actual_original_wires':len(report['actual_closed_full_brief_and_measurement']['outer_calls'])}))
