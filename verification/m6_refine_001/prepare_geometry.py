"""Freeze target sets and directions from actual baseline Blender readbacks."""

from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra,connected_components


def main():
    started,cpu=time.perf_counter(),time.process_time()
    rows=[]
    if (HERE/"GEOMETRY.json").exists():
        raise RuntimeError("target_geometry_already_prepared")
    for case in read("SOURCES.json")["cases"]:
        directory=HERE/"private/cases"/case["case_id"]
        with np.load(directory/"baseline_readback.npz") as package:
            arrays=dict(package)
        with np.load(directory/"seed.npz") as package:
            F=np.sort(package["F_source_ids"].astype(np.int64))
            seed_local=package["vertices_local"]
        vertices,faces=arrays["vertices"],arrays["faces"]
        if not np.array_equal(arrays["source_ids"],np.arange(len(vertices))):
            raise ValueError("baseline_source_ID_row_mapping_changed")
        if seed_local.tobytes()!=arrays["vertices_local"].tobytes():
            raise ValueError("baseline_native_float32_coordinates_differ_from_source_seed")
        full_edges=np.unique(np.sort(np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])),axis=1),axis=0)
        triangle=vertices[faces]
        cross=np.cross(triangle[:,1]-triangle[:,0],triangle[:,2]-triangle[:,0])
        sums=np.zeros_like(vertices)
        for corner in range(3):
            np.add.at(sums,faces[:,corner],cross)
        norm=np.linalg.norm(sums,axis=1)
        normals=np.divide(sums,norm[:,None],out=np.zeros_like(sums),where=norm[:,None]>0)
        adjacency=csr_matrix((np.ones(len(full_edges)*2),(np.r_[full_edges[:,0],full_edges[:,1]],np.r_[full_edges[:,1],full_edges[:,0]])),shape=(len(vertices),len(vertices)))
        degree=np.asarray(adjacency.sum(axis=1)).ravel()
        neighbor=np.divide(adjacency@normals,degree[:,None],out=np.zeros_like(normals),where=degree[:,None]>0)
        combined=.5*normals+.5*neighbor
        combined_length=np.linalg.norm(combined,axis=1)
        n0=np.divide(combined,combined_length[:,None],out=np.zeros_like(combined),where=combined_length[:,None]>0)
        if not (combined_length[F]>0).all():
            raise ValueError("target_has_unavailable_smoothed_initial_normal")
        fully_inside=np.isin(faces,F).all(axis=1)
        local_faces=faces[fully_inside]
        directed=np.concatenate((local_faces[:,[0,1]],local_faces[:,[1,2]],local_faces[:,[2,0]]))
        edges,incidence=np.unique(np.sort(directed,axis=1),axis=0,return_counts=True)
        B0=np.unique(edges[incidence==1])
        B1=np.setdiff1d(np.unique(edges[np.isin(edges,B0).any(axis=1)]),B0)
        protected=np.union1d(B0,B1)
        I=np.setdiff1d(F,protected)
        lengths=np.linalg.norm(vertices[edges[:,0]]-vertices[edges[:,1]],axis=1)
        graph=csr_matrix((np.tile(lengths,2),(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(len(vertices),len(vertices)))
        distance=dijkstra(graph,directed=False,indices=protected,min_only=True)
        reachable=I[np.isfinite(distance[I])]
        if not len(reachable):
            raise ValueError("no_finite_interior_distance")
        maximum=float(distance[reachable].max())
        center=case["center_source_id"]
        if center is None:
            center=int(reachable[np.lexsort((reachable,-distance[reachable]))[0]])
        if center not in I or not np.isfinite(distance[center]):
            raise ValueError("fixed_center_is_not_reachable_interior")
        C=reachable[distance[reachable]>=.75*maximum]
        interior_edges=edges[np.isin(edges,I).all(axis=1)]
        ell=float(np.median(np.linalg.norm(vertices[interior_edges[:,0]]-vertices[interior_edges[:,1]],axis=1)))
        h=.1*ell
        local_lookup=np.full(len(vertices),-1,dtype=np.int64)
        local_lookup[F]=np.arange(len(F))
        local_pairs=local_lookup[edges]
        local_graph=csr_matrix((np.ones(len(edges)*2),(np.r_[local_pairs[:,0],local_pairs[:,1]],np.r_[local_pairs[:,1],local_pairs[:,0]])),shape=(len(F),len(F)))
        component_count,_=connected_components(local_graph,directed=False)
        initial=directory/"initial.npz"
        np.savez_compressed(initial,**arrays,F_source_ids=F,B0_ids=B0,B1_ids=B1,I_ids=I,C_ids=C,n0=n0,
            boundary_distance=distance,local_edges=edges)
        floor=1e-6 if case["unit"]=="m" else 1e-4*ell
        spec=dict(case_id=case["case_id"],unit=case["unit"],h=h,ell=ell,center_source_id=center,
            source_type=case["source_type"],object_name=case["object_name"],base_blend_path=case["base_blend_path"],
            initial_npz=str(initial),baseline_scene=str(directory/"baseline_scene.json"),source_original=case["source_original"],
            local_distance_max=maximum,center_boundary_distance=float(distance[center]),
            tangent_abs_tol=floor,world_preservation_tol=max(floor,8*np.finfo(np.float32).eps*float(np.max(np.abs(vertices)))),
            normal_definition="normalize(0.5 area-weighted vertex unit normal +0.5 arithmetic mean of full-source one-ring unit normals), one positive-weight averaging step",
            direction_evidence="source winding and preexisting source external-surface interpretation, checked against actual baseline and local geometry views",
            distance_definition="edge-length geodesic on triangles wholly inF, nearest B0 union B1, finite interiors only enter distance maximum andC; unreachable I retained with zero reference displacement",
            core_definition="finite allowed vertices with distance>=0.75 maximum finite distance",require_scene_preservation=True,
            topology_definition="native polygon vertex loops and source vertex IDs, derived looptri tessellation separately reported",
            quality_gate=dict(max_gradient=.2,max_normal_change_deg=5),reference_recipe="hidden from consumers, independent feasibility control only")
        write((directory/"spec.json").relative_to(HERE),spec)
        rows.append(dict(case_id=case["case_id"],F=len(F),B0=len(B0),B1=len(B1),I=len(I),C=len(C),center_source_id=center,
            ell=ell,h=h,Dmax=maximum,center_D=float(distance[center]),local_components=component_count,
            F_unreferenced_by_complete_triangles=np.setdiff1d(F,np.unique(local_faces)).tolist(),
            I_unreachable=I[~np.isfinite(distance[I])].tolist(),normal_mean_F=np.mean(n0[F],axis=0).tolist(),
            initial=identity(initial),spec=identity(directory/"spec.json"),baseline_native_matches_source_seed=True))
        print(case["case_id"],"F/B0/B1/I/C",len(F),len(B0),len(B1),len(I),len(C),"ell",ell,"h",h,flush=True)
    write("GEOMETRY.json",dict(cases=rows,wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu,
        all_targets_frozen_before_consumers=True,supervised_final_displacement_in_consumer_inputs=False))


if __name__=="__main__":
    main()
