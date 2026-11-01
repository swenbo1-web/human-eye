"""Independent exact-rational replay of finite local surface provenance.

No producer imports. Work units bound structural visits, not machine cycles.
"""
from fractions import Fraction as Q
import hashlib
import json


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum((x*y for x,y in zip(a,b)),Q(0))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def binding(native,object_id,edges):
    data=json.dumps({'native':native,'object_id':object_id,'edges':edges},ensure_ascii=True,
        sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
    assert len(data)<=1024*1024
    return hashlib.sha256(data).hexdigest()


def point_segment_sq(p,a,b):
    ab=sub(b,a);ap=sub(p,a);den=dot(ab,ab)
    t=min(Q(1),max(Q(0),dot(ap,ab)/den)) if den else Q(0)
    residual=tuple(ap[k]-t*ab[k] for k in range(3))
    return dot(residual,residual)


def segment_sq(a,b,c,d):
    values=[point_segment_sq(p,x,y) for p,x,y in ((a,c,d),(b,c,d),(c,a,b),(d,a,b))]
    u,v,w=sub(b,a),sub(d,c),sub(a,c)
    aa,bb,cc,dd,ee=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    determinant=aa*cc-bb*bb
    if determinant:
        s=(bb*ee-cc*dd)/determinant;t=(aa*ee-bb*dd)/determinant
        if 0<=s<=1 and 0<=t<=1:
            residual=tuple(w[k]+s*u[k]-t*v[k] for k in range(3))
            values.append(dot(residual,residual))
    return min(values)


class ExactLocalIndex:
    def __init__(self,target,maximum,policy='strict_coplanar'):
        assert type(maximum) is int and 0<=maximum<=32768
        assert policy in ('strict_coplanar','visual_nearplanar')
        self.policy=policy
        self.maximum=maximum;self.work=0
        self.points=[tuple(Q(x) for x in p) for p in target['world_vertices']]
        self.faces=target['faces'];self.links={};self.normals={}
        self.reserve(6*len(self.faces))
        for i,face in enumerate(self.faces):
            assert len(face)==3 and len(set(face))==3
            for j in range(3):
                a,b=face[j],face[(j+1)%3]
                assert type(a) is int and type(b) is int and 0<=a<len(self.points) and 0<=b<len(self.points)
                self.links.setdefault(frozenset((a,b)),[]).append((i,a,b))

    def reserve(self,count):
        self.work+=count
        assert self.work<=self.maximum

    def normal(self,index):
        if index not in self.normals:
            self.reserve(2)
            a,b,c=[self.points[v] for v in self.faces[index]]
            n=cross(sub(b,a),sub(c,a));assert dot(n,n)>Q('1e-30')
            self.normals[index]=n
        return self.normals[index]

    def reconstruct(self,edge,radius):
        a,b=edge;start,end=self.points[a],self.points[b]
        incident=self.links[frozenset(edge)];assert len(incident)==1
        seed=incident[0][0];n=self.normal(seed);nsq=dot(n,n)
        length_sq=dot(sub(end,start),sub(end,start));assert length_sq>0
        normal_sine=1e-8 if self.policy=='strict_coplanar' else 1/1024
        plane_limit=(float(length_sq)**.5)*1e-10 if self.policy=='strict_coplanar' else radius/96
        radius_sq=Q(radius)**2;pending=[seed];seen={seed};accepted=[]
        while pending:
            self.reserve(2);index=pending.pop(0);assert len(seen)<=128
            other=self.normal(index);angle=cross(n,other)
            if dot(n,other)<=0 or dot(angle,angle)>Q(normal_sine)**2*nsq*dot(other,other):continue
            plane_squared=(Q('1e-20')*length_sq if self.policy=='strict_coplanar' else Q(plane_limit)**2)
            if any(dot(n,sub(self.points[v],start))**2>plane_squared*nsq for v in self.faces[index]):continue
            accepted.append(index)
            face=self.faces[index]
            for i in range(3):
                self.reserve(2);x,y=face[i],face[(i+1)%3]
                links=self.links[frozenset((x,y))]
                if len(links)!=2:continue
                left,right=links
                if (left[1],left[2])!=(right[2],right[1]):continue
                neighbour=right[0] if left[0]==index else left[0]
                if neighbour in seen:continue
                if segment_sq(start,end,self.points[x],self.points[y])>radius_sq:continue
                seen.add(neighbour);pending.append(neighbour)
        return {'edge':list(edge),'seed_face':seed,'face_ids':sorted(accepted),'radius':radius,
            'visited_face_count':len(seen),'scope':'oriented_bounded_plane_capsule_connected',
            'policy':self.policy,'max_plane_deviation':plane_limit,'max_normal_sine':normal_sine}

    def validate_hit(self,proof,point,direction,hits,object_id):
        if not hits:return False
        a,b=[self.points[v] for v in proof['edge']]
        for owner,index,depth in hits:
            if owner!=object_id or index not in proof['face_ids']:return False
            actual=tuple(Q(point[k]+depth*direction[k]) for k in range(3))
            if point_segment_sq(actual,a,b)>Q(proof['radius'])**2:return False
        return True

    def validate_features(self,edges,features):
        """Check a complete partition of native edges, without producer walk."""
        self.reserve(8*len(edges));neighbours={};normals={}
        for a,b in edges:
            neighbours.setdefault(a,[]).append(b);neighbours.setdefault(b,[]).append(a)
        def qnormal(a,b):
            incident=self.links[frozenset((a,b))];assert len(incident)==1
            face=incident[0][0]
            if face not in normals:
                x,y,z=[self.points[v] for v in self.faces[face]]
                normals[face]=cross(sub(y,x),sub(z,x))
            return normals[face]
        corners=set()
        for v,ns in neighbours.items():
            assert len(ns)==2
            left,right=(sub(self.points[x],self.points[v]) for x in ns)
            a,b=(qnormal(v,x) for x in ns)
            if any(cross(left,right)) or dot(left,right)>=0 or any(cross(a,b)) or dot(a,b)<=0:corners.add(v)
        assert len(corners)>=3 and len(features)==len(corners)
        assert features[0]['edge'][0]==min(corners,key=lambda v:self.points[v])
        assert self.points[features[0]['edge'][1]]<self.points[features[-1]['edge'][0]]
        covered=[];begins=[]
        for i,feature in enumerate(features):
            start,end=feature['edge'];chain=feature['source_edges']
            assert start in corners and end in corners and start!=end and chain
            assert chain[0][0]==start and chain[-1][1]==end
            assert end==features[(i+1)%len(features)]['edge'][0]
            for j,(a,b) in enumerate(chain):
                assert b in neighbours[a]
                if j:assert a==chain[j-1][1] and a not in corners
                covered.append(frozenset((a,b)))
            begins.append(start)
        assert len(set(begins))==len(corners) and set(begins)==corners
        assert len(covered)==len(edges) and len(set(covered))==len(edges)
        assert set(covered)=={frozenset(edge) for edge in edges}
        return features

    def sample_source(self,feature,numerator):
        a,b=[self.points[v] for v in feature['edge']]
        point=tuple(((4-numerator)*a[k]+numerator*b[k])/4 for k in range(3))
        for x,y in feature['source_edges']:
            if point_segment_sq(point,self.points[x],self.points[y])==0:return [x,y]
        raise AssertionError('sample has no native source')
