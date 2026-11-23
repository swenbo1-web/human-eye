"""Freeze the low bilateral task and run the two original owned slots."""

import argparse
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
sys.path.insert(0, str(HERE))
import host


PRIOR = V/'m4_yanyite_bilateral_region_native_001'
OLD = run_path(str(PRIOR/'experiment.py'))
BASE = OLD['BASE']
RUN, PLAN, PRODUCT = host.RUN, host.PLAN, host.PRODUCT
FROZEN, PROMPT = HERE/'FROZEN.json', host.PROMPT
SLOTS, LIMITS = OLD['SLOTS'], OLD['LIMITS']
JOURNAL = RUN/'FORMAL_SEQUENCE.jsonl'
ENTRY = RUN/'preflight/RUNTIME_PREFLIGHT.json'
PROOFS = (ENTRY, RUN/'preflight/LOW_SOURCE_TRUTH.json', RUN/'preflight/product/SUMMARY.json',
          RUN/'preflight/ordinary_v2/SUMMARY.json')
PRODUCT_PROOF = 'a62a86d526b29f9136c22fad9d2d0b4bc59d234b'
read, write, pin, git, require = (BASE[key] for key in ('read', 'write', 'pin', 'git', 'require'))
OLD['formal'].__globals__.update(HERE=HERE, RUN=RUN, PLAN=PLAN, PRODUCT=PRODUCT, FROZEN=FROZEN, PROMPT=PROMPT,
                                 JOURNAL=JOURNAL, ENTRY=ENTRY, __file__=str(Path(__file__).resolve()))
verify_freeze, formal, admit, archive = (OLD[key] for key in ('verify_freeze', 'formal', 'admit', 'archive'))


def runtime_preflight():
    """Use the two original fresh runs of the actual ingress and closure."""
    arms = {}
    sources = []
    for label in SLOTS:
        receipt = RUN/'preflight/entry_v2'/label/'ARM.json'
        p = read(receipt)
        arm = p['arms'][label]
        require(p['passed'] and set(p['arms']) == {label} and arm['closed'] and arm['reached_before_Blender_reserve']
                and arm['actual_product_handshake'] is (label == 'P1')
                and p['Blender'] == p['models'] == p['rasters'] == 0, 'actual_cold_ingress_failed/'+label)
        arms[label] = arm
        sources.extend([pin(receipt), *p['source_pins']])
    require([tool for tool in arms['P1']['tools'] if tool['name'] != 'human_eye_scene_observe'] ==
            arms['N1']['tools'], 'actual_ordinary_catalogue_different')
    write(ENTRY, {'passed':True, 'arms':arms, 'source_pins':sources, 'Blender':0, 'models':0})


def freeze():
    require(not (RUN/'slots').exists() and not JOURNAL.exists() and not FROZEN.exists(),
            'no_replacement_or_modified_freeze')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN)
            and pin(sys.executable)['sha256'] == host.PYTHON_SHA and pin(host.CLI)['sha256'] == host.CLI_SHA,
            'fixed_plan_or_execution_identity_changed')
    asset = pin(host.ASSET)
    require((asset['bytes'],asset['sha256']) == (3_415_766,host.ASSET_SHA256), 'fixed_original_Yanyite_changed')
    binding_path = host.PRODUCT_BINDING
    require(binding_path.read_bytes() == git('show', PRODUCT_PROOF+':'+binding_path.relative_to(V.parent).as_posix()),
            'accepted_install_binding_changed')
    binding = host.fixed_binding(binding_path)
    wheel = Path(binding['wheel_path'])
    paths = {binding_path, wheel, PRIOR/'host.py', PRIOR/'experiment.py', PRIOR/'costs.py',
             Path(sys.executable), *host.retained_sources(), *PROOFS,
             *[p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.md','.json','.py','.txt')]}
    for report in PROOFS:
        proof = read(report)
        require(proof['passed'] is True, 'actual_preflight_not_accepted/'+report.name)
        for row in proof.get('source_pins', proof.get('input_pins', [])):
            actual = pin(row['path'])
            require(all(actual[k] == row[k] for k in ('bytes','sha256')), 'preflight_source_changed/'+row['path'])
            paths.add(Path(row['path']))
    with ZipFile(wheel) as pack:
        for row in binding['source_manifest']:
            actual = Path(binding['install_root'])/row['path']
            require(pin(actual)['sha256'] == row['sha256'] and actual.read_bytes() == pack.read(row['path'])
                    == git('show', PRODUCT['commit']+':'+row['path']), 'installed_product_source_changed/'+row['path'])
            paths.add(actual)
    pins = {row['path']:row for row in map(pin, paths)}
    write(FROZEN, {'plan':PLAN, 'product':PRODUCT, 'asset_sha256':asset['sha256'], 'slots':list(SLOTS),
                   'prompt':pin(PROMPT), 'limits':LIMITS, 'passed_offline_preflight':True,
                   'request_configuration':['0.152.1','gpt-6.1-sol','medium','default'],
                   'inputs':sorted(pins.values(), key=lambda row:row['path'])})
    print('Frozen', verify_freeze(FROZEN), len(pins), 'inputs', flush=True)


def costs():
    digest = verify_freeze(FROZEN)
    summarize = run_path(str(PRIOR/'costs.py'))['summarize']
    arms = {label:summarize(RUN/'slots'/label, digest) for label in SLOTS}
    same_prompt = all(row.get('initial_prompt_sha256') == pin(PROMPT)['sha256']
                      for row in arms.values() if row.get('model_consumers_launched'))
    write(RUN/'COSTS.json', {'freeze_sha256':digest,'arms':arms,'same_original_prompt':same_prompt,
                            'provider_internal_time':None,'provider_billing':None})


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_required')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase', choices=('runtime_preflight','freeze','formal','slot','costs','archive'))
    p.add_argument('label', choices=SLOTS, nargs='?')
    a = p.parse_args()
    require((a.phase == 'slot') == bool(a.label), 'registered_label_required_only_in_slot')
    if a.phase == 'slot':
        raise SystemExit(host.run_slot(a.label, admit))
    globals()[a.phase]()
