"""Derive the sole reused qualification from the immutable prior run."""

import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
from hashlib import sha256

sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import ASSET, ASSET_SHA256, NS, ORIGINAL, ORIGINAL_RUN, PRODUCT, PRODUCT_BINDING, ROOT, read, save, sha


BASE = 'bf102d233b0f8c3c9621b43981b2cefac6ff06da'
ORIGINAL_FREEZE = '7bd5f9b4c3e0cbd513b0426db14e97204293751f433260e4b2c56688f3084cad'
ARCHIVE_SHA = '47a4267c8379a4bbc1baa2f56bfcb59f46f53636f8ada129ce264ea77bbc8ab8'


def require(test, reason):
    if not test:
        raise ValueError(reason)


def derive():
    from PIL import Image
    from io import BytesIO
    from bridge import TOOLS

    trust = {}

    def pin(path):
        path = Path(path).resolve(strict=True)
        trust[str(path)] = {'path':str(path), 'bytes':path.stat().st_size, 'sha256':sha(path)}
        return trust[str(path)]

    def sealed(name):
        path = ORIGINAL / name
        meta = pin(path)
        blob = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{BASE}:{path.relative_to(ROOT).as_posix()}'])
        require(sha256(blob).hexdigest()==meta['sha256'], 'original_evidence_does_not_match_Git/' + name)
        return json.loads(blob)

    frozen, index = sealed('FROZEN.json'), sealed('RAW_INDEX.json')
    result, publication = sealed('evidence/QN_SLOT_RESULT.json'), sealed('evidence/QN_SLOT_PUBLICATION.json')
    closed, proof = sealed('evidence/QN_CLOSED_IMAGES.json'), sealed('evidence/QN_QUALIFICATION.json')
    rejected, formal = sealed('evidence/QP_SLOT_RESULT.json'), sealed('consumer/COSTS.json')
    truth = sealed('fixture/TRUTH.json')
    fixture = sealed('fixture/ASSET_BINDING.json')
    require(sha(ORIGINAL/'FROZEN.json') == index['freeze_sha256'] == result['freeze_sha256'] == closed['freeze_sha256']
            == rejected['freeze_sha256'] == ORIGINAL_FREEZE, 'old_freeze_identity_changed')
    require(publication['status'] == result['status'] == 'completed' and publication['owned_budget_passed']
            and publication['result_sha256'] == closed['result_sha256'] == sha(ORIGINAL/'evidence/QN_SLOT_RESULT.json')
            and result['product_binding_sha256']==sha(PRODUCT_BINDING)
            and result['group']=='N' and result['phase']=='qualification' and result['model_consumers']==result['paid_API_calls']==0
            and result['closure_verification']['passed'] and result['closure_verification']['status']=='ready_closed'
            and result['closure_verification']['mcp_closure_required'] is False
            and result['independent_before_after']['passed'] and proof==result['qualification'] and proof['passed']
            and closed['passed'] and closed['reopened']==proof['images'], 'reused_QN_original_gate_not_passed')
    require(rejected['status']=='failed' and any(error['message']=='current_host_source_loaded' for error in rejected['errors'])
            and len(rejected['diagnostic_calls'])==2 and all(row['status']=='unrun' for row in formal['slots'])
            and len(formal['slots'])==6, 'old_failed_slot_or_formal_denominators_changed')
    require(frozen['product'] == PRODUCT and frozen['asset_sha256'] == result['asset_sha256'] == ASSET_SHA256
            == fixture['asset']['sha256'] == sha(ASSET)
            and fixture['counts']=={'objects':21,'vertices':3506,'triangles':6162}
            and sorted(row['object_name'] for row in truth['eligible'])==['S021','S034','S055']
            and frozen['prompt_sha256']==sha(NS/'inputs/PROMPT.txt')
            and result['budget']['slots']['QN']=={'business_admissions':5,'raster_actual':3,'raster_upper':3}
            and (frozen['max_business_per_slot'],frozen['max_qualification_rasters_per_slot'],frozen['task_s'],frozen['owned_s'])==(12,6,450,600),
            'reused_QN_asset_product_task_or_budget_mismatch')
    archive = pin(ORIGINAL/'ORIGINAL_RUNTIME.zip')
    require(archive['sha256']==index['archive']['sha256']==ARCHIVE_SHA and index['member_count']==866, 'old_original_archive_changed')
    qn_root = ORIGINAL_RUN/'slots/QN'
    names = {name for name in index['members'] if name.startswith('runtime/slots/QN/')}
    require(len(names)==188, 'old_QN_archive_member_count_changed')
    with ZipFile(archive['path']) as bundle:
        for name in sorted(names):
            data = bundle.read(name)
            path = ORIGINAL_RUN/name.removeprefix('runtime/')
            require({'bytes':len(data),'sha256':sha256(data).hexdigest()}==index['members'][name]
                    and path.read_bytes()==data, 'archived_QN_original_mismatch/'+name)
    require(read(qn_root/'owner/TOOLS_SCHEMA.json')==TOOLS==read(qn_root/'client/TOOLS.json')['result']['tools'],
            'actual_QN_tools_not_equal_to_recovery_common_tools')
    require((qn_root/'SLOT_RESULT.json').read_bytes()==(ORIGINAL/'evidence/QN_SLOT_RESULT.json').read_bytes()
            and (qn_root/'SLOT_PUBLICATION.json').read_bytes()==(ORIGINAL/'evidence/QN_SLOT_PUBLICATION.json').read_bytes()
            and (qn_root/'QUALIFICATION.json').read_bytes()==(ORIGINAL/'evidence/QN_QUALIFICATION.json').read_bytes(), 'filed_QN_is_not_archive_QN')
    worker = read(qn_root/'native/WORKER_CLOSED.json')
    require(worker['pid']==result['closure_verification']['pid'] and worker['poisoned'] is False
            and worker['initial_geometry_fingerprint']==worker['final_geometry_fingerprint'], 'old_QN_worker_exit_mismatch')
    require(sum(row['complete'] is True for row in proof['images'].values())==2
            and all(row['passed'] for row in proof['CLI'].values()), 'old_QN_image_or_CLI_gate_mismatch')
    for row in proof['images'].values():
        png = Path(row['path']).resolve(strict=True)
        raw = png.read_bytes()
        require(png.is_relative_to(qn_root.resolve()) and sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['bytes'],
                'reused_QN_PNG_not_original')
        with Image.open(BytesIO(raw)) as image:
            require(image.format=='PNG' and image.size==(512,512),'reused_QN_PNG_decode_failed')
            image.load()
    for file in ('owner/TOOLS_SCHEMA.json','native/WORKER_CLOSED.json','RUNTIME_CLOSE.json','DEVICE_EVIDENCE.json',
                 'client/TOOLS.json','SLOT_RESULT.json','SLOT_PUBLICATION.json','QUALIFICATION.json'):
        pin(qn_root/file)
    document = {'passed':True,'reused':True,'new_Blender_starts':0,'original_git':BASE,'original_freeze_sha256':ORIGINAL_FREEZE,
        'original_QN_result_sha256':publication['result_sha256'],'original_members_reverified':len(names),
        'assets_unchanged':True,'asset_sha256':ASSET_SHA256,'original_QP_failed':True,'old_formal_unrun':6,
        'tools':TOOLS,'budget':result['budget']['slots']['QN'],'proof':proof,'source_pins':list(trust.values())}
    destination = NS/'qualification/QN_DERIVED_ADMISSION.json'
    require(not destination.exists(), 'derived_QN_already_published')
    save(destination,document)
    return document


if __name__=='__main__':
    sys.path.insert(0,read(PRODUCT_BINDING)['dependency_root'])
    print('Reused QN closed originals', derive()['original_members_reverified'])
