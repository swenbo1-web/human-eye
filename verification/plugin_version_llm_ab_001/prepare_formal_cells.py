"""Materialize frozen task inputs; no product, model or Blender calls."""
import copy
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    start=time.perf_counter_ns()
    for name,digest in json.loads((HERE/'PLAN_FREEZE.json').read_text()).items():
        assert sha(HERE/name)==digest,name
    plan=json.loads((HERE/'PLAN.json').read_text())
    tasks={r['case_id']:r for r in json.loads((HERE/'TASKS.json').read_text())['cases']}
    rows=[]
    for item in plan['sequence']:
        cell=HERE/'formal_cells'/item['cell'];cell.mkdir(parents=True,exist_ok=False)
        fixture=cell/'fixture.json';save(fixture,{'cases':[copy.deepcopy(tasks[item['task']])]})
        site=ROOT/'.plugin_ab_runtime'/item['version']/'venv/Lib/site-packages'
        assert site.is_dir(),site
        config={'audit_dir':str(cell/'bridge_native'),'fixture_input':str(fixture),
            'blend_file':str(ROOT/'verification/arch_expert_entry_opt_001/actual_run_01/new_owned_setup/fixture.blend'),
            'blender':'D:/Tools/blender5.2/blender.exe','expected_install_root':str(site),
            'expected_source_sha256':('e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0'
                if item['version']=='A' else 'a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b')}
        save(cell/'cell.json',config)
        workspace=ROOT/'.plugin_ab_runtime/formal_workspaces'/item['cell']
        workspace.mkdir(parents=True,exist_ok=False)
        rows.append(dict(item,cell_sha256=sha(cell/'cell.json'),fixture_sha256=sha(fixture),workspace=str(workspace)))
    save(HERE/'FORMAL_CELLS_FREEZE.json',{'schema':'plugin-ab-cells-v1','rows':rows,'prepare_elapsed_ns':time.perf_counter_ns()-start})
    print(json.dumps({'prepared':len(rows),'model_calls':0,'product_calls':0}))


if __name__=='__main__':main()
