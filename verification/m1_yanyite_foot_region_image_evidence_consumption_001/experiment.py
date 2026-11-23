"""Freeze the matched foot task and run the two unmodified model slots."""

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
RUN, PLAN, PRODUCTS = host.RUN, host.PLAN, host.PRODUCTS
FROZEN, PROMPT = HERE/'FROZEN.json', host.PROMPT
SLOTS, LIMITS = tuple(host.SLOTS), OLD['LIMITS']
JOURNAL = RUN/'FORMAL_SEQUENCE.jsonl'
ENTRY = RUN/'preflight/RUNTIME_PREFLIGHT.json'
PROOFS = (ENTRY, RUN/'preflight/FOOT_TRUTH_FINAL.json', RUN/'preflight/product_A/SUMMARY.json',
          RUN/'preflight/product_B/SUMMARY.json', RUN/'preflight/ordinary_final/SUMMARY.json')
PRODUCT_PROOFS = {'A1':'a62a86d526b29f9136c22fad9d2d0b4bc59d234b',
                  'B1':'6fee57dff92aed9270259368c3139118f016ae6f'}
read, write, pin, git, require = (BASE[key] for key in ('read', 'write', 'pin', 'git', 'require'))
OLD['formal'].__globals__.update(HERE=HERE, RUN=RUN, PLAN=PLAN, PRODUCT=PRODUCTS, FROZEN=FROZEN,
                                 PROMPT=PROMPT, SLOTS=SLOTS, JOURNAL=JOURNAL, ENTRY=ENTRY,
                                 __file__=str(Path(__file__).resolve()))
verify_freeze, formal, admit, archive = (OLD[key] for key in ('verify_freeze', 'formal', 'admit', 'archive'))


def runtime_preflight():
    arms, sources = {}, []
    for label in SLOTS:
        receipt = RUN/'preflight/entry_v2'/label/'ARM.json'
        proof = read(receipt)
        arm = proof['arms'][label]
        require(proof['passed'] and set(proof['arms']) == {label} and arm['closed']
                and arm['actual_product_handshake'] and arm['reached_before_Blender_reserve']
                and proof['Blender'] == proof['models'] == proof['rasters'] == 0,
                'actual_cold_ingress_failed/'+label)
        arms[label] = arm
        sources.extend([pin(receipt), *proof['source_pins']])
    require(host.catalogues_equivalent(arms['A1']['tools'], arms['B1']['tools']),
            'formal_tool_definitions_differ_outside_evidence_description')
    write(ENTRY, {'passed':True,'arms':arms,'source_pins':sources,'Blender':0,'models':0})


def freeze():
    require(not (RUN/'slots').exists() and not JOURNAL.exists() and not FROZEN.exists(),
            'no_replacement_or_modified_freeze')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN)
            and pin(sys.executable)['sha256'] == host.PYTHON_SHA and pin(host.CLI)['sha256'] == host.CLI_SHA,
            'fixed_plan_or_execution_identity_changed')
    asset = pin(host.ASSET)
    require((asset['bytes'],asset['sha256']) == (3_415_766,host.ASSET_SHA256), 'fixed_original_Yanyite_changed')
    paths = {host.PRIOR_HOST, PRIOR/'experiment.py', PRIOR/'costs.py',
             Path(sys.executable), *host.retained_sources(), *PROOFS,
             *[p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.md','.json','.py','.txt')]}
    for report in PROOFS:
        proof = read(report)
        require(proof['passed'] is True, 'actual_preflight_failed/'+str(report))
        for row in proof.get('source_pins', proof.get('input_pins', [])):
            actual = pin(row['path'])
            require(all(actual[k] == row[k] for k in ('bytes','sha256')), 'preflight_source_changed/'+row['path'])
            paths.add(Path(row['path']))
    for label in SLOTS:
        binding_path = host.PRODUCT_BINDINGS[label]
        relative_binding = binding_path.relative_to(V.parent).as_posix()
        require(binding_path.read_bytes() == git('show', PRODUCT_PROOFS[label]+':'+relative_binding),
                'accepted_install_binding_changed/'+label)
        binding = host.fixed_binding(label)
        product_proof = read(RUN/f'preflight/product_{label[0]}/SUMMARY.json')
        require(product_proof['product_git'] == PRODUCTS[label]['commit'] and
                product_proof['actual_tools'] == read(host.catalogue_path(label)),
                'actual_offline_product_mcp_does_not_match_current_slot/'+label)
        wheel = Path(binding['wheel_path'])
        paths.update((binding_path,wheel))
        with ZipFile(wheel) as pack:
            for row in binding['source_manifest']:
                installed = Path(binding['install_root'])/row['path']
                require(pin(installed)['sha256'] == row['sha256']
                        and installed.read_bytes() == pack.read(row['path'])
                        == git('show', PRODUCTS[label]['commit']+':'+row['path']),
                        'installed_product_source_changed/'+label+'/'+row['path'])
                paths.add(installed)
    pins = {row['path']:row for row in map(pin,paths)}
    write(FROZEN, {'plan':PLAN,'product':PRODUCTS,'asset_sha256':asset['sha256'],'slots':list(SLOTS),
                   'prompt':pin(PROMPT),'limits':LIMITS,'passed_offline_preflight':True,
                   'request_configuration':['0.152.1','gpt-6.1-sol','medium','default'],
                   'inputs':sorted(pins.values(),key=lambda p:p['path'])})
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
