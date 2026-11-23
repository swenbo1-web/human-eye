"""Reuse the original owned runtime in new formal and loopback namespaces."""

import ast
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'m2_source_region_cold_selective_transport_001'
RUN = Path('D:/he_m2_source_region_selective_residency_001').resolve()
ENTRY = RUN/'preflight/entry'
REPLAY = RUN/'preflight/success'
prior = run_path(str(OLD/'host.py'))
LABELS,ASSETS,BINDINGS,LIMITS,PRIVATE_TOOL,PREVIOUS = (
    prior[key] for key in ('LABELS','ASSETS','BINDINGS','LIMITS','PRIVATE_TOOL','PREVIOUS'))
load,read,require,sha,WORKER,BLENDER = (prior[key] for key in ('load','read','require','sha','WORKER','BLENDER'))
SLOTS = prior['SLOTS']
CATALOGUE = HERE/'STANDARD_TOOLS.json'
_old_assemble = prior['assemble']
_original_slot = prior['Slot']
_slot_globals = _original_slot.__enter__.__globals__
_slot_globals.update(HERE=HERE,RUN=RUN,CATALOGUE=CATALOGUE)
owned_root = prior['owned_root']
BASE = 'a383f953c28413ccdc010869d9a7b35257416632'
BASE_BINDING = OLD/'install/PRODUCT_RUN_BINDING.json'
BINDINGS = {'A':BASE_BINDING,'B':HERE/'install/PRODUCT_RUN_BINDING.json'}

def binding_identity(label,path):
    arm = LABELS[label][1]
    require(Path(path).resolve(strict=True)==BINDINGS[arm].resolve(strict=True),
            'actual_owned_selective_residency_binding_path_changed')
    baseline = read(BASE_BINDING)
    identity = baseline if arm=='A' else read(BINDINGS[arm])
    require(baseline['preparation_git']==BASE and len(identity['source_manifest'])==143
            and sha(identity['wheel_path'])==identity['wheel_sha256'], 'fixed_selected_product_mismatch')
    if arm=='B':
        require(identity['historical_preparation_git']==BASE
                and identity['historical_source_sha256']==baseline['source_sha256']
                and identity['dependency_root']==baseline['dependency_root']
                and Path(identity['install_root']).resolve()==RUN/'candidate_install/product',
                'fixed_selective_residency_install_missing')
    return identity

prior['assemble'].__globals__['binding_identity'] = binding_identity



def assemble(root,label,path):
    common,ledger,binding = _old_assemble(root,label,path)
    common.evidence_enabled = lambda _: False

    def standard_catalogue(slot):
        require(slot == label,'standard_catalogue_bound_to_current_slot')
        return CATALOGUE

    common.catalogue_for = standard_catalogue
    return common,ledger,binding


class ReplayBudget(_slot_globals['PreflightBudget']):
    def admit_business(self,label,phase):
        require(self.ledger.snapshot()['counts']['Blender_start_attempts']==0,
                'offline_measurement_before_any_Blender_admission')
        return self.ledger.admit_business(label,phase)


def owned_replay_endpoint(root,label):
    require(Path(root).resolve() == REPLAY/label,'registered_closed_replay_namespace')
    ready = read(root/'REPLAY_READY.json')
    require(ready['offline_fixture'] is True and ready['label']==label and ready['host']=='127.0.0.1'
            and type(ready['port']) is int and 1024 <= ready['port'] < 65536 and type(ready['pid']) is int,
            'registered_replay_ready_identity_required')
    return SimpleNamespace(host=ready['host'],port=ready['port'])


def entry_with_registered_endpoint():
    source = PREVIOUS/'host.py'
    table = ast.parse(source.read_bytes(),str(source))
    klass, = [node for node in table.body if isinstance(node,ast.ClassDef) and node.name=='Slot']
    entry, = [node for node in klass.body if isinstance(node,ast.FunctionDef) and node.name=='__enter__']
    before = ast.dump(ast.parse("SimpleNamespace(host='127.0.0.1', port=1)",mode='eval').body)
    old, = [node for node in ast.walk(entry) if isinstance(node,ast.Call) and ast.dump(node)==before]
    old.func = ast.parse('self.preflight_endpoint',mode='eval').body
    old.args,old.keywords = [],[]
    code = ast.fix_missing_locations(ast.Module(body=[entry],type_ignores=[]))
    exec(compile(code,str(source),'exec'),_slot_globals)
    return _slot_globals['__enter__']


_slot_globals.update(assemble=assemble,PreflightBudget=ReplayBudget)


class Slot(_original_slot):
    __enter__ = entry_with_registered_endpoint()

    def preflight_endpoint(self):
        if self.root == REPLAY/self.label:
            return owned_replay_endpoint(self.root,self.label)
        require(self.root == ENTRY/self.label,'reservation_only_namespace_required')
        return SimpleNamespace(host='127.0.0.1',port=1)


def retained_sources():
    return {path for path in prior['retained_sources']() if path.is_file()} | {
        OLD/'host.py',OLD/'mcp_entry.py',OLD/'meter.py',OLD/'FROZEN.json',OLD/'controls.py',OLD/'verify.py',
        PREVIOUS/'host.py',PREVIOUS/'mcp_entry.py',Path(__file__).resolve(),CATALOGUE}
