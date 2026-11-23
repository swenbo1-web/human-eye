"""Bind closed scoring qualification and each domain's older truth sources."""

import argparse
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
CONTROL = run_path(str(HERE/'experiment.py'))
RUN = CONTROL['RUN']
ADMISSION = HERE/'ADMISSION.json'
RAW_SOURCES = RUN/'DOMAIN_SOURCES.json'
pin, read, require, write = (CONTROL[k] for k in ('pin','read','require','write'))


def verify(record=None):
    actual = read(ADMISSION) if record is None else record
    freeze = CONTROL['verify_freeze']()
    require(actual['qualification_freeze'] == pin(CONTROL['FROZEN'])
            and actual['qualification_freeze']['sha256'] == freeze
            and actual['score_entry'] == pin(HERE/'score.py')
            and actual['domain_receipt'] == pin(RAW_SOURCES)
            and actual['installed_product'] == CONTROL['PRODUCT'],
            'score_admission_not_bound_to_completed_preflight')
    receipt = read(RAW_SOURCES)
    require(receipt['passed'] and receipt['domain_inputs'] == actual['domain_inputs']
            and all(pin(row['path']) == row for row in actual['domain_inputs']),
            'historical_scoring_domain_input_changed')
    return pin(ADMISSION)['sha256'] if record is None else True


def seal():
    require(not ADMISSION.exists() and not RAW_SOURCES.exists(),'single_closed_score_admission_required')
    freeze = CONTROL['verify_freeze']()
    frozen = read(CONTROL['FROZEN'])
    fixed = {row['path'] for row in frozen['inputs']}
    domain_assets = run_path(str(HERE/'score.py'))['DOMAINS']
    evidence, candidates = {}, {}
    for asset, scorer in domain_assets.items():
        _, proof = scorer.historical_truth()
        require(proof['passed'] is True,'historical_domain_source_not_accepted/'+asset)
        rows = []
        for row in proof.get('source_pins',proof.get('input_pins',[])):
            current = pin(row['path'])
            require(all(current[key] == row[key] for key in ('bytes','sha256')),
                    'historical_domain_source_changed/'+row['path'])
            rows.append(current)
            candidates[current['path']] = current
        require(rows,'historical_domain_sources_missing/'+asset)
        evidence[asset] = rows
    additional = sorted((row for path,row in candidates.items() if path not in fixed),key=lambda row:row['path'])
    installed = HERE.parent/'m1_source_region_image_evidence_001/install/PRODUCT_RUN_BINDING.json'
    expected = '6fee57dff92aed9270259368c3139118f016ae6f:' + installed.relative_to(HERE.parents[1]).as_posix()
    require(installed.read_bytes()==CONTROL['git']('show',expected)
            and read(installed)['preparation_git']==CONTROL['PRODUCT'],'fixed_product_binding_changed')
    additional.append(pin(installed))
    write(RAW_SOURCES,{'passed':True,'qualification_freeze_sha256':freeze,'by_domain':evidence,
                       'domain_inputs':additional,'existing_product_binding':pin(installed)})
    record = {'qualification_freeze':pin(CONTROL['FROZEN']),'score_entry':pin(HERE/'score.py'),
              'domain_receipt':pin(RAW_SOURCES),'domain_inputs':additional,'installed_product':CONTROL['PRODUCT']}
    require(verify(record),'current_score_admission_not_verified')
    write(ADMISSION,record)
    print('Admitted',verify(),'with',len(additional),'additional domain/product inputs',flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('seal','verify'))
    phase = parser.parse_args().phase
    seal() if phase=='seal' else print(verify(),flush=True)
