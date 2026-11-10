started=time.time()
for name,data in geo.items():
    if name=='Mesh_D17AB2': continue
    minimum=float('inf')
    for first in target:
        for second in data['tri']:
            minimum=min(minimum,triangle_distance(first,second)[0])
    print(name,'exhaustive_mm',format(math.sqrt(minimum)*1000,'.12f'),'matches_pruned',abs(minimum-results[name][0])<1e-24,'pairs',len(target)*len(data['tri']))
print('seconds',time.time()-started)
print('winner_bbox_lower_bound_mm',(geo['Mesh_097A63']['v'][:,0].min()-geo['Mesh_D17AB2']['v'][:,0].max())*1000)
print('target_triangle_11',target[11].tolist())
print('winner_triangle_5',geo['Mesh_097A63']['tri'][5].tolist())
print('degenerate_triangles',{name:int(np.count_nonzero(np.linalg.norm(np.cross(data['tri'][:,1]-data['tri'][:,0],data['tri'][:,2]-data['tri'][:,0]),axis=1)==0)) for name,data in geo.items()})