"""Pinned, dependency-free finite boundary planner; explicit capability only."""
import base64,hashlib,json,math,time
from fractions import Fraction as Q

def require(test,reason):
    if not test:raise ValueError('nonplanar_local_'+reason)

def sub(a,b):return [x-y for x,y in zip(a,b)]

def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))

def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def source_binding(native,object_id,edges):
    data=json.dumps({'native':native,'object_id':object_id,'edges':edges},sort_keys=True,
        separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf8')
    require(len(data)<=1024*1024,'source_bytes_budget')
    return hashlib.sha256(data).hexdigest()

def point_segment_sq(point,a,b):
    edge=sub(b,a);offset=sub(point,a);den=dot(edge,edge)
    t=max(0.,min(1.,dot(offset,edge)/den)) if den else 0.
    residual=[offset[k]-t*edge[k] for k in range(3)]
    return dot(residual,residual)

def segment_sq(a,b,c,d):
    best=min(point_segment_sq(p,x,y) for p,x,y in ((a,c,d),(b,c,d),(c,a,b),(d,a,b)))
    u,v,w=sub(b,a),sub(d,c),sub(a,c)
    aa,bb,cc,dd,ee=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    determinant=dot(cross(u,v),cross(u,v))
    if determinant>0:
        s=(bb*ee-cc*dd)/determinant;t=(aa*ee-bb*dd)/determinant
        if 0<=s<=1 and 0<=t<=1:
            residual=[w[k]+s*u[k]-t*v[k] for k in range(3)]
            best=min(best,dot(residual,residual))
    return best

class LocalSurfaceIndex:
    def __init__(self,target,deadline,max_work=32768,policy='strict_coplanar'):
        require(type(max_work) is int and 0<=max_work<=32768,'work_limit')
        require(policy in ('strict_coplanar','visual_nearplanar'),'policy')
        self.policy=policy
        self.maximum=max_work;self.work=0;self.deadline=deadline
        self.vertices=target['world_vertices'];self.faces=target['faces']
        self.links={};self.normals={}
        self.reserve(9*len(self.faces))  # Producer, exact replay, full decision reconstruction.
        for i,face in enumerate(self.faces):
            require(len(face)==3 and len(set(face))==3 and all(type(v) is int and 0<=v<len(self.vertices) for v in face),'face_indices')
            for a,b in zip(face,face[1:]+face[:1]):
                self.links.setdefault(tuple(sorted((a,b))),[]).append((i,a,b))

    def reserve(self,units):
        require(time.perf_counter_ns()<self.deadline,'deadline')
        require(self.work+units<=self.maximum,'work_budget')
        self.work+=units

    def normal(self,index):
        if index not in self.normals:
            self.reserve(2)
            a,b,c=[self.vertices[v] for v in self.faces[index]]
            value=cross(sub(b,a),sub(c,a));length=math.hypot(*value)
            require(math.isfinite(length) and length>1e-15,'degenerate_face')
            self.normals[index]=[v/length for v in value]
        return self.normals[index]

    def proof(self,edge,radius):
        a,b=edge;start,end=self.vertices[a],self.vertices[b]
        incident=self.links.get(tuple(sorted(edge)),[])
        require(len(incident)==1,'single_seed_face')
        seed=incident[0][0];normal=self.normal(seed)
        length=math.hypot(*sub(end,start));require(length>0,'degenerate_edge')
        plane_tolerance=length*1e-10 if self.policy=='strict_coplanar' else radius/96
        max_normal_sine=1e-8 if self.policy=='strict_coplanar' else 1/1024
        queue=[seed];seen={seed};accepted=[]
        while queue:
            self.reserve(2);index=queue.pop(0)
            require(len(seen)<=128,'face_visit_budget')
            face_normal=self.normal(index)
            if dot(normal,face_normal)<=0 or math.hypot(*cross(normal,face_normal))>max_normal_sine:continue
            if any(abs(dot(normal,sub(self.vertices[v],start)))>plane_tolerance for v in self.faces[index]):continue
            accepted.append(index)
            face=self.faces[index]
            for x,y in zip(face,face[1:]+face[:1]):
                self.reserve(2);links=self.links[tuple(sorted((x,y)))]
                if len(links)!=2:continue
                first,second=links
                if first[1:]!=second[:0:-1]:continue  # Opposite orientation only.
                neighbour=second[0] if first[0]==index else first[0]
                if neighbour in seen:continue
                if segment_sq(start,end,self.vertices[x],self.vertices[y])>radius*radius:continue
                seen.add(neighbour);queue.append(neighbour)
        return {'edge':list(edge),'seed_face':seed,'face_ids':sorted(accepted),
            'radius':radius,'visited_face_count':len(seen),'scope':'oriented_bounded_plane_capsule_connected',
            'policy':self.policy,'max_plane_deviation':plane_tolerance,'max_normal_sine':max_normal_sine}

def local_hit(index,proof,point,direction,hits,object_id):
    if not hits:return False
    allowed=set(proof['face_ids']);a,b=[index.vertices[i] for i in proof['edge']]
    for owner,face,depth in hits:
        if owner!=object_id or face not in allowed:return False
        actual=[point[k]+depth*direction[k] for k in range(3)]
        if point_segment_sq(actual,a,b)>proof['radius']**2:return False
    return True

def canonical_boundary(index,edges):
    """Sampling features only: exact collinearity and oriented coplanarity."""
    index.reserve(8*len(edges))
    neighbours={}
    for a,b in edges:
        neighbours.setdefault(a,[]).append(b);neighbours.setdefault(b,[]).append(a)
    points={v:tuple(Q(x) for x in index.vertices[v]) for v in neighbours}
    require(len(set(points.values()))==len(points),'duplicate_boundary_positions')
    normals={}
    def exact_normal(a,b):
        face=index.links[tuple(sorted((a,b)))][0][0]
        if face not in normals:
            x,y,z=[tuple(Q(t) for t in index.vertices[v]) for v in index.faces[face]]
            normals[face]=cross(sub(y,x),sub(z,x))
        return normals[face]
    qdot=lambda a,b:sum(x*y for x,y in zip(a,b))
    corners=set()
    for v,(a,b) in neighbours.items():
        u,w=sub(points[a],points[v]),sub(points[b],points[v])
        na,nb=exact_normal(v,a),exact_normal(v,b)
        straight=not any(cross(u,w)) and qdot(u,w)<0
        coplanar=not any(cross(na,nb)) and qdot(na,nb)>0
        if not (straight and coplanar):corners.add(v)
    require(len(corners)>=3,'insufficient_sampling_features')
    start=min(corners,key=lambda v:points[v])
    def walk(first):
        path=[start];previous,current=start,first
        while current!=start:
            require(len(path)<=len(edges),'invalid_boundary_walk')
            path.append(current)
            candidates=neighbours[current]
            previous,current=current,next(v for v in candidates if v!=previous)
        require(len(path)==len(edges),'incomplete_boundary_walk')
        path.append(start);features=[];begin=0
        for i in range(1,len(path)):
            if path[i] in corners:
                features.append({'edge':[path[begin],path[i]],
                    'source_edges':[[path[j],path[j+1]] for j in range(begin,i)]})
                begin=i
        return features
    options=[walk(v) for v in neighbours[start]]
    return min(options,key=lambda fs:points[fs[0]['edge'][1]])

def sample_owner(index,feature,t):
    a,b=feature['edge'];vertices=index.vertices
    axis=next(k for k in range(3) if vertices[a][k]!=vertices[b][k])
    origin=Q(vertices[a][axis]);scale=Q(vertices[b][axis])-origin
    for x,y in feature['source_edges']:
        lo,hi=sorted(((Q(vertices[x][axis])-origin)/scale,(Q(vertices[y][axis])-origin)/scale))
        if lo<=Q(t)<=hi:return [x,y]
    raise ValueError('nonplanar_local_sample_without_source_edge')

def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))

def sub(a,b):return [x-y for x,y in zip(a,b)]

def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def need(test,reason):
    if not test:raise ValueError('nonplanar_'+reason)

def unit(v):
    length=math.hypot(*v);need(math.isfinite(length) and length>1e-15,'degenerate_direction')
    return [x/length for x in v]

def axes(direction):
    d=unit(direction);r=[-d[1],d[0],0.] if math.hypot(d[0],d[1])>1e-10 else [-1.,0.,0.]
    r=unit(r);return r,cross(d,r),d

def check(deadline):need(time.perf_counter_ns()<deadline,'deadline')

def dot_interval(a,b):
    """Outward enclosure for the dot product of the supplied binary64 values."""
    low=high=0.
    for x,y in zip(a,b):
        value=x*y
        if not math.isfinite(value):return [-math.inf,math.inf]
        low=math.nextafter(low+math.nextafter(value,-math.inf),-math.inf)
        high=math.nextafter(high+math.nextafter(value,math.inf),math.inf)
        if not math.isfinite(low) or not math.isfinite(high):return [-math.inf,math.inf]
    return [low,high]

def possible_objects(bounds,point,right,up):
    intervals=[dot_interval(point,a) for a in (right,up)]
    return [name for name,box in bounds.items() if all(
        not (intervals[k][1]<box[k][0] or intervals[k][0]>box[k][1]) for k in (0,1))]

def frame(native,center,right,up,direction,span):
    points=[p for o in native['objects'] for p in o['world_vertices']]
    depths=[dot(sub(p,center),direction) for p in points]
    margin=max(span,max(depths)-min(depths))*.125;distance=max(depths)+margin
    return dict(center_bu=center,direction=direction,right=right,up=up,
        camera_location_bu=[center[k]+direction[k]*distance for k in range(3)],
        ortho_scale_bu=span,clip_start_bu=margin*.25,clip_end_bu=distance-min(depths)+margin)

LEAF_SIZE=8

AUTO_FACE_THRESHOLD=26

MAX_BUILD_UNITS=65536

MAX_NODE_SLOTS=4096

MAX_PACKET_BYTES=512*1024

class IndexBudgetError(ValueError):pass

def limits_for_faces(count):
    depth=0
    while count>LEAF_SIZE*(1<<depth):depth+=1
    nodes=(1<<(depth+1))-1
    return count*(depth+3)+nodes,nodes

class IndexBudget:
    def __init__(self,deadline,*,max_build=MAX_BUILD_UNITS,max_nodes=MAX_NODE_SLOTS,max_bytes=MAX_PACKET_BYTES):
        if any(type(v) is not int or v<0 for v in (max_build,max_nodes,max_bytes)):
            raise ValueError('invalid_triangle_index_budget')
        if max_build>MAX_BUILD_UNITS or max_nodes>MAX_NODE_SLOTS or max_bytes>MAX_PACKET_BYTES:
            raise ValueError('triangle_index_budget_cannot_expand')
        self.deadline=deadline;self.max_build=max_build;self.max_nodes=max_nodes;self.max_bytes=max_bytes
        self.build_reserved=0;self.nodes_reserved=0;self.node_tests_reserved=0;self.packet_bytes=0
        self.reservations=[]
        self.box_limit=32768

    def check(self):
        if time.perf_counter_ns()>=self.deadline:raise IndexBudgetError('triangle_index_deadline')

    def reserve_build(self,count,object_id,right,up):
        self.check();units,nodes=limits_for_faces(count)
        if self.build_reserved+units>self.max_build or self.nodes_reserved+nodes>self.max_nodes:
            raise IndexBudgetError('triangle_index_build_budget')
        self.build_reserved+=units;self.nodes_reserved+=nodes
        self.reservations.append({'object_id':object_id,'face_count':count,'right':right,'up':up,
            'build_units_reserved':units,'node_slots_reserved':nodes})
        return units,nodes

    def test_node(self):
        self.check()
        if self.node_tests_reserved+2>self.box_limit:
            raise IndexBudgetError('triangle_index_traversal_budget')
        self.node_tests_reserved+=2

    def publish_bytes(self,value):
        size=len(json.dumps(value,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf8'))
        if self.packet_bytes+size>self.max_bytes:raise IndexBudgetError('triangle_index_packet_budget')
        self.packet_bytes+=size

def triangle_box(face,intervals):
    result=[]
    for axis in (0,1):
        low=min(intervals[axis][v][0] for v in face);high=max(intervals[axis][v][1] for v in face)
        if not math.isfinite(low) or not math.isfinite(high):raise IndexBudgetError('triangle_index_nonfinite_bounds')
        # Retain the tolerated barycentric halo as well as arithmetic edge cases.
        pad=4e-12*(high-low)+32*math.ulp(max(1.,abs(low),abs(high)))
        result.append((math.nextafter(low-pad,-math.inf),math.nextafter(high+pad,math.inf)))
    box=[result[0][0],result[1][0],result[0][1],result[1][1]]
    if not all(math.isfinite(v) for v in box):raise IndexBudgetError('triangle_index_nonfinite_bounds')
    return box

def build_index(obj,intervals,right,up,binding,budget):
    units,node_bound=budget.reserve_build(len(obj['faces']),obj['object_id'],right,up)
    boxes=[triangle_box(face,intervals) for face in obj['faces']]
    nodes=[]
    def build(ids):
        budget.check();index=len(nodes);nodes.append(None)
        bound=[min(boxes[i][0] for i in ids),min(boxes[i][1] for i in ids),
            max(boxes[i][2] for i in ids),max(boxes[i][3] for i in ids)]
        if len(ids)<=LEAF_SIZE:
            nodes[index]=bound+[-1,-1,sorted(ids)]
        else:
            axis=0 if bound[2]-bound[0]>=bound[3]-bound[1] else 1
            ids.sort(key=lambda i:(boxes[i][axis]/2+boxes[i][axis+2]/2,i))
            cut=len(ids)//2;left=build(ids[:cut]);right_id=build(ids[cut:])
            nodes[index]=bound+[left,right_id,[]]
        return index
    build(list(range(len(boxes))))
    need(len(nodes)<=node_bound, 'index_node_bound')
    result={'schema':'projected-triangle-bvh-v1','object_id':obj['object_id'],
        'face_count':len(obj['faces']),'vertex_count':len(obj['world_vertices']),
        'source_binding':binding,'right':right,'up':up,'leaf_size':LEAF_SIZE,
        'reservation_index':len(budget.reservations)-1,
        'build_units_reserved':units,'node_slots_reserved':node_bound,'nodes':nodes}
    budget.publish_bytes(result)
    return result


PROTOCOL = 'readonly-nonplanar-boundary-v1'
MODES = ('nonplanar_boundary_v1', 'nonplanar_dense_v1')
LIMITS = dict(png_bytes=16 * 1024 * 1024)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf8')).hexdigest()


def display_profile(host, renderer=None):
    return host._patch_focus_module().display_profile(host, renderer)


def source_geometry(prepared, patch, native):
    raw = prepared['raw']
    need(patch['category'] == 'boundary_edges' and patch['element_kind'] == 'edge'
        and patch['position']['status'] == 'known' and 3 <= len(patch['source_indices']) <= 64,
        'complete_boundary_patch_required')
    target = next(o for o in native['objects'] if o['object_id'] == prepared['source']['object_id'])
    local_metres = [[x * raw['unit_scale'] for x in p] for p in raw['vertices']]
    need(raw['polygons'] == target['faces'] and all(len(p) == 3 for p in raw['polygons'])
        and local_metres == target['local_vertices'], 'raw_native_triangle_correspondence')
    matrix = raw['matrix_world']
    matrix_metres = [row[:] for row in matrix]
    for k in range(3):
        matrix_metres[k][3] *= raw['unit_scale']
    need(matrix_metres == target['matrix'], 'raw_native_matrix_correspondence')
    world = [[(sum(matrix[k][j] * p[j] for j in range(3)) + matrix[k][3]) * raw['unit_scale']
        for k in range(3)] for p in raw['vertices']]
    need(world == target['world_vertices'], 'raw_native_world_correspondence')
    return [raw['edges'][i] for i in patch['source_indices']]


def production_plan(prepared, patch, native, renderer, deadline, mode):
    need(mode in MODES, 'mode')
    edges = source_geometry(prepared, patch, native)
    planned = choose(native, prepared['source']['object_id'], edges, deadline,
        locality_policy='visual_nearplanar', acceleration='auto' if mode == MODES[1] else 'off')
    need(planned['search_complete'] is True, 'incomplete_search_requires_review')
    chosen = planned['selected']
    row = chosen or planned['candidates'][0]
    points = [p for o in native['objects'] for p in o['world_vertices']]
    center = [min(p[k] for p in points) / 2 + max(p[k] for p in points) / 2 for k in range(3)]
    overview = chosen['overview_frame'] if chosen else frame(native, center, row['right'], row['up'],
        row['direction'], row['overview_span'])
    detail = chosen['detail_frame'] if chosen else None
    scale = prepared['raw']['unit_scale']
    def host_units(value):
        if value is None:
            return None
        return {key: ([x / scale for x in v] if key in ('center_bu', 'camera_location_bu')
            else v / scale if key in ('ortho_scale_bu', 'clip_start_bu', 'clip_end_bu') else v)
            for key, v in value.items()}
    return planned, host_units(overview), host_units(detail)

def traverse(index,point_intervals,budget,trace,selected):
    pending=[0]
    while pending:
        budget.test_node();number=pending.pop();node=index['nodes'][number]
        active=not any(point_intervals[k][1]<node[k] or point_intervals[k][0]>node[k+2] for k in (0,1))
        trace.append([number,active])
        if not active:continue
        if node[4]==-1:selected.extend(node[6])
        else:pending.extend((node[5],node[4]))
    selected.sort()

def filter_view(native,staged,vertex_intervals,right,up,binding,counts,budget,point_interval,threshold):
    """Publish partial traversal only as incomplete evidence; no rays yet."""
    used={name for sample in staged for names in sample['possible_objects'] for name in names}
    wanted={name for name in used if counts[name]>=threshold}
    if not wanted:return None
    result={'schema':'triangle-index-view-v1','indices':{},'queries':[],'complete':False,'reason':None}
    try:
        for obj in native['objects']:
            if obj['object_id'] in wanted:
                result['indices'][obj['object_id']]=build_index(obj,vertex_intervals[obj['object_id']],right,up,binding,budget)
        for sample in staged:
            refs=[]
            for point,names in zip(sample['pair'],sample['possible_objects']):
                query={'point':point,'possible_objects':names,'filters':{},'traces':{},'complete':False}
                refs.append(len(result['queries']));result['queries'].append(query)
                intervals=[point_interval(point,axis) for axis in (right,up)]
                for name in names:
                    if name not in result['indices']:continue
                    trace=[];selected=[];query['traces'][name]=trace;query['filters'][name]=selected
                    traverse(result['indices'][name],intervals,budget,trace,selected)
                query['complete']=True
            sample['index_queries']=refs
        result['complete']=True
    except IndexBudgetError as exc:
        result['reason']=str(exc)
        for query in result['queries']:
            for selected in query['filters'].values():selected.sort()
    # Query traces also occupy the bounded outgoing certificate envelope.
    budget.publish_bytes(result['queries'])
    return result

def object_bounds(objects,right,up,vertex_sink=None):
    if vertex_sink is None:
        # Preserve the pre-index small-scene computation and allocation path.
        bounds={}
        for obj in objects:
            axes_bounds=[]
            for axis in (right,up):
                intervals=[dot_interval(p,axis) for p in obj['world_vertices']]
                axes_bounds.append([min(v[0] for v in intervals),max(v[1] for v in intervals)])
            bounds[obj['object_id']]=axes_bounds
        return bounds
    bounds={}
    for obj in objects:
        axes_bounds=[]
        vertex_intervals=[] if vertex_sink is not None else None
        for axis in (right,up):
            intervals=[dot_interval(p,axis) for p in obj['world_vertices']]
            axes_bounds.append([min(v[0] for v in intervals),max(v[1] for v in intervals)])
            if vertex_intervals is not None:vertex_intervals.append(intervals)
        bounds[obj['object_id']]=axes_bounds
        if vertex_sink is not None:vertex_sink[obj['object_id']]=vertex_intervals
    return bounds

def projected_hit(native,point,right,up,direction,allowed_objects=None,*,with_depth=False,allowed_faces=None):
    """Projected barycentric depths, independent of verifier's 3D lines."""
    hits=[]
    for obj in native['objects']:
        if allowed_objects is not None and obj['object_id'] not in allowed_objects:continue
        triangles=(enumerate(obj['faces']) if allowed_faces is None or obj['object_id'] not in allowed_faces
             else ((index,obj['faces'][index]) for index in allowed_faces[obj['object_id']]))
        for index,face in triangles:
            a,b,c=[sub(obj['world_vertices'][i],point) for i in face]
            p,q,s=[[dot(v,axis) for axis in (right,up,direction)] for v in (a,b,c)]
            if not (min(p[0],q[0],s[0])<=0<=max(p[0],q[0],s[0])
                and min(p[1],q[1],s[1])<=0<=max(p[1],q[1],s[1])):continue
            x,y=q[0]-p[0],q[1]-p[1];u,v=s[0]-p[0],s[1]-p[1];den=x*v-y*u
            need(abs(den)>1e-12*max(math.hypot(x,y)*math.hypot(u,v),1e-300),'edge_on_ray_uncertain')
            b0=(-p[0]*v+p[1]*u)/den;b1=(-x*p[1]+y*p[0])/den
            if min(b0,b1,1-b0-b1)<-1e-12:continue
            depth=math.fsum((p[2]*(1-b0-b1),q[2]*b0,s[2]*b1))
            need(math.isfinite(depth),'nonfinite_depth');hits.append((depth,obj['object_id'],index))
    if not hits:return []
    depth=max(h[0] for h in hits);eps=1e-9*max(1.,abs(depth))
    return [(obj,index,z) if with_depth else (obj,index) for z,obj,index in hits if depth-z<=eps]

def choose(native,object_id,edges,deadline,*,max_tests=8192,max_locality_work=32768,locality_policy='strict_coplanar',
        acceleration='auto',index_limits=None):
    check(deadline);objects=native['objects']
    need(1<=len(objects)<=64 and sum(len(o['world_vertices']) for o in objects)<=4096
        and sum(len(o['faces']) for o in objects)<=2048,'geometry_budget')
    need(type(max_tests) is int and 0<=max_tests<=8192,'test_budget')
    need(len({o['object_id'] for o in objects})==len(objects),'unique_native_objects')
    binding=source_binding(native,object_id,edges)
    target=next(o for o in objects if o['object_id']==object_id);vertices=target['world_vertices']
    local_index=LocalSurfaceIndex(target,deadline,max_locality_work,locality_policy)
    need(3<=len(edges)<=64 and len({tuple(sorted(e)) for e in edges})==len(edges),'boundary_budget')
    degree={};adjacent={};normals=[]
    for a,b in edges:
        need(a!=b and 0<=a<len(vertices) and 0<=b<len(vertices),'edge_indices')
        degree[a]=degree.get(a,0)+1;degree[b]=degree.get(b,0)+1
        faces=[entry[0] for entry in local_index.links.get(tuple(sorted((a,b))),[])]
        need(len(faces)==1,'single_native_adjacent_triangle_required');adjacent[tuple((a,b))]=faces[0]
        p,q,r=[vertices[j] for j in target['faces'][faces[0]]]
        face_normal=unit(cross(sub(q,p),sub(r,p)));edge_length=math.hypot(*sub(vertices[a],vertices[b]))
        normals.append([edge_length*x for x in face_normal])
    need(all(v==2 for v in degree.values()),'closed_component_required')
    reached={edges[0][0]}
    for _ in edges:
        for a,b in edges:
            if a in reached or b in reached:reached.update((a,b))
    need(reached==set(degree),'single_component_required')
    normal=[math.fsum(n[k] for n in normals) for k in range(3)]
    need(math.hypot(*normal)>.1*sum(math.hypot(*n) for n in normals),'normal_cancellation_requires_charts')
    n=unit(normal);directions=[]
    for d in (n,[-x for x in n],[0.,0.,1.],[0.,1.,0.]):
        if not any(dot(d,old)>1-1e-10 for old in directions):directions.append(d)
    points=[vertices[i] for i in sorted(degree)];all_points=[p for o in objects for p in o['world_vertices']]
    need(all(type(x) in (int,float) and math.isfinite(x) for p in all_points for x in p),'finite_geometry')
    features=canonical_boundary(local_index,edges)
    center=[min(p[k] for p in points)/2+max(p[k] for p in points)/2 for k in range(3)]
    all_center=[min(p[k] for p in all_points)/2+max(p[k] for p in all_points)/2 for k in range(3)]
    counts={o['object_id']:len(o['faces']) for o in objects}
    need(acceleration in ('auto','off','force'),'acceleration_mode')
    threshold=1 if acceleration=='force' else AUTO_FACE_THRESHOLD
    indexed=acceleration!='off' and any(count>=threshold for count in counts.values())
    index_budget=IndexBudget(deadline,**(index_limits or {})) if indexed else None
    combined=box_work=projection_work=0;rows=[];search_complete=True
    for d in directions:
        check(deadline);right,up,d=axes(d)
        projected={i:[dot(sub(vertices[i],center),axis) for axis in (right,up)] for i in degree}
        widths=[max(p[k] for p in projected.values())-min(p[k] for p in projected.values()) for k in (0,1)]
        span=1.6*max(widths);min_width=min(widths)
        overview_span=2.5*max(abs(dot(sub(p,all_center),axis)) for p in all_points for axis in (right,up))
        need(span>0 and overview_span>0 and math.isfinite(span+overview_span),'degenerate_projection')
        need(min_width>64*max(math.ulp(float(x)) for p in points for x in p) or min_width==0,'unrepresentable_feature')
        row=dict(direction=d,right=right,up=up,center=center,span=span,overview_span=overview_span,
            projection=dict(overview_px=384*min_width/overview_span,detail_px=384*min_width/span),
            samples=[],visible_count=0,reason='no_projection_gain',tests_reserved=0,local_surfaces=[])
        rows.append(row)
        if not (row['projection']['overview_px']<16<=row['projection']['detail_px'] and overview_span/span>=2):continue
        # Reject overlapping non-neighbour edges in this projection.
        ambiguous=False
        def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        for i,(a,b) in enumerate(edges):
            for c,e in edges[i+1:]:
                if {a,b}&{c,e}:continue
                p,q,r,s=[projected[j] for j in (a,b,c,e)]
                if any(max(p[k],q[k])<min(r[k],s[k]) or max(r[k],s[k])<min(p[k],q[k]) for k in (0,1)):continue
                eps=span*span*1e-12;o=[orient(p,q,r),orient(p,q,s),orient(r,s,p),orient(r,s,q)]
                if min(o[:2])<=eps and max(o[:2])>=-eps and min(o[2:])<=eps and max(o[2:])>=-eps:ambiguous=True
        if ambiguous:row['reason']='ambiguous_projected_boundary';continue
        row['reason']='boundary_not_visible_enough';staged=[]
        for feature in features:
            a,b=feature['edge']
            dx,dy=sub(projected[b],projected[a]);length=math.hypot(dx,dy)
            if length<=6*span/384:row['reason']='edge_subpixel';break
            offset=[span/128*(-dy*right[k]+dx*up[k])/length for k in range(3)]
            for t in (.25,.5,.75):
                check(deadline);mid=[vertices[a][k]*(1-t)+vertices[b][k]*t for k in range(3)]
                pair=[[mid[k]+sign*offset[k] for k in range(3)] for sign in (-1,1)]
                staged.append(dict(edge=[a,b],source_edge=sample_owner(local_index,feature,t),pair=pair))
        if len(staged)!=len(features)*3:continue
        # Reserve both ends' broad-phase work before constructing intervals.
        boxes=len(staged)*2*len(objects)*3;projections=(len(all_points)+len(staged)*2)*2*3
        if box_work+boxes+(index_budget.node_tests_reserved if indexed else 0)>32768 or projection_work+projections>65536:
            row['reason']='broad_phase_budget_exhausted';search_complete=False;break
        box_work+=boxes;projection_work+=projections
        vertex_intervals={} if indexed else None
        bounds=object_bounds(objects,right,up,vertex_intervals)
        for sample in staged:
            sample['possible_objects']=[possible_objects(bounds,p,right,up) for p in sample['pair']]
        view_index=None
        if indexed:
            index_budget.box_limit=32768-box_work
            view_index=filter_view(native,staged,vertex_intervals,right,up,binding,counts,index_budget,dot_interval,threshold)
            if view_index is not None:
                row['acceleration']=view_index
                if not view_index['complete']:
                    row['reason']=view_index['reason'];search_complete=False;break
        if view_index is None:
            required=2*sum(counts[name] for s in staged for ids in s['possible_objects'] for name in ids)
        else:
            required=2*sum(len(view_index['queries'][s['index_queries'][side]]['filters'][name])
                if name in view_index['queries'][s['index_queries'][side]]['filters'] else counts[name]
                for s in staged for side,ids in enumerate(s['possible_objects']) for name in ids)
        if combined+required>max_tests:
            row['reason']='combined_budget_exhausted';search_complete=False;break
        combined+=required;row['tests_reserved']=required
        row['local_surfaces']=[local_index.proof(edge,4*span/128) for edge in edges]
        # The full ray reservation also bounds every possible front-hit
        # membership/distance check at producer and independent verifier.
        local_index.reserve(required)
        local_by_edge={tuple(sorted(proof['edge'])):proof for proof in row['local_surfaces']}
        for sample in staged:
            check(deadline);a,b=sample['edge'];pair=sample['pair']
            if view_index is None:
                hits=[projected_hit(native,p,right,up,d,ids,with_depth=True) for p,ids in zip(pair,sample['possible_objects'])]
            else:
                hits=[projected_hit(native,p,right,up,d,ids,with_depth=True,
                    allowed_faces=view_index['queries'][sample['index_queries'][side]]['filters'])
                    for side,(p,ids) in enumerate(zip(pair,sample['possible_objects']))]
            proof=local_by_edge[tuple(sorted(sample['source_edge']))]
            kinds=['open' if not h else 'local_surface' if local_hit(local_index,proof,p,d,h,object_id)
                else 'blocked' for p,h in zip(pair,hits)]
            visible=sorted(kinds)==['local_surface','open']
            row['samples'].append(dict(**sample,visible=visible))
            row['visible_count']+=visible
        if len(row['samples'])==len(features)*3 and row['visible_count']>=max(8,math.ceil(len(row['samples'])*2/3)):
            row['reason']='visible_boundary_gain'
    valid=[r for r in rows if r['reason']=='visible_boundary_gain']
    best=max(valid,key=lambda r:(r['visible_count'],r['projection']['detail_px']),default=None)
    if best:
        best['overview_frame']=frame(native,all_center,best['right'],best['up'],best['direction'],best['overview_span'])
        best['detail_frame']=frame(native,center,best['right'],best['up'],best['direction'],best['span'])
    result=dict(schema='bounded-nonplanar-plan-v1',selected=best,candidates=rows,
        native_binding_sha256=binding,binding_scope='outer_raw_native_display_epoch_protocol',
        sampling_features=features,sampling_policy='three_per_exact_collinear_coplanar_feature',
        locality_work_reserved=local_index.work,max_locality_work=max_locality_work,
        locality_policy=locality_policy,
        search_complete=search_complete,combined_triangle_tests_reserved=combined,max_triangle_tests=max_tests,
        combined_box_tests_reserved=box_work+(index_budget.node_tests_reserved if indexed else 0),combined_projection_ops_reserved=projection_work,
        maximum_candidates=4,maximum_images=2,execution_authority=False)
    if indexed and index_budget.reservations:
        result.update(acceleration_mode=acceleration,index_build_reservations=index_budget.reservations,
            index_build_units_reserved=index_budget.build_reserved,index_node_slots_reserved=index_budget.nodes_reserved,
            index_node_tests_reserved=index_budget.node_tests_reserved,index_packet_bytes=index_budget.packet_bytes)
    return result


def observe(host, object_id, patch, request_id, deadline_ns, mode):
    """One synchronous lease; restoration uncertainty quarantines read rendering."""
    host._readonly_request_id(request_id);check(deadline_ns)
    require(deadline_ns<=time.perf_counter_ns()+30_000_000_000,'original_deadline_required')
    require(type(patch) is dict and len(json.dumps(patch,allow_nan=False))<=16384,'patch_input_budget')
    renderer=host._readonly_native_module();m=host._raw_mesh_module()
    store=host._readonly_observation_store(create=True);now=time.perf_counter_ns()
    require(not store['quarantined'] and store['active_request_id'] is None,'read_channel_unavailable')
    store['seen']={k:v for k,v in store['seen'].items() if v>now}
    require(request_id not in store['seen'] and len(store['seen'])<128,'request_reused_or_capacity')
    store['seen'][request_id]=deadline_ns;store['active_request_id']=request_id
    store['sequence']+=1;audits=[];evidence=None;profile=None;started=now
    try:
        profile=display_profile(host,renderer)
        budget=m.WorkBudget(deadline_ns=deadline_ns)
        prepared=m.capture_raw(host,object_id,budget=budget)
        diagnosis=m.analyze_prepared(prepared,task_id=request_id,categories=['boundary_edges'],budget=budget)
        require(digest(patch) in {digest(p) for p in diagnosis['patches']},'stale_or_incomplete_patch')
        evidence=host.capture_readonly_evidence();check(deadline_ns)
        planned,overview,detail=production_plan(prepared,patch,evidence['native_scene'],renderer,deadline_ns,mode)
        planning_finished=time.perf_counter_ns();frames=[];total_bytes=0
        for kind,frame in [('overview',overview)]+([('detail',detail)] if detail else []):
            check(deadline_ns);require(display_profile(host,renderer)==profile,'display_changed_before_render')
            proof=[];frame_audits=[];t=time.perf_counter_ns()
            try:
                picture=host._readonly_render_view(renderer,store,'SCENE',frame=frame,
                    coverage='all_native_vertices' if kind=='overview' else 'intentional_local_window',
                    expected_evidence=evidence,audit_sink=frame_audits,frustum_sink=proof)
            finally:audits.extend(frame_audits)
            require(display_profile(host,renderer)==profile,'display_changed_after_render')
            require(len(proof)==1 and len(frame_audits)==1,'render_proof_missing')
            raw=base64.b64decode(picture['image_base64'],validate=True);total_bytes+=len(raw)
            require(total_bytes<=LIMITS['png_bytes'],'png_total_budget')
            frames.append(dict(kind=kind,picture=picture,png_sha256=hashlib.sha256(raw).hexdigest(),
                frustum=proof[0],audit=frame_audits[0],elapsed_ns=time.perf_counter_ns()-t))
        after=host.capture_readonly_evidence();after_profile=display_profile(host,renderer)
        final_raw=m.capture_raw(host,object_id,budget=budget)
        require(after==evidence and after_profile==profile and final_raw['source']['raw_sha256']==prepared['source']['raw_sha256'],
                'source_changed_after_observation')
        check(deadline_ns)
        identity={k:prepared['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')}
        return dict(protocol=PROTOCOL,mode=mode,request_id=request_id,object_id=object_id,patch=patch,
            raw=prepared['raw'],identity=identity,evidence=evidence,display=profile,
            source_binding=digest(dict(raw_sha256=prepared['source']['raw_sha256'],
                native=evidence['native_scene'],capture=evidence['capture'],display=profile)),
            plan=planned,frames=frames,started_ns=started,planning_finished_ns=planning_finished,
            finished_ns=time.perf_counter_ns(),deadline_ns=deadline_ns,restored=True,
            read_only=True,execution_authority=False)
    except BaseException:
        if audits:
            try:restored=(all(a['restored'] for a in audits) and host.capture_readonly_evidence()==evidence
                          and display_profile(host,renderer)==profile)
            except BaseException:restored=False
            if not restored:
                store['quarantined']=True;store['quarantine_reason']='patch_restoration_unconfirmed'
        raise
    finally:store['active_request_id']=None
