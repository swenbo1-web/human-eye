def crosses(begin,end,triangles):
    direction=end-begin
    first=triangles[:,1]-triangles[:,0]; second=triangles[:,2]-triangles[:,0]
    cross=np.cross(direction,second); determinant=np.sum(first*cross,axis=-1)
    scale=np.linalg.norm(direction,axis=-1)*np.linalg.norm(np.cross(first,second),axis=-1)
    valid=np.abs(determinant)>1e-12*scale
    inverse=np.divide(1.0,determinant,out=np.zeros_like(determinant),where=valid)
    offset=begin-triangles[:,0]
    bary_a=np.sum(offset*cross,axis=-1)*inverse
    cross2=np.cross(offset,first)
    bary_b=np.sum(direction*cross2,axis=-1)*inverse
    parameter=np.sum(second*cross2,axis=-1)*inverse
    return valid&(bary_a>=0)&(bary_b>=0)&(bary_a+bary_b<=1)&(parameter>=0)&(parameter<=1)
results=sorted((mesh_distance(current['Target'][0],triangles),name) for name,(triangles,vertices) in current.items() if name!='Target')
print('all_distances_m',results)
