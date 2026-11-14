"""Source-only supplement: literal AST and JSON reads, no imports of project code."""
from pathlib import Path
import ast,hashlib,json
R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_region_localization_consumption_001'
O=Path(__file__).parent
inputs={}
def raw(p):
 b=Path(p).read_bytes();inputs[str(p)]=hashlib.sha256(b).hexdigest();return b
def js(p):return json.loads(raw(p))
p=js(H/'PREP_FROZEN.json');f=js(H/'FROZEN.json');note=js(H/'FREEZE_GENERATION_NOTE.json')
pm=p['files_sha256'];fm=f['files_sha256'];shared=set(pm)&set(fm)
changed=[x for x in sorted(shared) if pm[x]!=fm[x]]
tree=ast.parse(raw(H/'bridge.py'))
schemas={}
for node in tree.body:
 if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('GENERIC','ACTIVE','SCENE_DATA','READ_IMAGES'):
  schemas[node.targets[0].id]=ast.literal_eval(node.value)
source_files=['bridge.py','launcher.py','native_tools.py','fake_cli.py','bootstrap.py','inputs/PROMPT.txt']
same={}
for n in source_files:
 path=H/n;current=hashlib.sha256(raw(path)).hexdigest();key=str(path)
 same[n]=pm[key]==fm[key]==current
result={
 'scope':'static evidence only; no new CLI, model, product, Blender or raster calls',
 'frozen_shared_files':len(shared),'frozen_shared_changed':changed,
 'frozen_preparation_count':len(pm),'frozen_formal_count':len(fm),
 'freeze_note_consistent':changed==[str(H/'freeze_sources.py')] and pm[changed[0]]==note['preparation_utility_sha256'] and fm[changed[0]]==note['formal_utility_sha256'],
 'execution_prompt_source_byte_identical_preparation_formal_current':same,
 'tool_descriptions':{k:{'name':v['name'],'characters':len(v['description']),'description':v['description']} for k,v in schemas.items()},
 'prompt':raw(H/'inputs/PROMPT.txt').decode(),
 'distinction':'same downstream preparation transport and product route; fake CLI does not exercise provider tool exposure, actual model selection or model evidence consumption',
 'inputs':inputs,
}
(O/'STATIC_REVIEW.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('tool_descriptions','prompt','inputs')},ensure_ascii=False,indent=2))
