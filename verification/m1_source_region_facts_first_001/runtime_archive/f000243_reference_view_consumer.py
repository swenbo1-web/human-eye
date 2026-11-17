"""Reference feature consumer: independent exact 3D rays and actual RNA.

The producer uses projected barycentric depth. This checker intersects exact
dyadic 3D lines with all native triangles, then checks actual camera direction.
"""
import base64,copy,hashlib,math,struct,time
from fractions import Fraction as Q
from . import mesh_structure as m,surface_geometry as g,reference_view as v,native_observation as n


class ExactVisibility:
    def __init__(self,native,deadline):
        self.deadline=deadline;self.tests=0;self.triangles=[]
        for obj in native['objects']:
            vertices=[tuple(Q(x) for x in p) for p in obj['world_vertices']]
            for index,face in enumerate(obj['faces']):
                a,b,c=(vertices[i] for i in face);normal=g.cross(g.sub(b,a),g.sub(c,a))
                v.require(any(normal),'degenerate_visibility_triangle')
                self.triangles.append((obj['object_id'],index,(a,b,c),normal))

    def __call__(self,native,sample,candidate,deadline):
        p=tuple(Q(x) for x in sample['point']);direction=tuple(Q(x) for x in candidate['eye']);hits=[];ambiguous=False
        eps=max(candidate['span_m']*1e-9,128*max(math.ulp(float(x)) for x in sample['point']))
        v.require(eps<candidate['span_m']/3072,'consumer_visibility_precision');epsilon=Q(eps)
        for name,index,triangle,normal in self.triangles:
            v.check(self.deadline);self.tests+=1;v.require(self.tests<=v.LIMITS['ray_triangle_tests'],'consumer_ray_budget')
            denominator=g.dot(normal,direction)
            if denominator==0:
                if g.dot(normal,g.sub(triangle[0],p))==0:
                    low=high=None;possible=True
                    for j in range(3):
                        edge=g.sub(triangle[(j+1)%3],triangle[j]);base=g.dot(g.cross(edge,g.sub(p,triangle[j])),normal)
                        slope=g.dot(g.cross(edge,direction),normal)
                        if slope==0:
                            if base<0:possible=False;break
                        elif slope>0:low=max(low,-base/slope) if low is not None else -base/slope
                        else:high=min(high,-base/slope) if high is not None else -base/slope
                    if possible and (low is None or high is None or low<=high):ambiguous=True
                continue
            depth=g.dot(normal,g.sub(triangle[0],p))/denominator
            hit=g.add(p,g.mul(direction,depth))
            if all(g.dot(g.cross(g.sub(triangle[(j+1)%3],triangle[j]),g.sub(hit,triangle[j])),normal)>=0 for j in range(3)):
                hits.append((depth,name,index))
        if ambiguous or not hits:return False
        closest=max(row[0] for row in hits)
        names={(name,index) for depth,name,index in hits if abs(depth-closest)<=epsilon}
        return abs(closest)<=epsilon and names=={(sample['object_id'],sample['triangle'])}


def validate_capabilities(caps):
    from .blender_host import _REFERENCE_VIEW_SHA256
    v.require(type(caps) is dict and set(caps)=={'protocol','helper_sha256','native','limits','read_only','execution_authority'}
        and caps['protocol']==v.PROTOCOL and caps['helper_sha256']==_REFERENCE_VIEW_SHA256
        and caps['limits']==v.LIMITS and caps['read_only'] is True and caps['execution_authority'] is False,'capability')
    n.validate_native_capabilities(caps['native']);return caps


def validate_result(value,*,object_id,patch,request_id,deadline_ns,capabilities):
    validate_capabilities(capabilities);v.check(deadline_ns)
    fields={'protocol','request_id','object_id','patch','packet','evidence','display','plan','frames','deadline_ns','finished_ns','restored','read_only','execution_authority'}
    v.require(type(value) is dict and set(value)==fields and value['protocol']==v.PROTOCOL and value['request_id']==request_id
        and value['object_id']==object_id and value['patch']==patch and value['deadline_ns']==deadline_ns
        and type(value['finished_ns']) is int and value['finished_ns']<deadline_ns and value['restored'] is True
        and value['read_only'] is True and value['execution_authority'] is False,'response_binding')
    packet=value['packet'];v.require(type(packet) is dict and set(packet)=={'schema','request_id','source','raw','triangles','triangle_polygons'}
        and packet['schema']==g.PROTOCOL and packet['request_id']==request_id,'source_packet')
    source=packet['source'];budget=m.WorkBudget(deadline_ns=deadline_ns)
    prepared=m.prepare_raw(packet['raw'],{k:source[k] for k in ('object_id','object_instance','document_epoch','capture_id')},budget=budget)
    v.require(prepared['source']==source and source['object_id']==object_id,'consumer_source_digest')
    g.validate_tessellation(prepared['raw'],packet['triangles'],packet['triangle_polygons'],budget)
    evidence=value['evidence'];v.require(type(evidence) is dict and type(evidence.get('native_scene')) is dict,'evidence')
    objects=evidence['native_scene'].get('objects');v.require(type(objects) is list and 1<=len(objects)<=64,'native_object_budget')
    vertex_count=triangles=0
    for obj in objects:
        v.require(type(obj) is dict and set(obj)==set(n._OBJECT_KEYS) and type(obj['world_vertices']) is list
            and type(obj['local_vertices']) is list and type(obj['faces']) is list,'native_geometry_fields')
        vertex_count+=len(obj['world_vertices']);triangles+=len(obj['faces'])
        v.require(vertex_count<=4096 and triangles<=1024 and all(type(t) is list and len(t)==3 for t in obj['faces']),'native_geometry_budget')
    native=n._readonly_evidence(evidence,evidence['capture'],minimum_objects=1)
    from .patch_focus import validate_profile
    validate_profile(value['display'],{o['object_id'] for o in objects})
    identity=evidence['capture'].get('host_identity');display=value['display']['objects']
    v.require(type(identity) is dict and identity.get('capture_scope')=='complete_scene_meshes'
        and identity.get('document_epoch')==source['document_epoch']
        and identity.get('object_instances')=={d['object_id']:str(d['object_uid']) for d in display},'display_source_binding')
    target=next(d for d in display if d['object_id']==object_id)
    v.require(source['object_instance']==str(target['object_uid'])+':'+str(target['mesh_uid']),'mesh_incarnation')
    exact=ExactVisibility(native,deadline_ns)
    replay,candidates,samples=v.plan(packet,patch,native,deadline_ns,visibility=exact)
    v.require(value['plan']==replay,'independent_visibility_decision')
    kinds=['overview','detail'] if replay['selected_ordinal'] is not None else []
    frames=value['frames'];v.require(type(frames) is list and len(frames)==len(kinds),'frame_count')
    images=[];sequence=0;total=0;actual=[];actual_signals=[];overview_proof=None
    for row,kind in zip(frames,kinds):
        v.check(deadline_ns)
        v.require(type(row) is dict and set(row)=={'kind','picture','png_sha256','frustum','audit','frame'} and row['kind']==kind,'frame_record')
        selected=candidates[replay['selected_ordinal']];frame=selected[kind];scale=packet['raw']['unit_scale']
        expected=dict(center_world_m=[x*scale for x in frame['center_bu']],right_world=frame['right'],up_world=frame['up'],
            eye_direction_world=frame['direction'],span_m=frame['ortho_scale_bu']*scale,
            screen_coverage='all_native_vertices' if kind=='overview' else 'intentional_local_window',depth_coverage='all_native_vertices')
        v.require(row['frame']==expected,'frame_geometry')
        n._validated_render_audit(row['audit'],'SCENE',[o['name'] for o in native['objects']],sequence,minimum_objects=1);sequence=row['audit']['sequence']
        n._validate_multiscale_frustum(row['frustum'],expected,native,'SCENE',kind)
        if kind=='overview':overview_proof=row['frustum']
        if kind=='detail':
            matrix=row['frustum']['camera_matrix_host_units'];eye=[matrix[k][2] for k in range(3)]
            camera_candidate=dict(selected,eye=eye)
            actual=[exact(native,dict(sample,object_id=object_id),camera_candidate,deadline_ns) for sample in samples]
            detail_span=row['frustum']['ortho_scale_bu']*scale;overview_span=overview_proof['ortho_scale_bu']*scale
            for sample in samples:
                def pixels(proof):
                    matrix=proof['camera_matrix_host_units'];axes=[[matrix[k][j] for k in range(3)] for j in (0,1)]
                    return math.hypot(*(v.dot(sample['delta'],a) for a in axes))*384/(proof['ortho_scale_bu']*scale)
                detail_px,overview_px=pixels(row['frustum']),pixels(overview_proof)
                matrix=row['frustum']['camera_matrix_host_units'];delta=[sample['point'][k]/scale-matrix[k][3] for k in range(3)]
                inside=all(abs(v.dot(delta,[matrix[k][j] for k in range(3)]))<=row['frustum']['ortho_scale_bu']*(.5-1/384) for j in (0,1))
                actual_signals.append(dict(detail_px=detail_px,overview_px=overview_px,inside_window=inside,
                    qualified=inside and detail_px>=2 and overview_px<2 and overview_span/detail_span>=2))
            v.require(sum(a and signal['qualified'] for a,signal in zip(actual,actual_signals))>=2,'actual_camera_feature_occluded_or_subpixel')
        picture=row['picture']
        v.require(type(picture) is dict and set(picture)=={'mime_type','image_base64','width','height','view','source'}
            and picture['mime_type']=='image/png' and picture['view']=='SCENE' and picture['width']==picture['height']==384
            and picture['source']=='blender_workbench_native_render' and type(picture['image_base64']) is str
            and len(picture['image_base64'])<=12*1024*1024,'picture_fields')
        blob=base64.b64decode(picture['image_base64'],validate=True);total+=len(blob)
        v.require(total<=16*1024*1024 and len(blob)>=24 and struct.unpack('>II',blob[16:24])==(384,384)
            and hashlib.sha256(blob).hexdigest()==row['png_sha256'],'png_hash_or_budget')
        clean=n._public_native_png(blob);images.append(dict(type='image',mimeType='image/png',data=base64.b64encode(clean).decode('ascii')))
    v.require(exact.tests==replay['consumer_planned_triangle_tests']+replay['consumer_actual_triangle_tests']
        and exact.tests+replay['producer_triangle_tests']<=16384,'combined_actual_work')
    v.check(deadline_ns)
    return dict(status='observed' if images else 'no_useful_image',protocol=v.PROTOCOL,images=images,
        plan=replay,actual_witness_visibility=actual,actual_witness_projection_px=actual_signals,source=source,
        reference_raw_sha256=patch['reference_raw_sha256'],feature_sha256=v.digest(patch),execution_authority=False,
        scope='current_source_reference_change_witnesses_not_damage_or_complete_visibility')
