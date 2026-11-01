"""Verification-only finite, oriented bounded-plane surface provenance."""
import hashlib
import json
import math
import time
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
        self.reserve(6*len(self.faces))  # Three links, producer + verifier.
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
