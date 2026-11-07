import numpy as np, json
n=np.array([2.0,-1.0,2.0])/3.0
print(json.dumps({'unit_direction':n.tolist(),'direction_length':float(np.linalg.norm(n)),'world_vertex_projection_ranges':[{'min':float(np.min(v@n)),'max':float(np.max(v@n))} for v,t in geoms],'vertex_0_difference':(geoms[1][0][0]-geoms[0][0][0]).tolist(),'projection_gap':float(np.min(geoms[1][0]@n)-np.max(geoms[0][0]@n))}))
