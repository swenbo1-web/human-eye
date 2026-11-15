"""One shared current-surface neighborhood table, five scales and batched descriptors."""

from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write,measure
import numpy as np
from scipy.spatial import cKDTree


def describe_current(vertices,faces,F,counts=(16,48,128,384,1024)):
    timings={}
    with measure(timings,"current_area_vertex_normals"):
        tri=vertices[faces]
        cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        cross_length=np.linalg.norm(cross,axis=1)
        area=np.zeros(len(vertices))
        normal_sum=np.zeros_like(vertices)
        for corner in range(3):
            np.add.at(area,faces[:,corner],cross_length/6)
            np.add.at(normal_sum,faces[:,corner],cross)
        normal_length=np.linalg.norm(normal_sum,axis=1)
        normals=np.divide(normal_sum,normal_length[:,None],out=np.zeros_like(vertices),where=normal_length[:,None]>0)
        valid=np.isfinite(normals[F]).all(axis=1)&(normal_length[F]>0)
    with measure(timings,"one_KDtree_and_batched_maximal_neighbor_query"):
        tree=cKDTree(vertices)
        distances,neighbor_ids=tree.query(vertices[F],k=max(counts),workers=1)
        offset=vertices[neighbor_ids]-vertices[F,None,:]
        query_normals=normals[F]
        axes=np.eye(3)[np.argmin(np.abs(query_normals),axis=1)]
        tangent=np.cross(query_normals,axes)
        tangent/=np.maximum(np.linalg.norm(tangent,axis=1,keepdims=True),1e-30)
        bitangent=np.cross(query_normals,tangent)
        height=np.einsum("nkj,nj->nk",offset,query_normals)
        tx=np.einsum("nkj,nj->nk",offset,tangent)
        ty=np.einsum("nkj,nj->nk",offset,bitangent)
        dots=np.einsum("nkj,nj->nk",normals[neighbor_ids],query_normals)
        spacing=np.maximum(distances[:,15],np.finfo(float).tiny)
    descriptor=[]
    ring_counts=[]
    radii=[]
    with measure(timings,"five_scale_shared_prefix_geometry_descriptors"):
        for count in counts:
            radius=np.maximum(distances[:,count-1],np.finfo(float).tiny)
            radii.append(radius)
            normalized=offset[:,:count]/radius[:,None,None]
            h=height[:,:count]/radius[:,None]
            x=tx[:,:count]/radius[:,None]
            y=ty[:,:count]/radius[:,None]
            weights=area[neighbor_ids[:,:count]].copy()
            weights/=np.maximum(weights.sum(axis=1,keepdims=True),1e-30)
            mean_h=np.sum(weights*h,axis=1)
            std_h=np.sqrt(np.maximum(0,np.sum(weights*(h-mean_h[:,None])**2,axis=1)))
            nd=dots[:,:count]
            mean_dot=np.sum(weights*nd,axis=1)
            std_dot=np.sqrt(np.maximum(0,np.sum(weights*(nd-mean_dot[:,None])**2,axis=1)))
            centroid=np.sum(normalized*weights[:,:,None],axis=1)
            centered=normalized-centroid[:,None]
            covariance=np.einsum("nki,nkj,nk->nij",centered,centered,weights)
            eigenvalues=np.linalg.eigvalsh(covariance)
            eigenvalues=np.maximum(eigenvalues,0)
            normalized_eigenvalues=eigenvalues/np.maximum(eigenvalues.sum(axis=1,keepdims=True),1e-30)
            ring=distances[:,:count]>=.6*radius[:,None]
            ring_counts.append(ring.sum(axis=1))
            ring_weights=weights*ring
            ring_weights/=np.maximum(ring_weights.sum(axis=1,keepdims=True),1e-30)
            design=np.stack((x*x,x*y,y*y,x,y,np.ones_like(x)),axis=2)
            gram=np.einsum("nki,nkj,nk->nij",design,design,ring_weights)
            rhs=np.einsum("nki,nk,nk->ni",design,h,ring_weights)
            gram+=np.eye(6)[None]*1e-6
            coefficients=np.linalg.solve(gram,rhs[:,:,None])[:,:,0]
            fitted=np.einsum("nki,ni->nk",design,coefficients)
            rms=np.sqrt(np.maximum(0,np.sum(ring_weights*(h-fitted)**2,axis=1)))
            ring_centroid=np.sum(normalized*ring_weights[:,:,None],axis=1)
            ring_centered=normalized-ring_centroid[:,None]
            ring_cov=np.einsum("nki,nkj,nk->nij",ring_centered,ring_centered,ring_weights)
            _,eigenvectors=np.linalg.eigh(ring_cov)
            plane_normal=eigenvectors[:,:,0]
            signs=np.where(np.einsum("ni,ni->n",plane_normal,query_normals)>=0,1.,-1.)
            # eigenvectors are in the original 3D axes used by normalized offsets.
            plane_residual=-np.einsum("ni,ni->n",ring_centroid,plane_normal)*signs
            values=np.stack((mean_h,std_h,h.min(axis=1),h.max(axis=1),np.quantile(h,.25,axis=1),np.quantile(h,.75,axis=1),
                np.sum(weights*np.abs(h),axis=1),mean_dot,std_dot,nd.min(axis=1),normalized_eigenvalues[:,0],normalized_eigenvalues[:,1],
                -coefficients[:,-1],rms,plane_residual,np.log(radius/spacing)),axis=1)
            descriptor.append(values)
    features=np.stack(descriptor,axis=1)
    finite=np.isfinite(features).all(axis=(1,2))
    valid&=finite
    features[~finite]=0
    baseline=np.max(np.abs(features[:,:,12]),axis=1)
    return dict(features=features.astype(np.float32),source_ids=F.astype(np.int64),valid_mask=valid,area=area[F],baseline_score=baseline,
                neighbor_ids=neighbor_ids.astype(np.int32),scale_radii=np.stack(radii,axis=1),ring_counts=np.stack(ring_counts,axis=1),timings=timings)


def main():
    started,cpu=time.perf_counter(),time.process_time()
    if (HERE/"FEATURES.json").exists():
        raise RuntimeError("shared_feature_preparation_already_exists")
    plan=read("PLAN.json")
    rows=[]
    folder=HERE/"private/features"
    folder.mkdir(parents=True,exist_ok=True)
    for index,case in enumerate(read("INPUT_INDEX.json")["cases"]):
        local={}
        with measure(local,"current_packet_read"):
            if identity(HERE/case["input"]["path"])["sha256"]!=case["input"]["sha256"]:
                raise ValueError("current_input_packet_changed")
            with np.load(HERE/case["input"]["path"]) as package:
                vertices,faces,F=package["vertices"],package["faces"],package["F_source_ids"].astype(np.int64)
        values=describe_current(vertices,faces,F,tuple(plan["candidate"]["neighbor_counts"]))
        neighbor_ids=values.pop("neighbor_ids")
        feature_timings=values.pop("timings")
        path=folder/(case["alias"]+".npz")
        with measure(local,"descriptor_cache_write"):
            np.savez_compressed(path,**values)
        # Neighbor identities are input-derived, stored separately for posthoc coverage without labels entering the selector.
        context=folder/(case["alias"]+"_context.npz")
        np.savez_compressed(context,neighbor_ids=neighbor_ids)
        row=dict(alias=case["alias"],split=case["split"],roi_alias=case["roi_alias"],valid_for_learning=case["valid_for_learning"],
                 **identity(path),context=identity(context),points=len(F),valid_points=int(values["valid_mask"].sum()),
                 timings={**local,**feature_timings},minimum_ring_points=int(values["ring_counts"].min()))
        rows.append(row)
        if (index+1)%50==0:
            print("prepared",index+1,"/600",flush=True)
    write("FEATURES.json",dict(status="completed_current_only_multiscale_features",cases=rows,channels=plan["candidate"]["channels"],
        shape_per_case=[384,5,16],supervision_arrays_read=0,network_forwards=0,
        input_contract="current full vertices/topology/F_source_ids only. All five scales reuse one neighbor table. No source names, reference coordinates or generation parameters enter features",
        limitations="Euclidean neighbors can cross nearby sheets, posthoc damaged-support coverage is separate from selection",
        wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu))
    print("features complete",len(rows),flush=True)


if __name__=="__main__":
    main()
