"""Fixed operator inputs for the finite single-mesh restore product.

Pins establish inputs, never intent truth or execution approval. The trusted
operator is responsible for same-index authorship of the intended reference.
"""
import hashlib,json
from pathlib import Path

PROTOCOL='owned-surface-restore-worker-v1'
PREFIX='HUMAN_EYE_SURFACE:'
MAX_MESSAGE=256*1024
LIMITS=dict(vertices=128,triangles=256,selected=8,displacement_m=.001,
    duration_ns=30_000_000_000,requests=16,scene_objects=1)
MODULES=('mesh_structure','surface_geometry','surface_reference','surface_restore','surface_owned')


def require(value,reason):
    if not value:raise ValueError('owned_surface_'+reason)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()


def decode(blob):
    require(len(blob)<=MAX_MESSAGE,'message_budget')
    def unique(pairs):
        result={}
        for k,v in pairs:require(k not in result,'duplicate_key');result[k]=v
        return result
    def reject(_):raise ValueError('owned_surface_nonfinite')
    return json.loads(blob,object_pairs_hook=unique,parse_constant=reject)


def pinned_file(path,expected,maximum):
    p=Path(path);require(p.is_absolute() and p.resolve()==p and p.is_file(),'fixed_file_path')
    require(type(expected) is str and len(expected)==64 and all(c in '0123456789abcdef' for c in expected),'pin_format')
    with p.open('rb') as f:blob=f.read(maximum+1)
    require(len(blob)<=maximum and hashlib.sha256(blob).hexdigest()==expected,'file_pin')
    return blob


def load_config(path):
    p=Path(path);require(p.is_absolute() and p.resolve()==p,'config_path')
    with p.open('rb') as f:blob=f.read(65537)
    require(len(blob)<=65536,'config_budget');value=decode(blob)
    require(type(value) is dict and set(value)=={'schema','blender_executable','blender_sha256','scene_file','scene_sha256',
        'reference_file','reference_sha256','object_id','journal_root','runtime_source_sha256','reference_intent'}
        and value['schema']=='owned-surface-operator-config-v1','config_fields')
    for field in ('blender_executable','scene_file','reference_file'):
        q=Path(value[field]);require(q.is_absolute() and q.resolve()==q and q.is_file(),'operator_path')
    journal=Path(value['journal_root']);require(journal.is_absolute() and journal.resolve()==journal and journal.is_dir(),'journal_path')
    require(type(value['object_id']) is str and 1<=len(value['object_id'])<=128,'target_id')
    intent=value['reference_intent'];require(type(intent) is dict and set(intent)=={'provenance','semantic_target','correspondence'}
        and all(type(v) is str and 1<=len(v)<=256 for v in intent.values())
        and intent['correspondence']=='same_index_from_owned_copy','operator_intent')
    require(type(value['runtime_source_sha256']) is str and len(value['runtime_source_sha256'])==64,'runtime_pin')
    return value,hashlib.sha256(blob).hexdigest()


def indices(value):
    require(type(value) is list and 1<=len(value)<=LIMITS['selected']
        and all(type(i) is int and 0<=i<LIMITS['vertices'] for i in value)
        and len(set(value))==len(value),'selected_indices')
    return sorted(value)
