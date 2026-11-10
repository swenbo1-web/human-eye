print('geometry modifiers',[(name,[(m.name,m.type) for m in objs[name].modifiers]) for name in ['N16','N13','N08','N28']])
f=world['N16']; block=world['N08']; rod=world['N28']
print('left_gap_m',f[:,0].min()-block[:,0].max())
print('left_witnesses',(float(block[:,0].max()),0.1,0.36),(float(f[:,0].min()),0.1,0.36))
print('overlap_witness',(0.245,0.1,0.36))
print('overlap_box_min',(max(f[5,0],world['N13'][:,0].min()),max(f[:,1].min(),world['N13'][:,1].min()),max(f[:,2].min(),world['N13'][:,2].min())))
print('overlap_box_max',(min(f[:,0].max(),world['N13'][:,0].max()),min(f[:,1].max(),world['N13'][:,1].max()),min(f[:,2].max(),world['N13'][:,2].max())))
print('rod_clearances_m',{'left':rod[:,0].min()-f[4,0],'right':f[5,0]-rod[:,0].max(),'bottom':rod[:,2].min()-f[4,2],'top':f[6,2]-rod[:,2].max()})
print('rod_top_witness',(float(rod[3,0]),0.1,float(rod[3,2])),'frame_top_inner_witness',(float(rod[3,0]),0.1,float(f[6,2])))