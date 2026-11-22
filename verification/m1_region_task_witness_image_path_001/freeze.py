"""Freeze the installed candidate, old evidence and the one main stdio matrix."""

from base64 import b64decode
from hashlib import file_digest, sha256
import json
from pathlib import Path
from runpy import run_path
from subprocess import check_output
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
V = NS.parent
ROOT = Path('D:/he_m1_region_task_witness_image_path_001')
ORIGINAL = V/'m1_region_task_first_packet_consumption_holdout_recovery_001'
BASELINE = V/'m1_region_task_first_packet_projection_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS/'install/PRODUCT_RUN_BINDING.json'
PLAN = '28c0fc90cf487f1743d800e63f1362319bd0a838:docs/M1_REGION_TASK_WITNESS_IMAGE_PATH_001_PLAN.md'
OLD_GIT = '19c4333ccf0e135db24edc593edd8a10d78908eb'
PRODUCT_GIT = '1535d08ac5124b5fe117101806ae3c85d47247fe'
MATRIX = (('A1_baseline','A1',False,False),('B1_baseline','B1',False,True),
          ('A1_candidate','A1',True,True),('B1_candidate','B1',True,True))
replay = run_path(str(NS/'harness/replay.py'))
read, save, require = (replay[key] for key in ('read','save','require'))
TARGET = NS/'FROZEN.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return file_digest(stream,'sha256').hexdigest()


def pins(path):
    path = Path(path).resolve(strict=True)
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':digest(path)}


def git(*args):
    return check_output(['git',*args],cwd=V.parent)


def historical_readback(slot,source):
    """Verify the original, real model-slot public read_images response."""
    ordinal={'A1':4,'B1':5}[slot]
    index=read(ORIGINAL/'RAW_INDEX.json')
    archive=ORIGINAL/index['archive']['name']
    require(digest(archive)==index['archive']['sha256'],'historic_public_reader_archive_changed')
    prefix=source['folder']/f'owner/tool_{ordinal:02}'
    bound=[]
    with ZipFile(archive) as bundle:
        for name in ('REQUEST.json','RESPONSE.json'):
            path=prefix/name
            filename=f'runtime/slots/{slot}/owner/tool_{ordinal:02}/{name}'
            row=pins(path)
            data=bundle.read(filename)
            require({k:row[k] for k in ('bytes','sha256')}==index['members'][filename]
                    and sha256(data).hexdigest()==row['sha256'],'historical_public_read_images_member_changed')
            bound.append(row)
    call,result=(read(row['path']) for row in bound)
    require(call['params']['name']=='read_images' and call['id']==result['id'] and result['result']['isError'] is False,
            'original_public_image_reader_did_not_complete')
    refs=call['params']['arguments']['refs']
    content=result['result']['content']
    require(len(refs)==2 and len(content)==4,'original_two_actual_readbacks_required')
    by_ref={}
    for ref,caption,image in zip(refs,content[::2],content[1::2],strict=True):
        title,metadata=caption['text'].split('\n',1)
        row=json.loads(metadata)
        old=source['original_images'][ref]
        data=b64decode(image['data'],validate=True)
        path=Path(row['local_image_path']).resolve(strict=True)
        require(title.startswith(ref+' ') and path.as_posix()==row['local_image_path']
                and path==Path(old['path']) and row['image_sha256']==old['sha256']==sha256(data).hexdigest()
                and pins(path)==old and image['type']=='image' and image['mimeType']=='image/png',
                'original_public_path_escaped_its_closed_scope_or_PNG')
        by_ref[ref]={'path':path.as_posix(),'sha256':old['sha256'],'bytes':old['bytes']}
    return by_ref,bound


def freeze():
    require(not TARGET.exists() and not (ROOT/'qualification').exists(), 'one_final_matrix_required')
    scope = NS.relative_to(V.parent).as_posix() + '/'
    require(git('merge-base',OLD_GIT,'HEAD').decode().strip()==OLD_GIT
            and all(name.startswith(scope) for name in git('diff','--name-only',OLD_GIT).decode().splitlines())
            and git('show',PLAN)==(NS/'PLAN.md').read_bytes(),'existing_fixed_evidence_or_plan_changed')
    original = read(ORIGINAL/'RAW_INDEX.json')
    original_zip = ORIGINAL/original['archive']['name']
    require(original['archive']['sha256']==digest(original_zip)
            and original['archive']['sha256']=='a61668ab58b0bf8160eb15838930137547cdb55f29b52d4186c9cea42f5064e7',
            'closed_original_formal_archive_changed')
    preflight=read(ROOT/'preflight_02/QB/RESULT.json')
    require(read(NS/'evidence/PRODUCT_CONTROLS.json')['passed'] is True
            and read(ROOT/'compatibility/RESULT.json')['baseline_candidate_comparisons']==30
            and preflight['status']=='completed' and preflight['read_images']['original_result_equal'] is True,
            'installed_preflight_required')
    registered = {}

    def add(path,sha=None):
        row = pins(path)
        require(sha is None or sha==row['sha256'],'bound_input_changed/' + row['path'])
        registered[row['path']] = row

    for path,git_id in ((BASELINE,'24b8855746dfe9eeee7fa7d374bec2da86c21a2e'),(CANDIDATE,PRODUCT_GIT)):
        identity = read(path)
        require(identity['preparation_git']==git_id and len(identity['source_manifest'])==143, 'fixed_product_version_required')
        add(path)
        add(identity['wheel_path'],identity['wheel_sha256'])
        for source in identity['source_manifest']:
            add(Path(identity['install_root'])/source['path'],source['sha256'])
    for slot in ('QA','QB','A1','B1'):
        snapshot = replay['archived'](slot)
        for pin in snapshot['pins']:
            add(pin['path'],pin['sha256'])
        for pin in snapshot['original_images'].values():
            add(pin['path'],pin['sha256'])
        if slot in ('A1','B1'):
            _,bound=historical_readback(slot,snapshot)
            for pin in bound:
                add(pin['path'],pin['sha256'])
    for path in (original_zip,ORIGINAL/'RAW_INDEX.json',ORIGINAL/'FROZEN.json',sys.executable,
                 V/'m4_dense_region_brief_001/checks/brief_schema.py',
                 V/'m4_cross_scale_live_qualification_001/checks/delivery.py',
                 V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
                 V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py'):
        add(path)
    for folder in (NS,ROOT/'compatibility',ROOT/'preflight_01',ROOT/'preflight_02',Path(str(ROOT)+'_independent_checks')):
        for path in folder.rglob('*'):
            if path.is_file():
                add(path)
    save(TARGET,{'plan':PLAN,'original_git':OLD_GIT,'candidate_git':PRODUCT_GIT,'matrix':MATRIX,
                 'candidate_builds':1,'candidate_installs':1,'new_Blender_starts':0,'new_model_starts':0,
                 'pins':[registered[path] for path in sorted(registered)]})
    print('Frozen',verify(),len(registered),'pins',flush=True)


def verify():
    value = read(TARGET)
    require(value['plan']==PLAN and value['original_git']==OLD_GIT and value['candidate_git']==PRODUCT_GIT
            and [list(row) for row in MATRIX]==value['matrix'], 'fixed_matrix_changed')
    for row in value['pins']:
        require(pins(row['path'])==row, 'frozen_input_changed/' + row['path'])
    return digest(TARGET)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    freeze()
