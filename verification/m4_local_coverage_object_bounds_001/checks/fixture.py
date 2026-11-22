"""Load two preregistered closed product captures from byte-identical archives."""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
REPO = NS.parents[1]
CASES = {
    'main': ('5b7910c1486071abae84466cb0b51230dc111aa0',
             'm4_dense_sweep_integrated_native_startup_001',
             '3cdb270694e6d7096dfd3554b6a19edea5a3891a1ee76d35d204e8713c916a06',
             (20,3502,6160), ('Component_582','Component_736')),
    'holdout': ('39fd39cd','m4_cross_scale_assembly_transfer_001',
                'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90',
                (28,416,744), ('N10',)),
}


def require(test,message):
    if not test:
        raise ValueError(message)


def digest(data):
    return {'sha256':sha256(data).hexdigest(),'bytes':len(data)}


def pin(path,data=None):
    path = Path(path).resolve(strict=True)
    return {'path':str(path),**digest(path.read_bytes() if data is None else data)}


def read(path):
    return json.loads(Path(path).read_bytes())


def source(name):
    commit,batch,expected,counts,local_names = CASES[name]
    sealed = REPO/'verification'/batch
    runtime = Path('D:/he_'+batch)
    slot = runtime/'slots/P1'
    is_main = name=='main'

    def versioned(path):
        logical = path.relative_to(REPO).as_posix()
        original = subprocess.check_output(['git','show',commit+':'+logical],cwd=REPO)
        require(original==path.read_bytes(),'git_evidence_changed/'+logical)
        return original

    index_path = sealed/('RAW_INDEX.json' if is_main else 'RUNTIME_INDEX.json')
    raw = versioned(index_path)
    index = json.loads(raw)
    archive = sealed/index['archive']['name'] if is_main else Path(index['archive']['path'])
    zipped = versioned(archive) if is_main else archive.read_bytes()
    require(digest(zipped)=={k:index['archive'][k] for k in ('sha256','bytes')},'sealed_archive_changed/'+name)
    members = index['members'] if is_main else {row['path']:row for row in index['files']}
    pins = [pin(index_path,raw),pin(archive,zipped)]
    with ZipFile(BytesIO(zipped)) as data:
        def member(path):
            live = slot/path
            key = ('runtime/' if is_main else '')+live.relative_to(runtime).as_posix()
            raw = data.read(key)
            require(digest(raw)=={k:members[key][k] for k in ('sha256','bytes')}
                    and raw==live.read_bytes(),'archive_member_changed/'+key)
            pins.append(pin(live,raw))
            return raw

        terminal = json.loads(member('TERMINAL_SOURCE.json'))
        producer = json.loads(member('product_full/call_001/SERVICE_RESULT.json'))
        result = json.loads(member('SLOT_RESULT.json'))
        publication = json.loads(member('SLOT_PUBLICATION.json'))
        native_copy = member('native/input.blend')
    require(pins[2]['sha256']==expected and len(pins)==7,'terminal_source_pin_changed/'+name)
    require(result['status']==publication['status']=='completed' and result['independent_before_after']['passed']
            and result['closure_verification']['passed'] and publication['result_sha256']==pins[4]['sha256']
            and terminal['source']['asset_sha256']==result['asset_sha256']==digest(native_copy)['sha256'],
            'original_source_or_close_changed/'+name)

    by_id = {row['object_id']:row for row in terminal['objects']}
    scene = {'objects':[]}
    for i,bound in enumerate(producer['binding']['objects']):
        row = by_id[bound['host_id']]
        require(bound['object_index']==i and bound['object_name']==row['name']
                and bound['instance_id']==row['instance_id'],'original_object_order_or_instance_changed/'+name)
        evaluated = row['evaluated']
        scene['objects'].append({'name':row['name'],'vertices':evaluated['vertices_world_m'],
                                 'triangles':evaluated['triangles']})
    dimensions = (len(scene['objects']),sum(len(o['vertices']) for o in scene['objects']),
                  sum(len(o['triangles']) for o in scene['objects']))
    require(dimensions==counts and len(by_id)==counts[0],'original_scene_size_changed/'+name)
    locals_ = producer['scopes'][1:]
    require(producer['scopes'][0]['scope_id']=='global'
            and tuple(scope['facts']['regions'][0]['object_name'] for scope in locals_)==local_names,
            'sealed_local_scope_roster_changed/'+name)
    return scene,producer,pins
