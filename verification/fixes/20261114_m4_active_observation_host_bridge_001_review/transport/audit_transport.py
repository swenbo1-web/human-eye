"""Independent offline host/capture/PNG/stdio review. Never imports product."""
from pathlib import Path
from fractions import Fraction as F
import base64, copy, hashlib, io, json, struct
import numpy as np
from PIL import Image

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=ROOT/'verification/m4_active_observation_host_bridge_001'
OUT=Path(__file__).resolve().parent
checks=[];inputs={};pixel_rows=[]
def raw(p):
    p=Path(p);v=p.read_bytes();inputs[str(p)]=hashlib.sha256(v).hexdigest();return v
def sha(v):return hashlib.sha256(v).hexdigest()
def read(p):return json.loads(raw(p))
def ck(name,value,detail=None):checks.append({'check':name,'passed':bool(value),'detail':detail})
archive=read(H/'EXTERNAL_ARCHIVE.json')
mapping={str(Path(r['original_path'])):ROOT/r['archive_path'] for r in archive['files']}
relative={r['original_relative_path']:ROOT/r['archive_path'] for r in archive['files']}
def orig(p):return mapping[str(Path(p))]
def rp(p):return relative[p]
for r in archive['files']:
    blob=raw(ROOT/r['archive_path'])
    ck('archive:'+r['original_relative_path'],sha(blob)==r['sha256'] and len(blob)==r['bytes'] and blob==raw(r['original_path']))

fixture=read(rp('payload/QA_GEOMETRY.json'));fd=read(rp('payload/FIXTURE.json'))
old=read(fd['source']);by_name={o['name']:o for o in fixture['objects']}
ck('fixture_sha',sha(raw(rp('payload/QA_GEOMETRY.json')))==fd['fixture_sha256'])
coordinates=0
for before,after in zip(old['objects'],fixture['objects']):
    wanted=[[F(x)*F(375,256) for x in pt] for pt in before['vertices']]
    actual=[[F(x) for x in pt] for pt in after['vertices']]
    ck('exact_scale:'+after['name'],wanted==actual and before['triangles']==after['triangles'])
    ck('binary32:'+after['name'],all(F(struct.unpack('f',struct.pack('f',float(x)))[0])==x for pt in actual for x in pt))
    coordinates+=3*len(actual)
ck('fixture_counts',coordinates==5730 and len(by_name)==28)

# Reconstruct full capture from actual QA socket delta resources, independent
# of the product decoder, then compare to the server's saved expanded capture.
captures={}
for run in ('acceptance_01','acceptance_02'):
    resources={};number=0
    qa_rx=sorted(k for k in relative if k.startswith('run/'+run+'/qa/rpc_') and k.endswith('/RX.bin'))
    for key in qa_rx:
        outer=read(rp(key));text=outer.get('result',{}).get('result') if isinstance(outer.get('result'),dict) else None
        if not isinstance(text,str) or not text.startswith('HUMAN_EYE_BLENDER_MCP:'):continue
        packet=json.loads(text.split(':',1)[1])['result']
        if packet.get('schema')!='human-eye-scene-delta-v1':continue
        for res in packet['resources']:resources[res['id']]=res
        cap=copy.deepcopy(packet['capture'])
        for mesh in cap['meshes']:
            ref=mesh.pop('_scene_resource');res=resources[ref['id']]
            ck(key+':resource:'+ref['id'],res['revision']==ref['revision'])
            mat=ref['matrix'];scale=ref['scale']
            mesh['vertices']=[[(sum(mat[r][c]*pt[c] for c in range(3))+mat[r][3])*scale for r in range(3)] for pt in res['vertices_local']]
            mesh['faces']=res['faces'];mesh['edges']=res['edges']
        number+=1
        recorded=read(rp(f'run/{run}/server/CAPTURE_{number:02d}.json'))
        ck(f'{run}:wire_capture_{number}',cap==recorded)
        captures[(run,number)]=recorded
    ck(run+':capture_count',number==(2 if run=='acceptance_01' else 3))

for (run,n),cap in captures.items():
    tag=f'{run}:capture{n}'
    ck(tag+':units',cap['unit']=='m' and cap['coordinate_frame']=='world' and cap['source']=='blender')
    if len(cap['meshes'])!=28:continue
    ck(tag+':geometry_counts',sum(len(x['vertices']) for x in cap['meshes'])==1910 and sum(len(x['faces']) for x in cap['meshes'])==3336)
    for mesh in cap['meshes']:
        name=mesh['name'].replace('_Renamed','')
        # Compare geometry against its unique unchanged source rather than name:
        exact=[o for o in fixture['objects'] if [[float(F(x)) for x in pt] for pt in o['vertices']]==mesh['vertices']]
        ck(tag+':world_geometry:'+mesh['name'],len(exact)==1)
        if exact:ck(tag+':triangles:'+mesh['name'],{tuple(t) for t in exact[0]['triangles']}=={tuple(t) for t in mesh['faces']})

def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def inspect_pixels(tag,frame,obs,cap,index):
    png=raw(orig(frame['image_path']));arrays=raw(orig(frame['arrays_path']))
    ck(tag+':frame_hashes',sha(png)==frame['image_sha256'] and sha(arrays)==frame['arrays_sha256'])
    with np.load(io.BytesIO(arrays),allow_pickle=False) as z:color=z['color'];depth=z['depth'];owner=z['owners']
    with Image.open(io.BytesIO(png)) as image:ck(tag+':PNG_RGB',image.mode=='RGB' and image.size==(512,512) and np.array_equal(np.asarray(image),color))
    ck(tag+':array_types',color.dtype==np.uint8 and owner.dtype==np.int32 and depth.dtype==np.float64 and color.shape==(512,512,3) and owner.shape==depth.shape==(512,512))
    ck(tag+':depth_owner',np.all(owner>=-1) and np.all(owner<len(cap['meshes'])) and np.isposinf(depth[owner==-1]).all() and np.isfinite(depth[owner>=0]).all() and (depth[owner>=0]>0).all())
    ck(tag+':payload_size',sum(x.nbytes for x in (color,owner,depth))==frame['array_payload_bytes'])
    boundary=np.zeros(owner.shape,dtype=bool)
    for a,b in [((slice(None,-1),slice(None)),(slice(1,None),slice(None))),((slice(None),slice(None,-1)),(slice(None),slice(1,None)))]:
        diff=color[a].astype(np.int32)-color[b].astype(np.int32)
        edge=(owner[a]!=owner[b]) & (np.sum(diff*diff,axis=2)>=576)
        boundary[a]|=edge;boundary[b]|=edge
    poses={p['name']:p for p in index['cameras']['views']};pose=poses[frame['view_name']]
    readable=set()
    for row in obs['pixel_rows']:
        i=row['object_index'];mesh=cap['meshes'][i];a,b,c=[list(map(F,mesh['vertices'][j])) for j in mesh['faces'][0]]
        normal=cross(sub(b,a),sub(c,a));front=sum(x*F(y) for x,y in zip(normal,pose['direction_rational']))>0
        surface=int(np.count_nonzero(owner==i));edges=int(np.count_nonzero(boundary & (owner==i)));good=front and surface>=16 and edges>=4
        ck(tag+':pixel:'+row['roi_id'],(surface,edges,front,good)==(row['visible_surface_pixels'],row['contrasting_boundary_pixels'],row['front_facing'],row['readable']))
        ck(tag+':pixel_host:'+row['roi_id'],row['host_id']==mesh['object_id'] and row['object_name']==mesh['name'])
        ck(tag+':thresholds:'+row['roi_id'],(row['minimum_surface_pixels'],row['minimum_boundary_pixels'],row['minimum_rgb_boundary_contrast'])==(16,4,24))
        pixel_rows.append({'frame':tag,'roi':row['roi_id'],'surface':surface,'boundary':edges,'front':front,'readable':good})
        if good:readable.add(row['roi_id'])
    ck(tag+':readable_ids',readable==set(obs['readable_roi_ids']))
    return readable

cases=[('acceptance_01','ordinary',1,1),('acceptance_01','same_source_repeat',2,None),('acceptance_02','recovery_rename_baseline',1,1),('acceptance_02','renamed_source',2,2),('acceptance_02','nonplanar_source',3,3)]
metadata={};new_frames={};rpc_count=0;tool_calls=0;image_count=0;text_bytes=0
for run in ('acceptance_01','acceptance_02'):
    responses=[]
    keys=sorted(k for k in relative if k.startswith('run/'+run+'/stdio/rpc_') and k.endswith('/TX.bin'))
    for key in keys:
        tx=read(rp(key));rxbytes=raw(rp(key.replace('/TX.bin','/RX.bin')));rx=json.loads(rxbytes);responses.append(rxbytes)
        rpc_count+=1;tool_calls+=tx['method']=='tools/call'
        ck(run+':rpc_id:'+str(tx['id']),rx['id']==tx['id'])
        case=next((x for x in cases if x[:2]==(run,tx['id'])),None)
        if case:
            result=rx['result'];texts=[c for c in result['content'] if c['type']=='text'];images=[c for c in result['content'] if c['type']=='image']
            ck(run+':content:'+tx['id'],not result['isError'] and len(texts)==1)
            meta=json.loads(texts[0]['text']);metadata[tx['id']]=meta;text_bytes+=len(texts[0]['text'].encode('utf8'))
            rb=read(rp(f'run/{run}/consumer_{tx["id"]}/READBACK.json'))
            ck(tx['id']+':consumer_text',rb['text']==meta and rb['model_calls']==0 and rb['model_image_consumption']=='not_tested')
            ck(tx['id']+':delivery_layers',meta['facts']['image_delivery_scope']=='local_core_validation' and meta['image_delivery']['consumer_read_status']=='unconfirmed' and meta['image_delivery']['mcp_content_constructed_image_count']==len(images))
            ck(tx['id']+':image_counts',len(images)==len(meta['frames'])==rb['image_blocks_read'])
            for i,(block,frame,rec) in enumerate(zip(images,meta['frames'],rb['images'])):
                blob=base64.b64decode(block['data'],validate=True);image_count+=1
                ck(tx['id']+':native:'+str(i),block['mimeType']=='image/png' and blob==raw(orig(frame['image_path']))==raw(orig(rec['path'])) and sha(blob)==rec['PNG_sha256']==frame['image_sha256'])
                with Image.open(io.BytesIO(blob)) as image:
                    ck(tx['id']+':decoded:'+str(i),image.size==(512,512) and image.mode=='RGB' and sha(np.asarray(image).tobytes())==rec['RGB_sha256'])
            cap=captures[(run,case[2])]
            binding=meta['binding'];facts=meta['facts'];scope=facts['scope']
            ck(tx['id']+':capture_revision',binding['scene_revision']==cap['revision'] and binding['document_epoch']==cap['host_identity']['document_epoch'])
            for i,host in enumerate(binding['objects']):
                mesh=cap['meshes'][i]
                ck(tx['id']+':mapping:'+str(i),host=={'object_index':i,'host_id':mesh['object_id'],'object_name':mesh['name'],'instance_id':cap['host_identity']['object_instances'][mesh['object_id']]})
            supported={r['object_index'] for r in facts['regions']}
            ck(tx['id']+':scope',scope['capture_object_count']==len(cap['meshes']) and scope['supported_roi_object_count']==len(supported) and {r['object_index'] for r in scope['objects_without_supported_roi']}==set(range(len(cap['meshes'])))-supported and scope['all_objects_participate_in_occlusion'])
            if case[3] is not None:
                index=read(rp(f'run/{run}/server/INDEX_{case[3]:02d}.json'));direct=read(rp(f'run/{run}/DIRECT_{tx["id"]}.json'))
                ck(tx['id']+':same_capture',sha(raw(rp(f'run/{run}/server/CAPTURE_{case[2]:02d}.json')))==index['actual_capture_sha256']==direct['same_capture_sha256'])
                mapped_regions={}
                for region in index['regions']:
                    mesh=cap['meshes'][region['object_index']]
                    mapped_regions[region['roi_id']]={k:region[k] for k in ('normal','vertices','triangle_indices')}
                    mapped_regions[region['roi_id']]['host']={'host_object_id':mesh['object_id'],'instance':cap['host_identity']['object_instances'][mesh['object_id']],'name':mesh['name']}
                ck(tx['id']+':DIRECT_regions',mapped_regions==direct['direct_regions'])
                for k in ('classifications','view_masks'):ck(tx['id']+':DIRECT_'+k,index[k]==direct['direct_'+k])
                ck(tx['id']+':classification_count',sum(len(x) for x in index['classifications'].values())==(0 if tx['id']=='nonplanar_source' else 36))
                ck(tx['id']+':capture_host_identity',index['host_identity']==cap['host_identity'])
                covered=set();ids=[r['roi_id'] for r in index['regions']];gains=[]
                for frame,obs in zip(meta['frames'],facts['observations']):
                    view=frame['view_name'];tag=run+':'+tx['id']+':'+view
                    ck(tag+':frame_binding',frame['host_binding_sha256']==binding['binding_sha256'] and frame['source_revision']==cap['revision'] and frame['image_ref']==obs['image_ref'] and frame['image_sha256']==obs['image_sha256'])
                    readable=inspect_pixels(tag,frame,obs,cap,index);mask=index['view_masks'][view];predicted={identity for n,identity in enumerate(ids) if mask&(1<<n)}
                    add=(predicted&readable)-covered;covered|=predicted&readable;gains.append(len(add));new_frames[frame['image_path']]=frame
                ck(tx['id']+':covered',covered==set(facts['coverage']['covered_roi_ids']))
                if tx['id']!='nonplanar_source':
                    ck(tx['id']+':chain',gains==[2,3] and facts['coverage']['observed_views']==['SCENE','BACK'] and len(covered)==5)
                    unknown=[r for r in facts['regions'] if r['status']=='unknown'];ck(tx['id']+':unknown',len(unknown)==1 and unknown[0]['object_name']=='Obj_006' and unknown[0]['reason']=='finite_camera_pool_uncovered')
        elif tx['id']=='bad_active_query':ck('bad_query_expected_error',rx['result']['isError'])
        elif tx['id']=='ping_after_bad_request':ck('ping_after_bad',rx['result']=={})
        elif tx['id']=='old_readonly_regression':ck('old_readonly_after_bad',not rx['result']['isError'])
    ck(run+':stdout_exact_RX',raw(rp('run/'+run+'/stdio/stdout.raw.bin'))==b''.join(responses))
ck('RPC_and_image_counts',(rpc_count,tool_calls,image_count,len(new_frames),len(pixel_rows))==(12,7,8,6,36))
ordinary=metadata['ordinary'];hot=metadata['same_source_repeat']
ck('hot_same_facts_frames',ordinary['facts']==hot['facts'] and ordinary['frames']==hot['frames'] and ordinary['binding']==hot['binding'])
ck('hot_no_new_prepare_render',hot['work']['result_cache_hit'] and hot['work']['prepare_calls']==hot['work']['geometry_parse_calls']==hot['work']['raster_attempts']==0 and hot['work']['capture_calls']==1)
before=captures[('acceptance_02',1)];after=captures[('acceptance_02',2)]
def instances(c):return {c['host_identity']['object_instances'][m['object_id']]:m for m in c['meshes']}
bi=instances(before);ai=instances(after);ck('rename_instance_set',bi.keys()==ai.keys())
ck('rename_geometry_unchanged',all((bi[k]['vertices'],bi[k]['faces'])==(ai[k]['vertices'],ai[k]['faces']) for k in bi))
ck('rename_one_name_id_change',sum(bi[k]['name']!=ai[k]['name'] for k in bi)==1 and sum(bi[k]['object_id']!=ai[k]['object_id'] for k in bi)==1)
mb=metadata['recovery_rename_baseline'];ma=metadata['renamed_source']
ck('rename_binding_changed',mb['binding']['binding_sha256']!=ma['binding']['binding_sha256'] and mb['binding']['scene_revision']!=ma['binding']['scene_revision'] and mb['binding']['geometry_identity']==ma['binding']['geometry_identity'])
ck('rename_image_refs_changed_same_PNG',all(x['image_ref']!=y['image_ref'] and x['image_sha256']==y['image_sha256'] for x,y in zip(mb['frames'],ma['frames'])))
npmeta=metadata['nonplanar_source'];npmesh=captures[('acceptance_02',3)]['meshes'][0]
verts=[[F(x) for x in p] for p in npmesh['vertices']];normal=cross(sub(verts[1],verts[0]),sub(verts[2],verts[0]));volume=sum(a*b for a,b in zip(normal,sub(verts[3],verts[0])))
ck('nonplanar_actual_volume_nonzero',len(verts)==4 and len(npmesh['faces'])==2 and volume!=0 and max(p[2] for p in verts)-min(p[2] for p in verts)==F(1,256))
ck('nonplanar_unknown_zero_render',npmeta['status']=='unknown' and npmeta['observation_status']=='no_supported_regions' and not npmeta['facts']['regions'] and not npmeta['frames'] and npmeta['work']['raster_attempts']==0)
result={'commit':'32a1c6eb47cfa84133d92199387339d407a33cb5','passed':all(x['passed'] for x in checks),'check_count':len(checks),'failed':[x for x in checks if not x['passed']],'checks':checks,'pixels':pixel_rows,'new_frames':len(new_frames),'native_image_blocks':image_count,'RPCs':rpc_count,'tools_calls':tool_calls,'active_text_bytes':text_bytes,'inputs_sha256':inputs,'product_model_Blender_raster_calls':0,'inspection_correction':'Initial schema inspection assumed content[-1] is text and got KeyError; corrected by selecting type=text. No product code executed.'}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('checks','pixels','inputs_sha256')},ensure_ascii=False))
