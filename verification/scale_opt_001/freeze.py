"""Freeze the single approved source change and prescribed O/C experiment."""
from pathlib import Path
import hashlib, importlib.util, json, subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def main():
    installs=load(HERE/'INSTALLS.json');assert installs['passed']
    surface=ROOT/'human_eye_plugin/surface_proximity.py'
    assert sha(surface)=='2c471262b29101439293a172820c7d9183f840492d6ca2250f72122c5548cce3'
    assert load(HERE/'BOUNDED_EQUIVALENCE.json')['passed']
    a,b=load(HERE/'REGRESSIONS_BASELINE.json'),load(HERE/'REGRESSIONS_CANDIDATE.json')
    assert a['tests_run']==b['tests_run']==193 and a['failure_ids']==b['failure_ids'] and a['error_ids']==b['error_ids']==[]
    assert all(c['full_result_equal'] for c in b['full_result_differential'])
    review=load(HERE/'REGRESSION_REVIEW.json');assert review['introduced_regressions']==0
    spec=importlib.util.spec_from_file_location('scale_opt_plan',HERE/'driver.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    pairs=driver.plan();assert sum(x['logical_expected'] for x in pairs)==78
    rawdiff=subprocess.check_output(['git','diff','--numstat','--','human_eye_plugin/surface_proximity.py'],cwd=ROOT,text=True).strip()
    assert rawdiff=='4\t0\thuman_eye_plugin/surface_proximity.py'
    files=[HERE/n for n in ('driver.py','freeze.py','quality_review.py','install_candidate.py','INSTALLS.json','BOUNDED_EQUIVALENCE.json','REGRESSIONS_BASELINE.json','REGRESSIONS_CANDIDATE.json','REGRESSION_REVIEW.json')]
    files.extend([surface,HERE.parent/'scale_diag_001/quality_review.py'])
    contract=Path('D:/hefe/verification/fixes/20261110_scale_diag_review/SCALE_OPT_001.md')
    value={'task':'SCALE-OPT-001','date':'2026-11-10','baseline_evidence_commit':'b39a5d9f58aed2782225287738413982beac4920',
       'admin_review_commit':'64a6001b976230a21eb121ad031ed8302f011df8','admin_contract':str(contract),'admin_contract_sha256':sha(contract),
       'candidate':'only type(value) is int early bit_length guard and return in surface_proximity._bounded; all other product bytes unchanged',
       'product_diff_numstat':rawdiff,'versions':{k:v['source_sha256'] for k,v in installs['versions'].items()},
       'logical_cells':78,'cells_per_version':39,'static_cells':36,'T_cells':42,'static_cold':12,'static_warm':24,'T_rounds':3,'physical_chains':18,
       'entry_budget_s':30,'worker_lifetime_s':570,'accuracy_m':1e-6,'unknown_is_correct_completion':False,
       'order':pairs,'no_resampling':True,'same_fixtures_and_oracle':driver.shared_inputs(),
       'target_D48_cold_entry_fraction_of_O':.75,'target_T_chain_median_fraction_of_O':.75,
       'T_primary_cost':'shared original child whole_chain_ns (same scope); new wrapper whole/full process costs also reported',
       'quality_fields':'same geometric facts/witness/work/reasons; runtime/source/trace IDs legitimately differ; expired never correct',
       'expected_G_mid_high':'original unknown reasons and limits remain; no expanded admissible geometry',
       'regressions':{'run_each':193,'pass_each':191,'known_baseline_failures':a['failure_ids'],'introduced_failures':0,'current_contract_review':review},
       'learning_binding':{'context_bound':False,'host_epoch':5,'rebind_required':True,'task_sync':'pending; no borrowed handle'},
       'no_LLM_or_Native_rerun':True,'tokens':'N/A','fees':'N/A','coordinator_model_cost':'unmeasured',
       'default_MCP_Hook':'unchanged by this batch; administrator separately owns user-authorized later deployment',
       'files_sha256':{str(p.resolve()):sha(p) for p in files}}
    target=HERE/'FREEZE.json';assert not target.exists()
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'freeze_sha256':sha(target),'logical_cells':78,'versions':value['versions']}))
if __name__=='__main__':main()
