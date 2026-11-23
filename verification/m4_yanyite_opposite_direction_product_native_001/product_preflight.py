"""Verify the installed evidence endpoint with the original closed Blender capture."""

import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import inspect
import json
from pathlib import Path
from runpy import run_path
import sys
from types import FunctionType
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
PRIOR = V/'m1_yanyite_foot_region_image_evidence_consumption_001'
FOOT = run_path(str(PRIOR/'product_preflight.py'))
CURVED, OLD, LOW = (FOOT[k] for k in ('CURVED','OLD','LOW'))
require, read, pin, git = (FOOT[k] for k in ('require','read','pin','git'))
PLAN = 'f555c10cd9a85dbeeeb9d635e2f29f5f26639863:docs/M4_YANYITE_OPPOSITE_DIRECTION_PRODUCT_NATIVE_001_PLAN.md'
RUN = Path('D:/he_m4_yanyite_opposite_direction_product_native_001/preflight').resolve()
HISTORY = Path('D:/he_m1_yanyite_foot_region_image_evidence_consumption_001').resolve()
REGISTER = '81341af1d1ba5abe85b4e83dd0097a161b63b9b2'
SLOT = HISTORY/'slots/B1'
BINDINGS = {'B':FOOT['BINDINGS']['B']}
TERMINAL_SHA = 'f52fc746cea933725ffe5a0c7602b2893914c331b427b83366259b283de1f5fb'
BOXES = {
    'negative_y': {'min':[-.08,-.112,0.], 'max':[.08,-.09,.05]},
    'positive_y': {'min':[-.08,.085,0.], 'max':[.08,.105,.05]},
}
EXPECTED = {
    'negative_y': (301,225,.8884277344390303,'c5094b937cdc4e22d516efe7cfca999b6ed36fa22956038b693e2d848b60310d',
                   'RIGHT',9126,72,(249,257,6098)),
    'positive_y': (136,107,.8952636703382715,'c35941e6477bef1347e6e034b0526f792bba981cdc364da2a1b3d969a934eab5',
                   'SCENE',20085,54,(217,388,29762)),
}


def inputs(arm):
    path, register, product, source, wheel = BINDINGS[arm]
    binding = read(path)
    require(path.read_bytes()==git('show',register+':'+path.relative_to(V.parent).as_posix())
            and (binding['preparation_git'],binding['source_sha256'],binding['wheel_sha256'])==(product,source,wheel)
            and len(binding['source_manifest'])==143 and pin(binding['wheel_path'])['sha256']==wheel,
            'fixed_evidence_install_changed')
    published = PRIOR/'RESULT.json'
    require(published.read_bytes()==git('show',REGISTER+':'+published.relative_to(V.parent).as_posix()),
            'foot_register_is_not_the_frozen_publication')
    archive_index, archive_path = HISTORY/'sealed/RAW_INDEX.json',HISTORY/'sealed/ORIGINAL_RUNTIME.zip'
    index = read(archive_index)
    require(index['archive']==pin(archive_path)==read(published)['raw_archive']['archive']
            and index['member_count']==len(index['members'])==1184,'foot_seal_changed')
    pinned = [pin(p) for p in (Path(__file__),PRIOR/'product_preflight.py',published,archive_index,archive_path,
                                path,Path(binding['wheel_path']),LOW['ORACLE'],*CURVED['source_paths']())]
    with ZipFile(archive_path) as archive:
        def take(filename):
            found = CURVED['pinned_member'](HISTORY,archive,index,filename)
            pinned.append(found)
            return Path(found['path']).read_bytes()

        raw_terminal = take(SLOT/'TERMINAL_SOURCE.json')
        terminal = json.loads(raw_terminal)
        score = json.loads(take(SLOT/'SLOT_RESULT.json'))
        require(len(raw_terminal)==9_614_533 and sha256(raw_terminal).hexdigest()==TERMINAL_SHA
                and terminal['source']['asset_sha256']==read(published)['asset_sha256']
                and score['status']=='completed' and score['closure_verification']['passed']
                and score['independent_before_after']['passed'],'original_foot_slot_source_unbound')
        take(SLOT/'mcp/HELD_CLOSE.json')
        take(SLOT/'INSTALLED_TOOLS.json')
        native_index = json.loads(take(SLOT/'native/WIRE/INDEX.json'))
        native = run_path(str(OLD['INPUTS']))['recorded_delta']
        txs,deltas = [],[]
        for number,key,count in ((2,'003',2),(3,'004',0)):
            owner = SLOT/'product_calls'/f'call_{number:03d}'
            receipt = json.loads(take(owner/'RECEIPT.json'))
            wire = SLOT/'mcp'/f"rpc_{receipt['index']:02d}"
            tx,rx = (take(wire/name) for name in ('TX.bin','RX.bin'))
            sent,reply = json.loads(tx),json.loads(rx)
            producer = json.loads(take(SLOT/'product_full'/f'call_{number:03d}'/'SERVICE_RESULT.json'))
            capture, _ = native(SLOT,key,count,native_index,take)
            require(sent==json.loads(take(owner/'REQUEST.json')) and receipt['RX_sha256']==sha256(rx).hexdigest()
                    and not reply['result']['isError'] and sent['id']==reply['id']==f'observe-{number}'
                    and capture['capture']['capture_state']==producer['binding']['capture_state']
                    and OLD['args_of'](sent)['query']['requested_facts']==['surface_proximity'],
                    'wrong_formal_foot_product_capture/'+key)
            txs.append(sent)
            deltas.append(capture)
    plan = []
    for detail in ('full','brief'):
        for side,src in zip(BOXES,txs,strict=True):
            request = OLD['renamed'](src,f'offline-opposite-{side}-{detail}',image=True,detail=detail)
            OLD['args_of'](request)['query']['region']['world_box_m'] = deepcopy(BOXES[side])
            delta = deltas[1] if plan else deltas[0]
            plan.append(OLD['case'](request,delta,terminal,None,stage=side,box=True))
    fixture = {'terminal':terminal,'capture_plan':[row['capture'] for row in plan],
               'source_pins':list({p['path']:p for p in pinned}.values())}
    return binding,fixture,plan


def truth_for(fixture,captured):
    terminal = fixture['terminal']
    meshes = captured['meshes']
    for current,native in zip(meshes,terminal['objects'],strict=True):
        evaluated = native['evaluated']
        require(current['object_id']==native['object_id'] and current['faces']==evaluated['triangles']
                and current['vertices']==evaluated['vertices_world_m'],'replayed_native_world_rows_changed')
    target,cube = meshes
    oracle = run_path(str(LOW['ORACLE']))
    low,high,planes = oracle['boxed_reference'](cube['vertices'],cube['faces'])
    states = {}
    for side,box in BOXES.items():
        ids,vs = oracle['selected_indices'](target['vertices'],target['faces'],(box['min'],box['max']))
        points = [target['vertices'][i] for i in vs]
        minimum = tuple(map(min,zip(*points,strict=True)))
        maximum = tuple(map(max,zip(*points,strict=True)))
        gaps = [[Fraction(x)-Fraction(y) for x,y in zip(minimum,low,strict=True)],
                [Fraction(x)-Fraction(y) for x,y in zip(high,maximum,strict=True)]]
        sign = int(side=='positive_y')
        distance = gaps[sign][1]
        require(all(d>0 for row in gaps for d in row)
                and [(s,a) for s in range(2) for a in range(3) if gaps[s][a]<=distance]==[(sign,1)],
                'the_new_selection_requires_one_unique_nearest_Y_plane/'+side)
        coordinate = (minimum,maximum)[sign][1]
        witness = next(p for p in points if p[1]==coordinate)
        on_cube = [witness[0], (low,high)[sign][1], witness[2]]
        require(any(oracle['triangle_contains'](on_cube,[cube['vertices'][v] for v in cube['faces'][i]])
                    for i in planes[sign,1]),'nearest_cube_surface_point_not_in_reference/'+side)
        ordered = sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
        require((len(ids),len(vs),float(distance),ordered)==EXPECTED[side][:4],
                'independent_opposite_region_truth_changed/'+side)
        states[side] = {'triangle_ids':ids,'vertex_ids':vs,'distance_m':float(distance),
                        'direction_world':[0,2*sign-1,0],'distance_exact':[distance.numerator,distance.denominator],
                        'source_point_world_m':witness,'reference_point_world_m':on_cube}
    require(states['negative_y']['distance_m']<.892<states['positive_y']['distance_m'],
            'independent_opposite_direction_threshold_changed')
    return states


def check_catalogue(arm,tools):
    FOOT['check_catalogue'](arm,tools)
    require(tools==read(SLOT/'INSTALLED_TOOLS.json'),'registered_evidence_catalogue_changed')


def adapted(function,before,after,**overrides):
    text = inspect.getsource(function)
    require(text.count(before)==1,'retained_proof_anchor_changed/'+function.__name__)
    scope = {**function.__globals__,**overrides}
    exec(compile(text.replace(before,after),function.__code__.co_filename,'exec'),scope)
    return scope[function.__name__]


check_measurement = adapted(LOW['check_measurement'],
    'a[:2]==b[:2] and b[2]==1.0 and Fraction(b[2])-Fraction(a[2])==Fraction(*expected[\'distance_exact\'])',
    "a[0]==b[0] and a[2]==b[2] and b[1]==expected['direction_world'][1]"
    " and abs(Fraction(b[1])-Fraction(a[1]))==Fraction(*expected['distance_exact'])")
check_request = adapted(FOOT['check_request'],"(1 if side=='negative_y' else 6)","(1 if side=='positive_y' else 6)",
                        EXPECTED=EXPECTED,LOW={**LOW,'check_measurement':check_measurement})
preflight = FunctionType(FOOT['preflight'].__code__,{
    **FOOT['preflight'].__globals__, '__file__':str(Path(__file__).resolve()),
    'PLAN':PLAN, 'BINDINGS':BINDINGS, 'inputs':inputs, 'truth_for':truth_for,
    'check_catalogue':check_catalogue, 'check_request':check_request},'preflight')


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256']==OLD['PYTHON_SHA'],
            'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',choices=tuple(BINDINGS),default='B')
    parser.add_argument('--output',type=Path,default=RUN/'product')
    parser.add_argument('--worker',action='store_true')
    args = parser.parse_args()
    root = args.output.resolve()
    require(root.parent==RUN and root.name in ('product','product_recovery'),'opposite_preflight_output_required')
    if args.worker:
        require(root.is_dir() and not (root/'REPLAY_CLOSE.json').exists(),'current_opposite_worker_root_required')
        _,fixture,_ = inputs(args.arm)
        raise SystemExit(OLD['retained_workers']()[0]['worker'](
            root,BINDINGS[args.arm][0],'opposite_direction_qualification',False,source=fixture))
    preflight(args.arm,root)
