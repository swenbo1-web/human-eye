"""Replay three sealed one-byte public witness substitutions without changing any original."""

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
E = run_path(str(HERE/'evidence.py'))
V = E['V']
RECOVERY = E['RECOVERY']
OLD = V/'m1_region_task_first_packet_consumption_holdout_001'
RUNTIME = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001')
QA_RUNTIME = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001')
FROZEN = {
    'recovery':('71059af94b9c01bd7f3f8998a01401114873e9e647b8066c58ad2b0da880281a',
                'a61668ab58b0bf8160eb15838930137547cdb55f29b52d4186c9cea42f5064e7'),
    'old':('2342ecb10d104ee000999b1d0d67e35545cf2516b50a45ac642a7ed6d54b14fc',
           'e4e1ce943c3a0fdbd96100d8fbcb7269b849f62de4146d5743d4d5dfca75c6aa'),
}
require,read,digest = (E[name] for name in ('require','read','digest'))


def bytes_receipt(raw):
    return {'bytes':len(raw),'sha256':digest(raw)}


class OriginalArchive:
    def __init__(self,directory,runtime,kind):
        self.directory = directory
        self.runtime = runtime
        self.index = read(directory/'RAW_INDEX.json')
        self.path = directory/self.index['archive']['name']
        expected_freeze,expected_archive = FROZEN[kind]
        require(digest((directory/'FROZEN.json').read_bytes())==self.index['freeze_sha256']==expected_freeze
                and bytes_receipt(self.path.read_bytes())=={'bytes':self.index['archive']['bytes'],'sha256':expected_archive}
                and self.index['archive']['sha256']==expected_archive,'sealed_original_batch_bytes_changed')
        self.checked = {}

    def take(self,relative):
        member = 'runtime/'+relative
        path = self.runtime/relative
        raw = path.read_bytes()
        with ZipFile(self.path) as original:
            require(original.read(member)==raw and bytes_receipt(raw)==self.index['members'][member],
                    'actual_runtime_original_does_not_match_archive/'+member)
        self.checked[member] = {'path':path.as_posix(),**bytes_receipt(raw)}
        return raw


def take_discovery(archive,label,n,readback_tool):
    base = 'slots/'+label
    slot = archive.runtime/base
    public = [json.loads(line) for line in archive.take(base+'/PUBLIC_REQUESTS.jsonl').splitlines()]
    relative = f'{base}/product_full/call_{n:03d}/SERVICE_RESULT.json'
    producer_raw = archive.take(relative)
    producer_path = archive.runtime/relative
    event, = [row for row in public if row.get('producer_archive') and
              Path(row['producer_archive']['path']).resolve()==producer_path.resolve()]
    require(event['producer_archive']['sha256']==digest(producer_raw),'retained_actual_producer_changed')
    producer = json.loads(producer_raw)
    wire = f"{base}/mcp/rpc_{event['receipt']['index']:02d}"
    tx,rx = (archive.take(wire+name) for name in ('/TX.bin','/RX.bin'))
    require(json.loads(tx)==event['request'] and json.loads(rx)==event['response']
            and event['receipt']['RX_sha256']==digest(rx)
            and json.loads(archive.take(f'{base}/product_calls/call_{n:03d}/RESPONSE.json'))==json.loads(rx),
            'retained_native_discovery_wire_did_not_match_actual_product_call')
    stored = json.loads(archive.take(base+'/SLOT_RESULT.json'))
    publication = json.loads(archive.take(base+'/SLOT_PUBLICATION.json'))
    require(stored['status']==publication['status']=='completed' and stored['closure_verification']['passed']
            and publication['result_sha256']==archive.checked['runtime/'+base+'/SLOT_RESULT.json']['sha256'],
            'sealed_called_slot_did_not_close')
    source = json.loads(archive.take(base+'/TERMINAL_SOURCE.json'))
    owner = f'{base}/owner/tool_{readback_tool:02d}'
    req,reply = (json.loads(archive.take(owner+name)) for name in ('/REQUEST.json','/RESPONSE.json'))
    require(req['params']['name']=='read_images' and req['id']==reply['id'] and not reply['result']['isError'],
            'retained_image_readback_not_real_succeeded_request')
    actual_frames = {frame['image_ref']:frame for frame in producer['frames']}
    attestations = {}
    content = reply['result']['content']
    for i,block in enumerate(content):
        if block['type']!='text':
            continue
        head,_,desc = block['text'].partition('\n')
        ref = head.split()[0]
        image = json.loads(desc)
        original = actual_frames[ref]
        path = Path(image['local_image_path']).resolve(strict=True)
        file = archive.take(path.relative_to(archive.runtime).as_posix())
        png = content[i+1]
        require(path.is_relative_to(slot) and path==Path(original['image_path']).resolve()
                and png['type']=='image' and png['mimeType']=='image/png'
                and base64.b64decode(png['data'],validate=True)==file
                and image['image_sha256']==digest(file)==original['image_sha256'],
                'old_readback_caption_ref_path_or_PNG_not_original')
        attestations[ref] = {'path':path.as_posix(),**bytes_receipt(file)}
    require(list(attestations)==req['params']['arguments']['refs'],'old_readback_ref_order_or_roster_changed')
    return {'slot':slot,'tx':tx,'rx':rx,'producer':producer,'source':source,'readback':attestations,
            'detail':event['request']['params']['arguments']['response_detail']}


def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def mutate_frame_index(raw,proof):
    reply = json.loads(raw)
    body = json.loads(reply['result']['content'][0]['text'])
    target, = [row for row in proof['public_witnesses'] if row['object_name']=='Component_582']
    require(target['frame_index']==1 and target['view_name']=='SCENE' and target['scope_id']!='global',
            'retained_current_local_seen_R_does_not_match_frozen_substitution')
    table = body['witnesses']
    oi,fi = (table['columns'].index(key) for key in ('region_index','frame_index'))
    row, = [entry for entry in table['rows'] if entry[oi]==target['region_index']]
    base = compact(row).encode()
    changed = list(row)
    changed[fi] = 0
    hit = compact(changed).encode()
    require(raw.count(base)==1,'no_unique_single_native_row_to_reassign')
    mutated = raw.replace(base,hit)
    offsets = [i for i,(a,b) in enumerate(zip(raw,mutated,strict=True)) if a!=b]
    require(len(offsets)==1 and raw[offsets[0]:offsets[0]+1]==b'1'
            and mutated[offsets[0]:offsets[0]+1]==b'0','negative_wire_is_not_exact_single_byte_frame_change')
    altered = json.loads(mutated)
    comparable = deepcopy(altered)
    comparable['result']['content'][0]['text'] = reply['result']['content'][0]['text']
    require(comparable==reply,'negative_wire_altered_other_transport_fields_or_PNGs')
    body['witnesses']['rows'][table['rows'].index(row)] = changed
    require(json.loads(altered['result']['content'][0]['text'])==body,
            'negative_wire_altered_other_public_output_fields')
    return mutated,offsets[0]


def qualify_path_table(source,original):
    """Exercise only the independent checker; the sealed historical packet remains unchanged."""
    def edit_paths(entries):
        packet = json.loads(source['rx'])
        body = json.loads(packet['result']['content'][0]['text'])
        body['witness_image_paths'] = {'columns':['frame_index','local_image_path'],'rows':entries}
        packet['result']['content'][0]['text'] = compact(body)
        return packet

    qualified = [[row['frame_index'],source['readback'][row['image_ref']]['path']]
                 for row in original['public_witnesses']]
    props = {'slot':source['slot'],'authoritative_paths':source['readback'],'require_paths':True}
    new = E['verify_public_witnesses']
    accepted = new(edit_paths(qualified),source['producer'],**props)
    require(len(accepted['paths'])==2 and accepted['eligible_unique_path_frame_indices']==[1,2],
            'independent_checker_did_not_accept_two_valid_derived_paths')
    aliases = deepcopy(qualified)
    aliases[0][1] = aliases[0][1].replace('/slots/','/SLOTS/')
    require(aliases[0][1]!=qualified[0][1],'wrong_case_negative_did_not_change_path')
    rejected = []
    for label,rows,reason in (
        ('duplicate_frame',qualified+[qualified[0]],'optional_witness_path_has_duplicate_frame_index'),
        ('global_same_view_instead_of_local',[[0,qualified[0][1]],qualified[1]],
         'optional_witness_path_does_not_refer_to_delivered_complete_local_frame'),
        ('path_points_to_other_local_original',[[1,qualified[1][1]],qualified[1]],
         'optional_witness_path_wrong_or_noncanonical'),
        ('noncanonical_spelling',aliases,'optional_witness_path_wrong_or_noncanonical'),
        ('required_valid_path_was_missing',qualified[:1],'missing_path_for_delivered_complete_local_frame'),
    ):
        try:
            new(edit_paths(rows),source['producer'],**props)
        except ValueError as error:
            require(str(error)==reason,'derived_path_rejected_for_wrong_reason/'+label)
            rejected.append({'case':label,'rejected_for':str(error)})
        else:
            raise ValueError('derived_bad_path_accepted/'+label)
    return {'scope':'synthetic table checker only: genuine archived PNG and paths; no production candidate implied',
            'accepted_original_references':accepted['paths'],'negative_controls':rejected}


def replay(wire_output=None):
    old = run_path(str(RECOVERY/'checks/evidence.py'))
    calibration = run_path(str(RECOVERY/'harness/common.py'))
    product = read(calibration['PRODUCT_BINDING'])
    dependencies = read(calibration['SEAL']/'SHARED_DEPENDENCY.json')
    sys.path[:0] = [product['dependency_root'],dependencies['dependency_root']]
    recovery = OriginalArchive(RECOVERY,RUNTIME,'recovery')
    qa = OriginalArchive(OLD,QA_RUNTIME,'old')
    truth = OLD/'fixture/TRUTH.json'
    cases = {}
    for label,point,n,readback in (('QA',qa,2,3),('QB',recovery,1,3),
                                   ('A1',recovery,1,4),('B1',recovery,1,5)):
        item = take_discovery(point,label,n,readback)
        reply = json.loads(item['rx'])
        valid = E['verify_public_witnesses'](reply,item['producer'])
        archived = {'request_detail':item['detail'],'original_RX':bytes_receipt(item['rx']),
                    'new_normal_validation':valid,'verified_same_slot_original_paths':item['readback']}
        cases[label] = archived
        if label=='QA':
            continue
        mutant,offset = mutate_frame_index(item['rx'],valid)
        mutated = json.loads(mutant)
        passed_old = old['verify_discovery'](item['slot'],mutated,item['producer'],item['source'],truth,expected='brief')
        require(passed_old['passed'] is True,'could_not_reproduce_old_false_acceptance/'+label)
        try:
            E['verify_public_witnesses'](mutated,item['producer'])
        except ValueError as error:
            require(str(error)==E['WITNESS_BINDING_ERROR'],'new_wrong_witness_rejected_for_unrelated_reason/'+label)
        else:
            raise ValueError('new_checker_wrongly_accepted_the_public_witness/'+label)
        archived.update({'wrong_RX':bytes_receipt(mutant),'wire_offset_zero_based':offset,'byte_replacement':'1→0',
                         'old_full_recovery_checker_accepted':True,
                         'new_rejected_for':E['WITNESS_BINDING_ERROR'],
                         'fixed_wire_byte_length_preserved':len(mutant)==len(item['rx'])})
        if wire_output is not None:
            (wire_output/(label+'_ORIGINAL_RX.bin')).write_bytes(item['rx'])
            (wire_output/(label+'_BAD_WITNESS_RX.bin')).write_bytes(mutant)
        if label=='QB':
            archived['optional_path_checker']=qualify_path_table(item,valid)
    return {'passed':True,'source_commit':'19c4333ccf0e135db24edc593edd8a10d78908eb',
            'archived_normal_pass':4,'same_byte_length_mutations':3,'old_false_accepts':3,'new_exact_rejects':3,
            'cases':cases,'checked_archived_members':{**qa.checked,**recovery.checked},
            'scope':'sealed original bytes and explicit derived single-byte controls only',
            'new_Blender_starts':0,'new_model_starts':0,'new_PNG_constructions':0}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path)
    ap.add_argument('--wire-output',type=Path)
    opts = ap.parse_args()
    if opts.wire_output:
        opts.wire_output.mkdir(parents=True)
    output = replay(opts.wire_output)
    if opts.report:
        with opts.report.open('x',encoding='utf8',newline='\n') as out:
            out.write(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({key:output[key] for key in ('passed','archived_normal_pass','old_false_accepts','new_exact_rejects')}))
