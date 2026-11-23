"""Bind the installed product and the four historical source-region requests."""

from hashlib import file_digest, sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PRIOR = HERE.parent/'m4_source_region_visual_scope_proof_001'
OLD_RUN = Path('D:/he_m4_source_region_visual_scope_proof_001')
RUN = Path('D:/he_m4_source_region_live_bounds_qualification_001')
PLAN = ('8d6ffc8ae7f9b54500820ac7ba630fad3dfbbe2a:'
        'docs/M4_SOURCE_REGION_LIVE_BOUNDS_QUALIFICATION_001_PLAN.md')
PREDECESSOR = '789165b8f892afcd62ea1bb765a185eec1982e13'
PRODUCT = 'ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'
ASSETS = {
    'RAIL': ('he_m4_rail_source_region_product_native_001',
             'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce', ('M19','M21')),
    'ASSEMBLY': ('he_m4_assembly_cross_asset_product_native_001',
                 '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85', ('N19','N25')),
}


def git(*args):
    return subprocess.check_output(('git',*args),cwd=REPO)


def pin(path):
    path=Path(path)
    with path.open('rb') as stream:
        return {'path':str(path),'bytes':path.stat().st_size,'sha256':file_digest(stream,'sha256').hexdigest()}


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path,value):
    with path.open('x',encoding='utf8',newline='\n') as out:
        json.dump(value,out,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)
        out.write('\n')


def full_prior_archive():
    ref = PRIOR/'RESULT.json'
    assert ref.read_bytes()==git('show', PREDECESSOR+':'+ref.relative_to(REPO).as_posix())
    result=read(ref)
    index_file=OLD_RUN/'sealed/RAW_INDEX.json'
    index=read(index_file)
    assert result['passed'] and result['raw_originals']['index']==pin(index_file)
    archive=Path(index['archive']['path'])
    assert pin(archive)==index['archive']==result['raw_originals']['archive']
    assert index['member_count']==len(index['members'])==524
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None and sorted(bundle.namelist())==sorted(index['members'])
        for name,entry in index['members'].items():
            data=bundle.read(name)
            assert len(data)==entry['bytes'] and sha256(data).hexdigest()==entry['sha256']
            assert data==(OLD_RUN/name).read_bytes(),name
    return result, (ref,index_file,archive)


def load_inputs():
    RUN.mkdir(parents=True,exist_ok=True)
    plan=HERE/'PLAN.md'
    content=git('show',PLAN)
    if not plan.exists():
        with plan.open('xb') as out:
            out.write(content)
    assert plan.read_bytes()==content
    prior, prior_files=full_prior_archive()
    verifier=run_path(str(PRIOR/'runner.py'))['verify_install']
    install=verifier()
    assert install['git']==PRODUCT and install['verified_sources']==143
    sys.path.insert(0,str(PRIOR))
    from sources import load_main
    found={case['label']:case for case in load_main()}
    paths={plan,*prior_files,Path(install['manifest']['path']),Path(install['wheel']['path'])}
    headers={'schema':'human-eye-m4-live-bounds-requests-v1','order':list(ASSETS),'cases':{}}
    for label,(folder,expected,targets) in ASSETS.items():
        slot=Path('D:/')/folder/'slots/P1'
        path, terminal=slot/'native/input.blend',slot/'TERMINAL_SOURCE.json'
        asset_pin,terminal_pin=pin(path),pin(terminal)
        assert asset_pin['sha256']==expected
        paths.update((path,terminal))
        batch={'label':label,'asset':asset_pin,'terminal':terminal_pin,'queries':[],'closed_cases':[]}
        for name in targets:
            case=found[name]
            original=case['proof']
            v=prior['cases'][name]['offline_proof']
            old_path=Path(v['path'])
            assert pin(old_path)==v and read(old_path)['passed'] is True
            assert all(terminal_pin[k]==original['terminal'][k] for k in ('sha256','bytes'))
            paths.update((old_path,Path(case['png']),Path(case['npz'])))
            batch['queries'].append(case['query'])
            rec=read(old_path)
            batch['closed_cases'].append({
                'label':name,'query':case['query'],
                'source_triangle_indices':case['producer']['region_ref']['source_triangle_indices'],
                'old_camera_specification':case['producer']['binding']['camera_specification'],
                'original_kept_ordinals':rec['original_camera_tight_world']['kept_ordinals'],
                'original_pixel_counts':rec['actual_archived_frame']['selected_pixels'],
                'prior_receipt':v,'prior_proof':original,
            })
        headers['cases'][label]=batch
    requests=RUN/'REQUESTS.json'
    write(requests,headers)
    paths.add(requests)
    result={'passed':True,'plan':PLAN,'product':install,'prior_commit':PREDECESSOR,
            'prior_archive_members_verified':524,'requests':pin(requests),
            'source_pins':[pin(p) for p in sorted(paths)],'field_sources':[
                'old accepted production arguments, bound full camera and real original same-slot receipts',
                'closed real terminal arrays for replay and later independent pre/post comparison',
            ]}
    write(RUN/'INPUT_CUSTODY.json',result)
    print({'requests':pin(requests),'prior_archive_members':524,'order':headers['order'],'verified_install_sources':143})


if __name__=='__main__':
    load_inputs()
