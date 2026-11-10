for name in ['N16','N12','N24','N04','N19','N13','N28']:
 print(name,'vertices',world[name].round(9).tolist())
mid=(world['N12'][:,2].min()+world['N12'][:,2].max()+world['N24'][:,2].min()+world['N24'][:,2].max())/4
pipe_mid=((world['N04'].min(0)+world['N04'].max(0))/2+(world['N19'].min(0)+world['N19'].max(0))/2)/2
rear=world['N10'][:,1].max()
print('threshold_z',mid,'beam_rear_y',rear,'pipe_mid_xy',pipe_mid[:2].tolist())
for name in ['N15','N16','N18','N25']:
 center=(world[name].min(0)+world[name].max(0))/2
 print(name,'center',center.tolist(),'distance_xy',float(np.linalg.norm(center[:2]-pipe_mid[:2])),'passes',[bool(center[2]<mid),bool(center[1]>rear),bool(np.linalg.norm(center[:2]-pipe_mid[:2])<=.70)])