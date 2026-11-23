"""One fixed two-arm visual-wire replay and, after the byte gate, one cold pair."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from time import perf_counter_ns
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m4_source_region_selective_visual_capture_001'
PRIOR_COMMIT = '72eb34df7d662a3081febf02bf58f39e736cd49a'
PRODUCT_A = 'ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'
PRODUCT_B_PARENT = '85a5501ba8e03d29340ef9a94e38ae1a2849330f'
ROOT = Path('D:/he_m4_source_region_visual_wire_reuse_001').resolve()
OLD_ROOT = Path('D:/he_m4_source_region_selective_visual_capture_001').resolve()
OLD_INDEX_SHA = 'd4fd024c2ac5d04f2b8550028a84a12ed721b6e828f57d7e5ba85897dabff2be'
OLD_ARCHIVE_SHA = 'f2a8436258ccf1096b38f7105ecabf6c89f30b8c80491dc717f3f7723b16220c'
SAME_BOX = ROOT/'preflight/same-box'
B_BINDING = ROOT/'candidate_install/PRODUCT_RUN_BINDING.json'
CONTROL_NAMES = ('WIRE_CONTROLS.json','HOST_WIRE_CONTROLS.json','SCORE_CONTROLS.json','COMPATIBILITY.json')


def git(*args):
    return subprocess.check_output(['git','-C',str(HERE.parents[1]),*args])


def check_prior_sources():
    names = ['experiment.py','cold_native.py','stdio_entry.py','replay.py','score.py','build.py']
    files = [PRIOR/name for name in names]
    for path in files:
        rel = path.relative_to(HERE.parents[1]).as_posix()
        if path.read_bytes()!=git('show',PRIOR_COMMIT+':'+rel):
            raise ValueError('prior_source_blob_changed/'+rel)
    return files


check_prior_sources()
trial = run_path(str(PRIOR/'experiment.py'))
shared = trial['run_slot'].__globals__
load,save,need,pin = (shared[n] for n in ('load','save','need','pin'))
BASE_BINDING,ASSET,ORDER,PYTHON = (shared[n] for n in ('BASE_BINDING','ASSET','ORDER','PYTHON'))
reference_inputs = shared['reference_inputs']
old_assert_install = shared['assert_install']


def verify_pair(a,b,reference=None):
    program = run_path(str(HERE/'score.py'))
    return program['verify_pair'](a,b,reference)


def assert_install(arm):
    path,binding = old_assert_install(arm)
    selected = binding['preparation_git']
    if arm=='A':
        need(selected==PRODUCT_A,'standard_baseline_wrong_commit')
    else:
        need(git('rev-parse',selected+'^').decode().strip()==PRODUCT_B_PARENT,
             'visual_wire_candidate_wrong_parent')
    return path,binding


# Keep the identical stdio, timeout, source-capture, native shutdown and
# publication path from the frozen paired trial.
native = run_path(str(HERE/'cold_native.py'))
shared.update(HERE=HERE, ROOT=ROOT, B_BINDING=B_BINDING, NativeSession=native['NativeSession'],
              verify_pair=verify_pair, assert_install=assert_install)
run_pair,run_slot = shared['run_pair'],shared['run_slot']


def decode_host_reply(blob):
    reply = json.loads(blob)
    need(reply.get('status')=='success' and reply['result']['executed'] is True,
         'unexpected_native_host_reply')
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    envelopes = [json.loads(line[len(prefix):]) for line in reply['result']['result'].splitlines()
                 if line.startswith(prefix)]
    need(len(envelopes)==1 and 'result' in envelopes[0],'native_host_envelope_missing')
    return envelopes[0]['result']


def business_rows(slot):
    index_path = slot/'native/WIRE/INDEX.json'
    index = load(index_path)
    need([r['sequence'] for r in index] in ([1,2,3],[1,2,3,4])
         and all(r['response_sendall_completed'] for r in index),
         'actual_native_wire_trace_missing_or_unclosed')
    shots = load(slot/'SHOOT.json')['queries']
    rows = []
    for i,shot in enumerate(shots,1):
        wire = slot/'native/WIRE'/f'{i:03}'
        tx,rx = wire/'REQUEST.bin',wire/'RESPONSE.bin'
        need(tx==Path(shot['host_tx_path']) and rx==Path(shot['host_rx_path'])
             and tx.stat().st_size==index[i-1]['request_bytes']
             and rx.stat().st_size==index[i-1]['response_attempted_bytes'],
             'native_wire_slot_binding_changed')
        rows.append(dict(label=shot['label'],tx=tx.stat().st_size,rx=rx.stat().st_size,
                         request=pin(tx),response=pin(rx)))
    need(len(rows)==2,'two_admitted_business_requests_required')
    return rows


def previous_business_rows():
    index_path = OLD_ROOT/'sealed/RAW_INDEX.json'
    archive = OLD_ROOT/'sealed/ORIGINAL_RUNTIME.zip'
    need(pin(index_path)['sha256']==OLD_INDEX_SHA and pin(archive)['sha256']==OLD_ARCHIVE_SHA,
         'sealed_previous_visual_experiment_changed')
    index = load(index_path)
    result = {}
    with ZipFile(archive) as sealed:
        for arm in ('A','B'):
            rows = []
            for i,label in enumerate(ORDER,1):
                triplet = {}
                for field,name in (('tx','REQUEST.bin'),('rx','RESPONSE.bin')):
                    rel = f'slots/{arm}/native/WIRE/{i:03}/{name}'
                    artifact = OLD_ROOT/rel
                    blob = artifact.read_bytes()
                    entry = pin(artifact,blob)
                    need(blob==sealed.read(rel) and all(entry[k]==index['members'][rel][k]
                                                        for k in ('bytes','sha256')),
                         'previous_native_wire_archive_member_changed')
                    triplet.update({field:len(blob),'request' if field=='tx' else 'response':entry})
                rows.append(dict(label=label,**triplet))
            result[arm] = rows
    return result


def total(rows):
    return sum(row['tx']+row['rx'] for row in rows)


def net_gate(root):
    result = load(root/'RESULT.json')
    need(result['passed'] and result['offline'],'offline_quality_must_pass_before_byte_gate')
    old = previous_business_rows()
    current = {arm:business_rows(root/'slots'/arm) for arm in ('A','B')}
    totals = {'offline_A':total(current['A']),'offline_B':total(current['B']),
              'prior_formal_A':total(old['A']),'prior_formal_B':total(old['B'])}
    candidate = totals['offline_B']
    return {'passed':candidate<min(totals['offline_A'],totals['prior_formal_B']),
            'criterion':'current B actual two-request native TX+RX below current A and previous formal B',
            'totals':totals,'online_source_and_wire_escaping_included':True,
            'gain_vs_offline_A_bytes':totals['offline_A']-candidate,
            'gain_vs_prior_formal_B_bytes':totals['prior_formal_B']-candidate,
            'rows':current,'prior_formal_rows':old}


def same_box_result(slot,reference):
    program = run_path(str(HERE/'score.py'))
    old = program['old']
    publication_check, mcp_exchange, checked_path = (getattr(old,name) for name in
                                                      ('publication_check','mcp_exchange','checked_path'))
    transcript = program['ScopedTranscript']()
    manifest = load(slot/'SHOOT.json')
    need(manifest['offline'] and manifest['label']=='B'
         and tuple(x['label'] for x in manifest['queries'])==('M21','M21'),'same_box_transcript_changed')
    terminal = load(checked_path(slot,manifest['terminal_path']))
    closed = publication_check(slot,manifest,terminal,load(checked_path(slot,manifest['publication_path'])))
    shots = manifest['queries']
    need(shots[0]['args']==shots[1]['args'],'same_box_mcp_request_must_be_exact_repeat')
    old_png = reference['M21']['png'].read_bytes()
    payloads = []
    producers = []
    png_pins = []
    mcp_pins = []
    for shot in shots:
        png = checked_path(slot,shot['png_path'])
        png_bytes = png.read_bytes()
        need(png_bytes==old_png,'same_box_original_PNG_changed')
        tx,rx=(checked_path(slot,shot[k]) for k in ('mcp_tx_path','mcp_rx_path'))
        mcp_exchange(tx.read_bytes(),rx.read_bytes(),shot['args'],png_bytes)
        wire_tx,wire_rx=(checked_path(slot,shot[k]) for k in ('host_tx_path','host_rx_path'))
        sent,payload = transcript.exchange(wire_tx.read_bytes(),wire_rx.read_bytes())
        need(sent['command']=='capture_source_region_visual','same_box_native_private_route_changed')
        producers.append(load(checked_path(slot,shot['producer_path'])))
        payloads.append(payload)
        png_pins.append(pin(png))
        mcp_pins.append({'request':pin(tx),'response':pin(rx)})
    first,second = transcript.receipts
    need(payloads[0]['retained_ordinals']==payloads[1]['retained_ordinals']
         and first['camera_sha256']==second['camera_sha256']
         and first['generation']==second['generation'] and first['generation'] is not None
         and not first['metadata_referenced'] and second['metadata_referenced']
         and first['kept_meshes']==second['kept_meshes']==4
         and first['referenced_original_ordinals']==[]
         and second['referenced_original_ordinals']==payloads[1]['retained_ordinals']
         and second['sent_vertices']==second['sent_triangles']==0,
         'same_box_did_not_actualize_metadata_and_all_four_resource_hits')
    need(producers[0]['task_result']['facts']==producers[1]['task_result']['facts'],
         'same_box_measurement_facts_changed')
    rows = business_rows(slot)
    need(rows[1]['rx']<rows[0]['rx'],'same_box_response_not_smaller_with_proof')
    return {'passed':True,'offline':True,'same_box_mcp_requests':2,'original_png_equal':True,
            'same_camera_digest':True,'same_measurement_facts':True,'metadata_reused':True,
            'current_resource_hits':4,'slot':str(slot),'closure':closed,
            'rows':rows,'png':png_pins,'mcp':mcp_pins,'wire_receipts':transcript.receipts}


def frozen_inputs(preflight):
    files = [*HERE.glob('*.py'),*check_prior_sources(),HERE/'PLAN.md',
             *(shared[k] for k in ('FIXTURE','TERMINAL','RETAINED','METER','DEVICE','BASE_BINDING','B_BINDING','BLENDER','PYTHON')),
             preflight/'RESULT.json',preflight/'NET_GATE.json',SAME_BOX/'RESULT.json',ROOT/'OLD_CUSTODY_AND_WIRE.json',
             *(ROOT/name for name in CONTROL_NAMES)]
    need(all(load(ROOT/name)['passed'] is True for name in CONTROL_NAMES),'required_control_not_passed')
    controls=load(ROOT/'WIRE_CONTROLS.json')
    for row in controls['wire_receipts'].values():
        index=Path(row['path'])
        need(pin(index)==row,'installed_wire_control_index_changed')
        for call in load(index)['calls']:
            for key in ('request','response'):
                evidence=call[key]
                need(pin(Path(evidence['path']))==evidence,'installed_wire_control_bytes_changed')
    return [pin(path) for path in sorted(set(files))]


def gate_passed(preflight,reference):
    result=load(preflight/'RESULT.json')
    need(result['passed'] and result['offline']
         and verify_pair(preflight/'slots/A',preflight/'slots/B',reference)==result['score'],
         'closed_offline_quality_not_reproducible')
    gate=load(preflight/'NET_GATE.json')
    need(gate['passed'] and net_gate(preflight)==gate,'real_offline_net_wire_bytes_did_not_drop')
    repeat=load(SAME_BOX/'RESULT.json')
    need(repeat['passed'] and same_box_result(SAME_BOX/'slots/B',reference)==repeat,
         'closed_same_box_evidence_not_reproducible')


def assert_freeze(reference=None):
    reference=reference if reference is not None else reference_inputs()
    frozen=load(ROOT/'FREEZE.json')
    preflight=Path(frozen['preflight'])
    need(frozen['files']==frozen_inputs(preflight),'frozen_run_inputs_changed')
    gate_passed(preflight,reference)


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('offline','same-box','freeze','cold','formal'))
    parser.add_argument('arg',nargs='?')
    args=parser.parse_args()
    need(Path(sys.executable).resolve()==PYTHON
         and pin(PYTHON)['sha256']==shared['PYTHON_SHA']
         and sys.flags.isolated and sys.dont_write_bytecode,'fixed_interpreter')
    reference=reference_inputs()
    if args.action=='same-box':
        need(args.arg is None,'same_box_has_one_fixed_namespace')
        SAME_BOX.mkdir(parents=True,exist_ok=False)
        previous=shared['ORDER']
        shared['ORDER']=('M21','M21')
        try:
            outcome=run_slot(SAME_BOX,'B',reference,offline=True)
            need(outcome['passed'] and outcome['safe'],'same_box_real_TCP_slot_failed')
        finally:
            shared['ORDER']=previous
        result=same_box_result(SAME_BOX/'slots/B',reference)
        save(SAME_BOX/'RESULT.json',result)
        return 0
    if args.action in ('offline','freeze'):
        tag=args.arg or 'paired'
        need(tag!='same-box' and tag.isascii() and tag.replace('-','').isalnum(),'private_preflight_namespace')
        sandbox=ROOT/'preflight'/tag
        if args.action=='offline':
            sandbox.mkdir(parents=True,exist_ok=False)
            if not run_pair(sandbox,True,reference):
                return 1
            gate=net_gate(sandbox)
            save(sandbox/'NET_GATE.json',gate)
            return int(not gate['passed'])
        gate_passed(sandbox,reference)
        save(ROOT/'FREEZE.json',{'preflight':str(sandbox),'files':frozen_inputs(sandbox),'at_ns':perf_counter_ns()})
        return 0
    assert_freeze(reference)
    exact=pin(ROOT/'FREEZE.json')
    if args.action=='cold':
        need(args.arg in ('A','B'),'cold_arm_required')
        mark=run_slot(ROOT,args.arg,reference,reservation_only=True)
        mark['freeze']=exact
        save(ROOT/f'COLD_{args.arg}.json',mark)
        return 0
    need(args.arg is None,'formal_has_one_fixed_pair')
    for arm in ('A','B'):
        gate=load(ROOT/f'COLD_{arm}.json')
        need(gate['at_appointment_boundary'] and gate['actual_Blender']==0 and gate['label']==arm
             and gate['freeze']==exact,'true_cold_appointment_proof_required')
    save(ROOT/'FORMAL_START.json',{'freeze':exact,'pid':__import__('os').getpid(),
                                 'started_ns':perf_counter_ns(),'order':['A','B']})
    return int(not run_pair(ROOT,False,reference))


if __name__=='__main__':
    raise SystemExit(main())
