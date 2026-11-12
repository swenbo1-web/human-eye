def dot_rows(left,right):
    return np.einsum('...i,...i->...',left,right)
def point_segment_sq(point,start,end):
    direction=end-start
    denom=dot_rows(direction,direction)
    fraction=np.clip(np.divide(dot_rows(point-start,direction),denom,out=np.zeros_like(denom),where=denom>0),0,1)
    delta=point-start-fraction[...,None]*direction
    return dot_rows(delta,delta)
def point_triangle_sq(point,tri):
    start=tri[:,0]; edge1=tri[:,1]-start; edge2=tri[:,2]-start
    normal=np.cross(edge1,edge2); normal_sq=dot_rows(normal,normal)
    offset=point-start
    height=dot_rows(offset,normal)
    projected=offset-np.divide(height,normal_sq,out=np.zeros_like(height),where=normal_sq>0)[:,None]*normal
    aa=dot_rows(edge1,edge1); ab=dot_rows(edge1,edge2); bb=dot_rows(edge2,edge2)
    pa=dot_rows(projected,edge1); pb=dot_rows(projected,edge2)
    det=aa*bb-ab*ab
    u=np.divide(bb*pa-ab*pb,det,out=np.full_like(det,np.inf),where=det>0)
    v=np.divide(aa*pb-ab*pa,det,out=np.full_like(det,np.inf),where=det>0)
    inside=(u>=0)&(v>=0)&(u+v<=1)&(normal_sq>0)
    result=np.minimum.reduce([point_segment_sq(point,tri[:,index],tri[:,(index+1)%3]) for index in range(3)])
    plane_sq=np.divide(height*height,normal_sq,out=np.full_like(height,np.inf),where=normal_sq>0)
    return np.where(inside,np.minimum(result,plane_sq),result)
def segment_segment_sq(start1,end1,start2,end2):
    dir1=end1-start1; dir2=end2-start2; offset=start1-start2
    aa=dot_rows(dir1,dir1); bb=dot_rows(dir1,dir2); cc=dot_rows(dir2,dir2)
    dd=dot_rows(dir1,offset); ee=dot_rows(dir2,offset); det=aa*cc-bb*bb
    valid=det>1e-14*aa*cc
    along1=np.divide(bb*ee-cc*dd,det,out=np.zeros_like(det),where=valid)
    along2=np.divide(aa*ee-bb*dd,det,out=np.zeros_like(det),where=valid)
    interior=valid&(along1>=0)&(along1<=1)&(along2>=0)&(along2<=1)
    delta=offset+along1[:,None]*dir1-along2[:,None]*dir2
    result=np.minimum.reduce([point_segment_sq(start1,start2,end2),point_segment_sq(end1,start2,end2),point_segment_sq(start2,start1,end1),point_segment_sq(end2,start1,end1)])
    return np.where(interior,np.minimum(result,dot_rows(delta,delta)),result)
def segment_hits_triangle(start,end,tri):
    direction=end-start; edge1=tri[:,1]-tri[:,0]; edge2=tri[:,2]-tri[:,0]
    h=np.cross(direction,edge2); determinant=dot_rows(edge1,h)
    valid=np.abs(determinant)>1e-14*np.sqrt(dot_rows(edge1,edge1)*dot_rows(h,h))
    inv=np.divide(1.,determinant,out=np.zeros_like(determinant),where=valid)
    offset=start-tri[:,0]; u=inv*dot_rows(offset,h)
    q=np.cross(offset,edge1); v=inv*dot_rows(direction,q); along=inv*dot_rows(edge2,q)
    return valid&(u>=0)&(v>=0)&(u+v<=1)&(along>=0)&(along<=1)
def triangle_pair_distances(tri1,tri2):
    count1,count2=len(tri1),len(tri2)
    first=np.repeat(tri1,count2,axis=0); second=np.tile(tri2,(count1,1,1))
    squared=np.full(len(first),np.inf); hits=np.zeros(len(first),dtype=bool)
    for vertex in range(3):
        squared=np.minimum(squared,point_triangle_sq(first[:,vertex],second))
        squared=np.minimum(squared,point_triangle_sq(second[:,vertex],first))
        hits|=segment_hits_triangle(first[:,vertex],first[:,(vertex+1)%3],second)
        hits|=segment_hits_triangle(second[:,vertex],second[:,(vertex+1)%3],first)
        for other in range(3):
            squared=np.minimum(squared,segment_segment_sq(first[:,vertex],first[:,(vertex+1)%3],second[:,other],second[:,(other+1)%3]))
    squared[hits]=0
    nearest=int(np.argmin(squared))
    return math.sqrt(max(0,float(squared[nearest]))),bool(hits[nearest]),(nearest//count2,nearest%count2)
started=time.time()
results=[]
for first,second,lower in candidates:
    distance,hit,triangle_indices=triangle_pair_distances(meshes[first]['tri'],meshes[second]['tri'])
    results.append((first,second,distance,hit,triangle_indices))
print('elapsed',time.time()-started)
near=[row for row in results if row[2]<=2.0]
print('qualifying',len(near))
for first,second,distance,hit,indices in near:
    print(meshes[first]['name'],meshes[second]['name'],format(distance,'.12f'),'crossing',hit,'tri',indices)
print('nonqualifying_candidates',[(meshes[a]['name'],meshes[b]['name'],round(d,9)) for a,b,d,_,_ in results if d>2])
print('degenerate_triangles',[(entry['name'],int(np.sum(np.linalg.norm(np.cross(entry['tri'][:,1]-entry['tri'][:,0],entry['tri'][:,2]-entry['tri'][:,0]),axis=1)==0))) for entry in meshes])