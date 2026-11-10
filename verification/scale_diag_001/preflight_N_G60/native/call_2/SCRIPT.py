"""Measured ordinary bpy/NumPy baseline. No production or oracle imports."""
import heapq, json, math, time
import numpy as np

def dot(a,b):return float(a[0]*b[0]+a[1]*b[1]+a[2]*b[2])
def sub(a,b):return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def add(a,b):return (a[0]+b[0],a[1]+b[1],a[2]+b[2])
def mul(a,t):return (a[0]*t,a[1]*t,a[2]*t)
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def point_triangle(p,t):
    a,b,c=t;ab=sub(b,a);ac=sub(c,a);ap=sub(p,a)
    d1=dot(ab,ap);d2=dot(ac,ap)
    if d1<=0 and d2<=0:return a
    bp=sub(p,b);d3=dot(ab,bp);d4=dot(ac,bp)
    if d3>=0 and d4<=d3:return b
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:return add(a,mul(ab,d1/(d1-d3)))
    cp=sub(p,c);d5=dot(ab,cp);d6=dot(ac,cp)
    if d6>=0 and d5<=d6:return c
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:return add(a,mul(ac,d2/(d2-d6)))
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))))
    den=va+vb+vc
    if den==0:raise ValueError('degenerate_triangle')
    return add(a,add(mul(ab,vb/den),mul(ac,vc/den)))

def segment_segment(p,q,r,s):
    u,v,w=sub(q,p),sub(s,r),sub(p,r)
    a,b,c,d,e=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
    if a==0 or c==0:raise ValueError('zero_edge')
    den=a*c-b*b
    x=max(0.,min(1.,(b*e-c*d)/den)) if den>1e-30*a*c else 0.
    y=(b*x+e)/c
    if y<0:y=0.;x=max(0.,min(1.,-d/a))
    elif y>1:y=1.;x=max(0.,min(1.,(b-d)/a))
    return add(p,mul(u,x)),add(r,mul(v,y))

def piercing(p,q,t):
    a,b,c=t;u=sub(q,p);e1=sub(b,a);e2=sub(c,a);h=cross(u,e2);det=dot(e1,h)
    # Coplanar cases are covered below by vertex-face and edge-edge zero.
    if abs(det)<=1e-14*max(1e-30,math.sqrt(dot(e1,e1)*dot(e2,e2)*dot(u,u))):return None
    inv=1/det;s=sub(p,a);v=dot(s,h)*inv
    if v<0 or v>1:return None
    z=cross(s,e1);w=dot(u,z)*inv
    if w<0 or v+w>1:return None
    x=dot(e2,z)*inv
    return add(p,mul(u,x)) if 0<=x<=1 else None

def triangle_pair(a,b,counts):
    counts['triangle_pairs']+=1
    for x,y in ((a,b),(b,a)):
        for i in range(3):
            counts['segment_face_tests']+=1
            hit=piercing(x[i],x[(i+1)%3],y)
            if hit is not None:return 0.,hit,hit
    best=(float('inf'),None,None)
    for p in a:
        q=point_triangle(p,b);v=sub(p,q);counts['point_face_tests']+=1
        if dot(v,v)<best[0]:best=(dot(v,v),p,q)
    for q in b:
        p=point_triangle(q,a);v=sub(p,q);counts['point_face_tests']+=1
        if dot(v,v)<best[0]:best=(dot(v,v),p,q)
    for i in range(3):
        for j in range(3):
            p,q=segment_segment(a[i],a[(i+1)%3],b[j],b[(j+1)%3]);v=sub(p,q);counts['edge_edge_tests']+=1
            if dot(v,v)<best[0]:best=(dot(v,v),p,q)
    return best

def bound(a,b):
    d=np.maximum(0.,np.maximum(a[0]-b[1],b[0]-a[1]))
    # Conservative slack for float arithmetic; never prune a boundary tie.
    return max(0.,float(d@d)-1e-14)

class Geometry:
    def __init__(self,local,faces,matrix,deadline,counts):
        self.local=local;self.faces=faces;self.matrix=matrix
        self.world=np.array([[sum(matrix[j,i]*p[i] for i in range(3))+matrix[j,3] for j in range(3)] for p in local])
        self.tris=self.world[faces];self.lo=self.tris.min(axis=1);self.hi=self.tris.max(axis=1)
        self.nodes=[];self.cent=(self.lo+self.hi)*.5
        self.root=self.build(np.arange(len(faces)),deadline)
        self.bounds=(self.world.min(axis=0),self.world.max(axis=0));self.qualified=None
        counts['vertices_copied']+=len(local);counts['triangles_copied']+=len(faces);counts['index_builds']+=1
    def build(self,ids,deadline):
        if time.perf_counter_ns()>=deadline:raise TimeoutError('native_index_deadline')
        lo,hi=self.lo[ids].min(axis=0),self.hi[ids].max(axis=0);idx=len(self.nodes);self.nodes.append(None)
        if len(ids)<=4:self.nodes[idx]=((lo,hi),None,None,ids)
        else:
            axis=int(np.argmax(np.ptp(self.cent[ids],axis=0)));ids=ids[np.argsort(self.cent[ids,axis],kind='stable')];mid=len(ids)//2
            left=self.build(ids[:mid],deadline);right=self.build(ids[mid:],deadline);self.nodes[idx]=((lo,hi),left,right,None)
        return idx
    def bytes(self):
        arrays=[self.local,self.faces,self.matrix,self.world,self.tris,self.lo,self.hi,self.cent]
        arrays += [arr for node in self.nodes for arr in (node[0][0],node[0][1],node[3]) if arr is not None]
        return sum(a.nbytes for a in arrays)

def nearest(a,b,deadline,c):
    best=(float('inf'),None,None);queue=[(bound(a.nodes[0][0],b.nodes[0][0]),0,0)]
    while queue:
        if time.perf_counter_ns()>=deadline:raise TimeoutError('native_precision_deadline')
        lower,i,j=heapq.heappop(queue);c['node_pair_visits']+=1
        if lower>best[0]+1e-14:c['node_pruned']+=1;continue
        na,nb=a.nodes[i],b.nodes[j]
        if na[3] is not None and nb[3] is not None:
            for x in na[3]:
                for y in nb[3]:
                    c['triangle_bound_tests']+=1
                    if bound((a.lo[x],a.hi[x]),(b.lo[y],b.hi[y]))>best[0]+1e-14:c['triangle_pruned']+=1;continue
                    value=triangle_pair(a.tris[x],b.tris[y],c)
                    if value[0]<best[0]:best=value
        else:
            if nb[3] is not None or (na[3] is None and float(np.prod(na[0][1]-na[0][0]))>=float(np.prod(nb[0][1]-nb[0][0]))):
                pairs=((na[1],j),(na[2],j))
            else:pairs=((i,nb[1]),(i,nb[2]))
            for x,y in pairs:
                lower=bound(a.nodes[x][0],b.nodes[y][0])
                if lower<=best[0]+1e-14:heapq.heappush(queue,(lower,x,y))
                else:c['node_pruned']+=1
    return math.sqrt(max(0.,best[0])),list(best[1]),list(best[2])

def qualify_prism(g,deadline):
    """Closed, embedded two-layer extrusion; derive cap/boundary from topology."""
    z=np.unique(g.local[:,2])
    if len(z)!=2:return False
    if len({tuple(v) for v in g.local})!=len(g.local):return False
    edges={};caps=[]
    for f in g.faces:
        if time.perf_counter_ns()>=deadline:raise TimeoutError('native_solid_deadline')
        for a,b in zip(f,np.roll(f,-1)):edges.setdefault(tuple(sorted((int(a),int(b)))),[]).append((int(a),int(b)))
        if len(set(g.local[f,2]))==1:caps.append(f)
    if any(len(v)!=2 or v[0]!=tuple(reversed(v[1])) for v in edges.values()):return False
    areas=[];boundaries=[];boundary_edges=[]
    for layer in z:
        fs=[f for f in caps if g.local[f[0],2]==layer];counts={};signed=[]
        for f in fs:
            p=g.local[f,:2];u=p[1]-p[0];v=p[2]-p[0];signed.append(float(u[0]*v[1]-u[1]*v[0]))
            for a,b in zip(f,np.roll(f,-1)):counts[tuple(sorted((int(a),int(b))))]=counts.get(tuple(sorted((int(a),int(b)))),0)+1
        if not signed or min(map(abs,signed))<=1e-18 or not (all(x>0 for x in signed) or all(x<0 for x in signed)):return False
        bd=[key for key,v in counts.items() if v==1];adj={}
        for a,b in bd:adj.setdefault(a,[]).append(b);adj.setdefault(b,[]).append(a)
        if any(len(v)!=2 for v in adj.values()):return False
        order=[min(adj)];prev=None;cur=order[0]
        while True:
            nxt=next((v for v in adj[cur] if v!=prev),None)
            if nxt==order[0]:break
            if nxt is None or nxt in order:return False
            order.append(nxt);prev,cur=cur,nxt
        if len(order)!=len(adj):return False
        if {int(v) for f in fs for v in f}!=set(adj):return False
        pts=g.local[order,:2];N=len(pts)
        for i in range(N):
            if time.perf_counter_ns()>=deadline:raise TimeoutError('native_solid_deadline')
            p,q=pts[i],pts[(i+1)%N];r,s=pts,np.roll(pts,-1,axis=0)
            def orient(a,b,c):return (b[...,0]-a[...,0])*(c[...,1]-a[...,1])-(b[...,1]-a[...,1])*(c[...,0]-a[...,0])
            o1,o2,o3,o4=orient(p,q,r),orient(p,q,s),orient(r,s,p),orient(r,s,q)
            mask=(o1*o2<=0)&(o3*o4<=0)&(np.maximum(np.minimum(p[0],q[0]),np.minimum(r[:,0],s[:,0]))<=np.minimum(np.maximum(p[0],q[0]),np.maximum(r[:,0],s[:,0])))&(np.maximum(np.minimum(p[1],q[1]),np.minimum(r[:,1],s[:,1]))<=np.minimum(np.maximum(p[1],q[1]),np.maximum(r[:,1],s[:,1])))
            mask[[i,(i-1)%N,(i+1)%N]]=False
            if np.any(mask):return False
        polyarea=abs(float(np.sum(pts[:,0]*np.roll(pts[:,1],-1)-pts[:,1]*np.roll(pts[:,0],-1))))
        if abs(sum(map(abs,signed))-polyarea)>1e-10 or len({int(v) for f in fs for v in f})-len(counts)+len(fs)!=1:return False
        areas.append(polyarea);boundaries.append({tuple(p) for p in pts})
        boundary_edges.append({frozenset((tuple(g.local[a,:2]),tuple(g.local[b,:2]))) for a,b in bd})
    if boundaries[0]!=boundaries[1] or abs(areas[0]-areas[1])>1e-10:return False
    if boundary_edges[0]!=boundary_edges[1]:return False
    sides={}
    for f in g.faces:
        if len(set(g.local[f,2]))==1:continue
        xy=frozenset(tuple(p[:2]) for p in g.local[f])
        if len(xy)!=2 or xy not in boundary_edges[0]:return False
        sides.setdefault(xy,[]).append({tuple(p) for p in g.local[f]})
    if set(sides)!=boundary_edges[0]:return False
    for xy,faces in sides.items():
        corners={(x,y,float(level)) for x,y in xy for level in z}
        if len(faces)!=2 or len(faces[0])!=3 or len(faces[1])!=3 or faces[0]|faces[1]!=corners:return False
        diagonal=faces[0]&faces[1]
        if len(diagonal)!=2:return False
        p,q=diagonal
        if p[:2]==q[:2] or p[2]==q[2]:return False
    return True

def solid_relation(a,b,deadline):
    for g in (a,b):
        if g.qualified is None:g.qualified=qualify_prism(g,deadline)
    if not a.qualified or not b.qualified:return {'status':'unknown','relation':None,'reason':'native_closed_prism_qualification_failed'}
    for g in (a,b):
        for tri in g.tris:
            if time.perf_counter_ns()>=deadline:raise TimeoutError('native_solid_deadline')
            n=np.cross(tri[1]-tri[0],tri[2]-tri[0]);norm=float(np.linalg.norm(n))
            if norm==0:continue
            n/=norm;x=a.world@n;y=b.world@n
            if max(float(y.min()-x.max()),float(x.min()-y.max()))>1e-10:
                return {'status':'measured','relation':'separated','reason':'independently_qualified_prisms_support_separation'}
    return {'status':'unknown','relation':None,'reason':'native_no_separating_support_certificate'}

class Solver:
    def __init__(self):self.cache={};self.pairs={};self.revision=0
    def change(self,step):
        if step==6:self.cache.clear();self.pairs.clear()
        elif step in (3,4,5):
            self.cache={k:v for k,v in self.cache.items() if v['logical_id']!='competitor'}
            self.pairs.clear()
        self.revision+=1
    def query(self,mode,deadline_ns):
        import bpy
        started=time.perf_counter_ns();c={k:0 for k in ['directory_objects','vertices_copied','triangles_copied','index_builds','index_reuses','pair_cache_hits','pair_calls','triangle_pairs','segment_face_tests','point_face_tests','edge_edge_tests','node_pair_visits','node_pruned','triangle_bound_tests','triangle_pruned','aabb_candidates','aabb_excluded']}
        stages={};directory=sorted((o for o in bpy.context.scene.objects if o.type=='MESH'),key=lambda o:o.name);c['directory_objects']=len(directory)
        rows={};mark=time.perf_counter_ns();live=set()
        for o in directory:
            if time.perf_counter_ns()>=deadline_ns:raise TimeoutError('native_directory_deadline')
            if mode=='G' and o.name not in ('Target','Peer_000'):continue
            key=int(o.session_uid);live.add(key);matrix=np.array([list(r) for r in o.matrix_world],dtype=float)
            row=self.cache.get(key);data_id=int(o.data.session_uid)
            if row is None or row['data_id']!=data_id or not np.array_equal(row['g'].matrix,matrix):
                local=np.array([list(v.co) for v in o.data.vertices],dtype=float);faces=np.array([list(f.vertices) for f in o.data.polygons],dtype=np.int64)
                if faces.ndim!=2 or faces.shape[1]!=3:raise ValueError('native_requires_triangles')
                row={'logical_id':o.get('scale_logical_id'),'data_id':data_id,'g':Geometry(local,faces,matrix,deadline_ns,c)};self.cache[key]=row
            else:c['index_reuses']+=1
            rows[o.name]=(key,row['g'])
        self.cache={k:v for k,v in self.cache.items() if k in live};stages['directory_expand_index_ns']=time.perf_counter_ns()-mark
        target_key,target=rows['Target'];names=['Peer_000'] if mode=='G' else [name for name in rows if name!='Target']
        ranked=sorted((bound(target.bounds,rows[name][1].bounds),name) for name in names)
        best=float('inf');winners=[];witness=None;mark=time.perf_counter_ns();pair=None
        for lower,name in ranked:
            if lower>best*best+1e-14:c['aabb_excluded']+=1;continue
            c['aabb_candidates']+=1;key,geo=rows[name];pkey=(target_key,key,id(target),id(geo))
            if pkey in self.pairs:value=self.pairs[pkey];c['pair_cache_hits']+=1
            else:
                c['pair_calls']+=1;value=nearest(target,geo,deadline_ns,c);self.pairs[pkey]=value
            if value[0]<best-1e-9:best=value[0];winners=[name];witness=value[1:];pair=geo
            elif abs(value[0]-best)<=1e-9:winners.append(name)
        stages['distance_ns']=time.perf_counter_ns()-mark;mark=time.perf_counter_ns()
        relation=solid_relation(target,pair,deadline_ns) if mode=='G' else None
        stages['solid_ns']=time.perf_counter_ns()-mark
        result={'status':'complete','distance_m':best,'nearest_names':sorted(winners),'witness':witness,'solid':relation,'work':c,'stages':stages,
                'cache_array_bytes':sum(row['g'].bytes() for row in self.cache.values()),'cache_geometry_count':len(self.cache),'revision':self.revision}
        result['computation_ns']=time.perf_counter_ns()-started
        if time.perf_counter_ns()>=deadline_ns:raise TimeoutError('native_report_deadline')
        return result

_scale_solver=Solver()
_scale_result=_scale_solver.query('G',402212843826300)
print(json.dumps(_scale_result,allow_nan=False,separators=(',',':')))
