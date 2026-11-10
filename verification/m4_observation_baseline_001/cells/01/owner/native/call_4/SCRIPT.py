print('geometry modifiers',[(n,[(m.name,m.type) for m in o.modifiers]) for n,o in sorted(meshes.items()) if len(o.modifiers)])
frame=world['N16']; block=world['N08']; rod=world['N28']
print('left gap m',frame[:,0].min()-block[:,0].max())
print('rod vertical clearances m',rod[:,2].min()-frame[4,2],frame[6,2]-rod[:,2].max())
print('rod horizontal clearances m',rod[:,0].min()-frame[4,0],frame[5,0]-rod[:,0].max())
print('right overlap XYZ m',np.minimum(frame.max(0),world['N13'].max(0))-np.maximum(frame.min(0),world['N13'].min(0)))
print('rail midpoint Z',sum((world[n][:,2].min()+world[n][:,2].max())/2 for n in ['N12','N24'])/2)
print('front beam back Y',world['N10'][:,1].max())
