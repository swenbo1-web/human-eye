"""Freeze the original capture arms, ABI controls and two installed source identities."""
from hashlib import sha256
import json
from pathlib import Path
from subprocess import check_output

NS=Path(__file__).resolve().parent
V=NS.parent
RUN=Path('D:/he_m3_whole_object_witness_triangle_001')
BASE=V/'m1_source_region_no_image_measurement_packet_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE=NS/'install/PRODUCT_RUN_BINDING.json'
PLAN='cb76797a3c8743d1d17774150f8a0d9beafbe421:docs/M3_WHOLE_OBJECT_WITNESS_TRIANGLE_001_PLAN.md'
PREVIOUS=V/'m1_source_region_no_image_native_transfer_001'
ARMS={'baseline_standard':('baseline','standard'),'baseline_evidence':('baseline','evidence'),
      'candidate_standard':('candidate','standard'),'candidate_evidence':('candidate','evidence')}


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    path=path.resolve(strict=True)
    raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def freeze():
    inputs=[BASE,CANDIDATE,NS/'install/BUILD_INSTALL.json',NS/'PLAN.md',Path(__file__),NS/'build_install.py',
            PREVIOUS/'RAW_INDEX.json',PREVIOUS/'ORIGINAL_RUNTIME.zip',
            V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
            V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
            *sorted((NS/'harness').glob('*')),*(NS/'checks'/filename for filename in (
            'delivery.py','historical.py','matrix.py','HISTORICAL.json','CHECKER_PREFLIGHT.json'))]
    if (NS/'PLAN.md').read_bytes()!=check_output(['git','show',PLAN],cwd=V.parent):
        raise ValueError('original frozen plan text changed')
    preflight=read(NS/'harness/PREFLIGHT.json')
    if preflight['passed'] is not True or len(preflight['cells'])!=6:
        raise ValueError('actual baseline stdio preflight missing')
    history=read(NS/'checks/HISTORICAL.json')
    if not history['passed'] or set(history['sealed_labels'])!={'P1','P2','P3'}:
        raise ValueError('three original source slots not verified')
    identities={}
    for label,path in [('baseline',BASE),('candidate',CANDIDATE)]:
        binding=read(path)
        identities[label]={key:binding[key] for key in ('preparation_git','source_sha256','wheel_sha256','install_root')}
        wheel=pin(Path(binding['wheel_path']))
        if wheel['sha256']!=binding['wheel_sha256'] or len(binding['source_manifest'])!=143:
            raise ValueError('bound installed version changed',label)
        inputs.append(Path(wheel['path']))
        for item in binding['source_manifest']:
            source=Path(binding['install_root'])/item['path']
            if pin(source)['sha256']!=item['sha256']:
                raise ValueError('fixed installed member changed',label,item['path'])
            inputs.append(source)
    for cell in preflight['cells']:
        item=cell['case']
        source=Path(item['path'])
        if pin(source)!=item:
            raise ValueError('baseline preflight closure changed')
        inputs.append(source)
    spec={'plan':PLAN,'inputs':[pin(path) for path in sorted(set(inputs))],
          'source_slots':['P1','P2','P3'],'identities':identities,'arms':ARMS,
          'formal_positive_cases':3*len(ARMS),'formal_requests':6*len(ARMS),
          'response_body_UTF8_bytes_limit':2048,'allowed_new_solves_cold':1,'allowed_new_solves_hot':0,
          'host_requests_per_public_result':1,'witness_checks_limit':2,
          'allow_new_blender':0,'allow_new_models':0,'allow_extra_builds':0,'allow_new_rasters':0}
    with (NS/'FROZEN.json').open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    print(pin(NS/'FROZEN.json'))


if __name__=='__main__':
    freeze()
