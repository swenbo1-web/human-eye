"""Independent raw CLI image counts and static retained-correction review."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE=ROOT/'verification/m4_routed_task_benefit_001'
OUT=Path(__file__).resolve().parent
inputs={}
def read(p):
    p=Path(p); b=p.read_bytes(); inputs[str(p)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}; return b
def js(p): return json.loads(read(p))
rows=[]
for slot in ['N1','P1','P2','N2','N3','P3']:
    raw=read(Path('D:/he_routed_001/formal')/slot/'c/stdout.raw.bin')
    completed=[]
    for line in raw.splitlines():
        try: event=json.loads(line)
        except (ValueError,UnicodeError): continue
        item=event.get('item',{})
        if event.get('type')=='item.completed' and item.get('type')=='mcp_tool_call':
            content=(item.get('result') or {}).get('content',[])
            completed.append({'id':item['id'],'tool':item['tool'],'images':sum(x.get('type')=='image' for x in content)})
    consumer=js(Path('D:/he_routed_001/formal')/slot/'c/CONSUMER.json')
    rows.append({'slot':slot,'actual_completed_MCP_image_blocks':sum(x['images'] for x in completed),
                 'consumer_public_image_count':consumer['public_image_count'],'completed_tools':completed})
declared=js(HERE/'IMAGE_DELIVERY_COUNT_CORRECTION.json')
assert [r['actual_completed_MCP_image_blocks'] for r in rows]==[r['actual_CLI_image_blocks'] for r in declared['rows']]
assert all(r['actual_completed_MCP_image_blocks']==r['consumer_public_image_count'] for r in rows)
old=read(HERE/'COST_R1.md').decode().replace('\r\n','\n').replace('\r','\n')
new=read(HERE/'COST.md').decode().replace('\r\n','\n').replace('\r','\n')
diff=list(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='COST_R1.md',tofile='COST.md',n=0))
(OUT/'COST_CORRECTION.diff').write_text(''.join(diff),encoding='utf-8')
changed=[x for x in diff if x[:1] in ('-','+') and not x.startswith(('---','+++'))]
assert len(changed)==2 and all('PNG' in x for x in changed)
r1=js(HERE/'review/SOURCE_ENTRY_LIFECYCLE_ENTAILMENT_R1.json')
current=js(HERE/'review/SOURCE_ENTRY_LIFECYCLE_ENTAILMENT.json')
source=read(HERE/'launcher.py').decode()
fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run_slot')
divisions=[n for n in ast.walk(fn) if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Div)]
def path_join(n):
    if not isinstance(n,ast.BinOp) or not isinstance(n.op,ast.Div): return False
    left=(isinstance(n.left,ast.Name) and n.left.id in ('runtime','metadata')) or path_join(n.left)
    right=(isinstance(n.right,ast.Constant) and isinstance(n.right.value,str)) or (isinstance(n.right,ast.Name) and n.right.id=='slot')
    return bool(left and right)
assert all(path_join(n) for n in divisions)
assert len(r1['failures'])==1 and r1['failures'][0]['check']=='no_divided_batch_metric'
assert current['failures']==[]
stable_fields=['entailment','execution','source','evidence_sha256','checks','reviewer_role']
assert all(r1[k]==current[k] for k in stable_fields)
scorer=ROOT/'verification/m4_region_localization_consumption_001/admin/score_quality.py'
scorer_text=read(scorer).decode(); tree=ast.parse(scorer_text)
qualified=[]
for n in ast.walk(tree):
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Subscript) and isinstance(t.slice,ast.Constant) and t.slice.value=='fully_qualified' for t in n.targets):
        qualified.append(ast.unparse(n.value))
assert qualified==["bool(lifecycle and panels['passed'] and remainder and scope and all((value['passed'] for value in questions.values())))"]
result={'schema':'independent-routed001-corrections-v1','raw_image_rows':rows,
        'total_raw_CLI_image_blocks':sum(r['actual_completed_MCP_image_blocks'] for r in rows),
        'cost_MD_only_change':'28->12 image sentence with per-group detail; time/usage unchanged',
        'R1_failure_preserved':r1['failures'],'all_run_slot_divisions_are_path_joins':[ast.unparse(n) for n in divisions],
        'source_R1_to_corrected_unchanged_fields':stable_fields,
        'fully_qualified_predicate':qualified[0],
        'image_refs_delivered_is_descriptive_not_quality_predicate':True,
        'new_product_model_blender_raster_scorer_calls':0,
        'limit':'Image count and static predicate correction verified independently; no provider fee/image-token inference.'}
(OUT/'CORRECTIONS_RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'CORRECTIONS_INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'image_counts':[r['actual_completed_MCP_image_blocks'] for r in rows],
                  'total':result['total_raw_CLI_image_blocks'],'path_joins':len(divisions),
                  'static_quality_predicate_verified':True,'cost_md_changed_lines':len(changed)},ensure_ascii=False))
