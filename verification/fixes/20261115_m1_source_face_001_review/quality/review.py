"""Root independent saved semantic/dataflow review. No product or author code imported."""
from pathlib import Path
from fractions import Fraction as F
import json,hashlib,re,sys,ast
sys.path.insert(0,'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np

N=Path('C:/Users/Administrator/.codex/worktrees/m1-source-face-binding-001/hefe/verification/m1_source_face_binding_001')
OLD=Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_occluded_scene_transfer_001')
R=Path('D:/he_source_face_001/formal');OUT=Path(__file__).parent
load=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks=[]
def check(label,ok):
 checks.append({'check':label,'passed':bool(ok)})
 if not ok:print('FAIL',label)
def walk(x):
 if isinstance(x,dict):
  yield x
  for v in x.values():yield from walk(v)
 elif isinstance(x,list):
  for v in x:yield from walk(v)
def rid(oi,ids):return 'object_'+str(oi).zfill(2)+'_triangles_'+'_'.join(map(str,ids))
def identity(x):return rid(x['object_index'],x['source_triangle_indices'])
def vec(x):return tuple(F(str(v)) for v in x)
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def dot(a,b):return sum(x*y for x,y in zip(a,b))
prior=load('D:/hefe/verification/fixes/20261115_m4_occluded_001_review/quality/RESULT_R1.json')
check('prior independent geometric/pixel review passed',prior['passed'])
for p,h in prior['inputs'].items():check('prior input retained '+Path(p).name,sha(p)==h)
for name in ['TRUTH.json','PIXEL_TRUTH.json']:check('same verified truth '+name,(N/'admin'/name).read_bytes()==(OLD/'admin'/name).read_bytes())
for name in ['SCENE_GEOMETRY_RATIONAL.json','CAMERAS.json']:check('same raw input '+name,(N/'inputs'/name).read_bytes()==(OLD/'inputs'/name).read_bytes())
truth=load(N/'admin/TRUTH.json');pixel=load(N/'admin/PIXEL_TRUTH.json');norm=load(N/'admin/NORMALIZED.json')
scene=load(N/'inputs/SCENE_GEOMETRY_RATIONAL.json');names=[x['name'] for x in scene['objects']]
tr={x['roi_id']:x for x in truth['regions']};known=set(prior['geometry']['complete_readable']);remaining=prior['geometry']['remaining_reasons']
pix={(f['view_name'],x['roi_id']):x for f in pixel['frames'] for x in f['rows']}
olds={f['view_name']:{k:v.copy() for k,v in np.load(f['NPZ']).items()} for f in pixel['native_frame_descriptors']}
offsets=np.cumsum([0]+[len(x['triangles']) for x in scene['objects']])
slot_results=[];all_codes={}
for slot in norm['slots']:
 sid=slot['slot_id'];base=R/sid/'o';final=Path(slot['raw_answer_path']).read_text(encoding='utf8');clean=final.replace('**','').replace('`','');sources={'final':final}
 check(sid+' original final hash',sha(slot['raw_answer_path'])==slot['raw_answer_sha256'])
 for s in slot['sources']:
  check(sid+' source '+s['id'],sha(s['path'])==s['sha256']);sources[s['id']]=Path(s['path']).read_text(encoding='utf8')
  if s['kind']=='tool_result':
   payload=load(s['path']);sources[s['id']]+='\n'+'\n'.join(x['text'] for x in payload.get('result',{}).get('content',[]) if x.get('type')=='text')
  if s['kind']=='cited_artifact':check(sid+' actual final citation',s['path'].replace('\\','/') in final.replace('\\','/'))
 for row in walk(slot):
  if 'source_id' in row and 'excerpt' in row:check(sid+' exact source excerpt',row['excerpt'].replace('\r\n','\n') in sources[row['source_id']].replace('\r\n','\n'))
 # Parse human inventory independently of author normalization.
 inventory={};witness_numbers=[]
 for line in clean.splitlines():
  if not line.startswith('|'):continue
  cells=[x.strip() for x in line.strip('|').split('|')]
  hits=[i for i,n in enumerate(names) if re.search(r'\b'+n+r'\b',cells[0])]
  if not hits:continue
  oi=hits[0]
  if len(cells)==7 and re.match(r'^\d+\s',cells[0]):
   for j,code in enumerate(cells[1:]):
    if code in ['—','-']:continue
    inventory[rid(oi,[2*j,2*j+1])]=code
  elif len(cells)==4 and not re.search(r'\[\d+,\s*\d+\]',cells[0]):
   for col in [1,2,3]:
    pairs=re.findall(r'(?:\[(\d+),\s*(\d+)\]|(\d+)–(\d+))(?:\s*@?(SCENE|LEFT|BACK))?',cells[col])
    for a,b,c,d,v in pairs:inventory[rid(oi,[int(a or c),int(b or d)])]=({'SCENE':'S','LEFT':'L','BACK':'B'}[v] if col==1 else 'O' if col==2 else 'N')
  elif len(cells)==5:
   pair=re.search(r'\[(\d+),\s*(\d+)\]',cells[1])
   if pair:
    key=rid(oi,list(map(int,pair.groups())));inventory[key]={'SCENE':'S','LEFT':'L','BACK':'B'}[cells[2]];witness_numbers.append((key,cells[2],int(cells[3].replace(',','')),int(cells[4].replace(',',''))))
  elif len(cells)==3:
   for col,code in [(1,'N'),(2,'O')]:
    for a,b in re.findall(r'\[(\d+),\s*(\d+)\]',cells[col]):inventory[rid(oi,[int(a),int(b)])]=code
  elif len(cells)==4:
   pair=re.search(r'\[(\d+),\s*(\d+)\]',cells[0])
   if pair:witness_numbers.append((rid(oi,list(map(int,pair.groups()))),{'S':'SCENE','L':'LEFT','B':'BACK'}[cells[1]],int(cells[2].replace(',','')),int(cells[3].replace(',',''))))
 check(sid+' raw final full inventory',len(inventory)==61 and set(inventory)==set(tr))
 for key,code in inventory.items():
  check(sid+' raw inventory '+key,(key in known and code in 'SLB') or (key in remaining and code==('N' if remaining[key]=='no_front_facing_candidate' else 'O')))
  if code in 'SLB':check(sid+' raw selected witness '+key,pix[{'S':'SCENE','L':'LEFT','B':'BACK'}[code],key]['complete_readable'])
 for key,view,ns,nb in witness_numbers:check(sid+' raw numerical witness '+key,pix[view,key]['surface_pixels']==ns and pix[view,key]['boundary_pixels']==nb)
 check(sid+' normalized exact inventory',{identity(p['identity']) for p in slot['panels']}==set(inventory))
 frames=load(base/'OBSERVATIONS.json')['frames'];refs={f['ref']:f for f in frames};byview={f['view_name']:f for f in frames}
 check(sid+' four actual task frames',len(frames)==4 and set(byview)=={'SCENE','LEFT','BACK','TOP'})
 for frame in frames:
  check(sid+' frame sha '+frame['view_name'],sha(frame['NPZ'])==frame['NPZ_sha256'] and sha(frame['PNG'])==frame['PNG_sha256'])
  arrays=np.load(frame['NPZ'])
  for key in ['color','depth','owners','triangle_ids']:check(sid+' saved frame same '+frame['view_name']+' '+key,np.array_equal(arrays[key],olds[frame['view_name']][key]))
  check(sid+' raw final actual frame ref '+frame['view_name'],frame['ref'] in final)
 for p in slot['panels']:
  key=identity(p['identity']);covered=key in known
  check(sid+' normalized status '+key,p['status']==('covered' if covered else 'unknown'))
  if not covered:check(sid+' normalized reason '+key,p['reason_code']==remaining[key])
  for w in p.get('views',[]):
   check(sid+' witness bound '+key,w['ref'] in refs and refs[w['ref']]['view_name']==w['view'] and pix[w['view'],key]['complete_readable'])
   for field in ['surface_pixels','boundary_pixels']:
    if field in w:check(sid+' witness number '+key+' '+field,w[field]==pix[w['view'],key][field])
 check(sid+' remaining exact',{identity(x) for x in slot['remaining']}==set(remaining))
 for p in slot['pixel_targets']:
  key=identity(p['identity']);t=tr[key];expected=prior['geometry']['pixel_targets'][p['id']]
  check(sid+' sample identity',key==expected)
  check(sid+' sample center',vec(p['center_world_m'])==vec(t['center_world_m']))
  a=vec(p['front_direction_world']);b=vec(t['front_direction_world']);check(sid+' sample front',cross(a,b)==(0,0,0) and dot(a,b)>0)
  if 'quad_world_m' in p:check(sid+' sample corners',{vec(q) for q in p['quad_world_m']}=={vec(q) for q in t['quad_world_m']})
  if 'bounds_world_m' in p:check(sid+' sample bounds',[tuple(min(F(q[i]) for q in t['quad_world_m']) for i in range(3)),tuple(max(F(q[i]) for q in t['quad_world_m']) for i in range(3))]==list(map(vec,p['bounds_world_m'])))
  check(sid+' sample image binding',p['ref'] in refs and refs[p['ref']]['view_name']==p['view'])
  # Parse final front phrase independently; this catches the reported center/front transcription defect.
  segment=clean[clean.index(p['id']):];m=re.search(r'[Ff]ront orientation:\s*\(([^)]+)\)',segment)
  check(sid+' raw front transcript '+p['id'],m is not None and tuple(F(x.strip()) for x in m.group(1).split(','))==a)
 for p in slot['source_targets']:check(sid+' source target '+p['id'],p['status']=='unknown' and p['reason_code']==remaining[identity(p['identity'])])
 check(sid+' unsupported complete',len(slot['unsupported'])==1 and slot['unsupported'][0]['identity']['source_triangle_indices']==[0,1,2,3] and slot['unsupported'][0]['identity']['object_index']==11)
 check(sid+' finite scope/no contradictions',slot['finite_pool_only'] and not slot['global_invisibility_overclaim'] and not slot['contradictions'])
 codes=[]
 for path in sorted(base.glob('tool_*/REQUEST.json')):
  request=load(path)['params'];response=load(path.parent/'RESPONSE.json')
  check(sid+' successful execution '+path.parent.name,not response.get('error') and response['result'].get('isError') is not True)
  code=request['arguments'].get('code','');ast.parse(code);codes.append({'attempt':path.parent.name,'name':request['name'],'code':code,'path':str(path)})
 all_codes[sid]=codes
 text='\n'.join(x['code'] for x in codes);has_ranges='source_triangle_index_ranges' in text;geometric=('np.cross(' in text)
 check(sid+' actual ranges/geometry branch',has_ranges==sid.startswith('B') and geometric==sid.startswith('A'))
 check(sid+' full witness recomputation present',all(x in text for x in ['boundary','triangle_ids','complete_witness_pixel_index']))
 obs=json.loads(load(base/'tool_01/RESPONSE.json')['result']['content'][0]['text']);regions=[dict(zip(obs['regions']['columns'],r)) for r in obs['regions']['rows']]
 check(sid+' capability correctly received',('source_triangle_index_ranges' in obs['regions']['columns'])==sid.startswith('B'))
 if sid.startswith('B'):
  arr=np.load(byview['LEFT']['NPZ']);roi=list(arr['patch_roi_ids']);mapping=arr['face_patch_ids'];starts=arr['face_patch_offsets']
  for reg in regions:
   indices=[i for lo,hi in reg['source_triangle_index_ranges'] for i in range(lo,hi+1)];oi=reg['object_index'];expected_ids=(np.flatnonzero(mapping[starts[oi]:starts[oi+1]]==roi.index(reg['roi_id']))).tolist()
   check(sid+' actual delivered source mapping '+reg['roi_id'],indices==expected_ids)
 slot_results.append({'slot':sid,'raw_inventory_count':len(inventory),'explicit_witness_number_rows':len(witness_numbers),'ranges_used':has_ranges,'geometric_inverse_observed':geometric,'all_witness_recomputed':True,'formal_frames':len(frames),'tool_calls':len(codes)})

before=load(N/'admin/NORMALIZED_B.json');after=load(N/'admin/NORMALIZED_B_R1.json');diffs=[]
def diff(a,b,path=''):
 if type(a)!=type(b):diffs.append((path,a,b));return
 if isinstance(a,dict):
  for k in a.keys()|b.keys():diff(a.get(k),b.get(k),path+'/'+str(k))
 elif isinstance(a,list):
  if len(a)!=len(b):diffs.append((path,a,b));return
  for i,(x,y) in enumerate(zip(a,b)):diff(x,y,path+'/'+str(i))
 elif a!=b:diffs.append((path,a,b))
diff(before,after)
check('B correction only front coordinate elements',len(diffs)==6 and all('/pixel_targets/' in x[0] and '/front_direction_world/' in x[0] for x in diffs))
out={'passed':all(c['passed'] for c in checks),'assertions':len(checks),'failed':[x for x in checks if not x['passed']],'checks':checks,'slots':slot_results,'normalization_B_diffs':diffs,'dataflow_requests':all_codes,'new_product_model_Blender_raster_calls':0,'method':'Same-byte prior independently checked truth, fresh raw final inventory parsing, original source excerpts, formal saved-array comparison, manual full request/dataflow reading plus branch assertions. No author or product code imported.','limitations':['Prior independent geometry/pixels reused; no new renderer proof.','No causal inference about total performance or reason for witness recomputation.','AST strings assist manual audit, not a generic proof of arbitrary Python dataflow.']}
with (OUT/'RESULT.json').open('x',encoding='utf8',newline='\n') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps({'passed':out['passed'],'assertions':len(checks),'failed':out['failed'],'slots':slot_results,'B_diffs':diffs}))
