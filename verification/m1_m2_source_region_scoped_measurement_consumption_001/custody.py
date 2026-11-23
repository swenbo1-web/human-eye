"""Check the frozen engineering evidence and existing installation before the consumer run."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m1_m2_source_region_scoped_measurement_consumption_001')
OLD = V / 'm1_m2_source_region_scoped_measurement_001'
OLD_RUNTIME = Path('D:/he_m1_m2_source_region_scoped_measurement_001')
EVIDENCE = '2b3c8c2811c018ab8eda5e7c21b2bc51a442fa10'
PRODUCT = 'ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'
SOURCE = '4a51c48524b66895819b69a30d2bd8eb020ce840028f0612f8d6e887c0423f09'
WHEEL = '7ff84ab1349d93a0810c687c8e3b0cea10d311c512380b5a9077305f35d5685d'
PLAN = ('b76c86712a13c895ec5845167f8b85ee18d35e92:'
        'docs/M1_M2_SOURCE_REGION_SCOPED_MEASUREMENT_CONSUMPTION_001_PLAN.md')


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return {'bytes': len(data), 'sha256':sha256(data).hexdigest()}


def pin(path):
    return {'path': str(path), **digest(path.read_bytes())}


def git(*args):
    return subprocess.check_output(('git', *args), cwd=V.parent)


def main():
    plan_bytes = git('show', PLAN)
    plan = HERE/'PLAN.md'
    if not plan.exists():
        with plan.open('xb') as out:
            out.write(plan_bytes)
    assert plan.read_bytes() == plan_bytes
    refs = [OLD / name for name in ('RESULT.json', 'FROZEN.json', 'install/PRODUCT_RUN_BINDING.json')]
    for path in refs:
        assert git('show', f'{EVIDENCE}:{path.relative_to(V.parent).as_posix()}') == path.read_bytes()
    result,frozen,binding = map(read,refs)
    assert result['passed'] and result['live']['completed_slots']==4 and result['live']['measurements']==12
    assert result['freeze']['sha256']==pin(refs[1])['sha256']
    truth_path = RUN/'preflight/TRUTH.json'
    truth = read(truth_path)
    assert truth['passed'] and truth['terminal_sha256']==pin(Path(truth['terminal_path']))['sha256']
    assert truth['asset_sha256']==pin(Path(truth['asset_path']))['sha256']

    wheel, installed = Path(binding['wheel_path']), Path(binding['install_root'])
    assert binding['preparation_git']==PRODUCT and binding['source_sha256']==SOURCE
    assert pin(wheel)['sha256']==binding['wheel_sha256']==WHEEL
    expected = {entry['path']:entry['sha256'] for entry in binding['source_manifest']}
    assert len(expected)==143
    paths = [*expected, 'human_eye_plugin/plugin.json', 'human_eye_plugin/mcp_config.json']
    git_blobs = run_path(str(V/'m4_cross_scale_local_first_view_001/install/build_install.py'))['git_blobs']
    blobs = git_blobs(PRODUCT,paths)
    with ZipFile(wheel) as package:
        assert package.testzip() is None
        assert {name for name in package.namelist() if name.endswith('.py')}==expected.keys()
        assert all((installed/name).read_bytes()==blobs[name]==package.read(name) for name in paths)
        assert all(digest(blobs[name])['sha256']==expected[name] for name in expected)

    raw_index = OLD_RUNTIME/'sealed/RAW_INDEX.json'
    archive = OLD_RUNTIME/'sealed/ORIGINAL_RUNTIME.zip'
    assert digest(raw_index.read_bytes())==result['raw_archive']['index']
    index = read(raw_index)
    assert pin(archive)==index['archive']==result['raw_archive']['archive']
    assert len(index['members'])==index['member_count']==result['raw_archive']['member_count']==1507
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None and sorted(bundle.namelist())==sorted(index['members'])
        for name,row in index['members'].items():
            assert digest(bundle.read(name))==row and bundle.read(name)==(OLD_RUNTIME/name).read_bytes(),name
    inputs = [plan,truth_path,*refs,wheel,raw_index,archive,Path(truth['asset_path']),Path(truth['terminal_path'])]
    with (RUN/'preflight/CUSTODY.json').open('x',encoding='utf8',newline='\n') as out:
        json.dump({'passed':True,'engineering_evidence':EVIDENCE,'product':PRODUCT,
                   'runtime_source_count':len(expected),'runtime_source_sha256':SOURCE,'wheel_sha256':WHEEL,
                   'prior_archive_members_verified':len(index['members']),'new_builds':0,'new_installs':0,
                   'source_pins':[pin(path) for path in inputs]},out,ensure_ascii=False,indent=2)
        out.write('\n')
    print(pin(RUN/'preflight/CUSTODY.json'))


if __name__ == '__main__':
    main()
