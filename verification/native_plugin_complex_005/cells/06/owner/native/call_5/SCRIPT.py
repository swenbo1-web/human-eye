winner='Near_017'; gg=geom[winner]
print('winner_witness',results[winner][1].tolist(),results[winner][3])
print('same_vertex_shape',tg['v'].shape==gg['v'].shape,'max_world_vertex_difference',float(np.max(np.abs(tg['v']-gg['v']))),'same_triangles',bool(np.array_equal(tg['t'],gg['t'])))
edge_index=results[winner][3][1];tri_index=results[winner][3][2]
print('Target_edge_indices',tg['e'][edge_index].tolist(),'world',tg['v'][tg['e'][edge_index]].tolist())
print('Near_017_triangle_indices',gg['t'][tri_index].tolist(),'world',gg['v'][gg['t'][tri_index]].tolist())
print('evaluated_mesh_coverage',len(geom),'candidates',len(results),'triangles_per_object',sorted(set(len(g['t']) for g in geom.values())))
print('runner_up_witness',results['Peer_000'][1].tolist(),results['Peer_000'][2].tolist())