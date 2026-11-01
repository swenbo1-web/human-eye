"""Trusted same-index reference bindings; signed source-metric deviations.

Only a local Python owner binds an intended reference. A model reference id is
a lookup, not correspondence proof, approval, or write authority. No persistence
or inference of intended shape from a damaged mesh.
"""
from dataclasses import dataclass
from fractions import Fraction as Q
import copy,math,uuid
from . import surface_geometry as g


@dataclass(frozen=True)
class ReferenceIntent:
    provenance: str
    semantic_target: str
    correspondence: str


class ReferenceRegistry:
    def __init__(self):self._bindings={};self._revoked=set()

    def bind(self,reference,target,triangles,polygon_indices,*,intent):
        g.require(type(intent) is ReferenceIntent and all(type(v) is str and 1<=len(v)<=256 for v in
            (intent.provenance,intent.semantic_target,intent.correspondence)),'trusted_reference_intent')
        g.require(intent.correspondence=='same_index_from_owned_copy','correspondence_not_established')
        g.require(len(self._bindings)<16,'reference_registry_full')
        _compatible(reference,target)
        from .mesh_structure import WorkBudget
        g.validate_tessellation(reference['raw'],triangles,polygon_indices,WorkBudget())
        ref=uuid.uuid4().hex
        self._bindings[ref]=copy.deepcopy(dict(reference=reference,target_identity={k:target['source'][k]
            for k in ('object_id','object_instance','document_epoch')},triangles=triangles,polygon_indices=polygon_indices,
            intent=dict(provenance=intent.provenance,semantic_target=intent.semantic_target,correspondence=intent.correspondence)))
        return ref

    def revoke(self,ref):
        g.require(ref in self._bindings,'unknown_reference');self._revoked.add(ref)

    def resolve(self,ref,target):
        g.require(ref in self._bindings and ref not in self._revoked,'unknown_or_revoked_reference')
        value=self._bindings[ref]
        g.require(all(target['source'][k]==v for k,v in value['target_identity'].items()),'reference_target_incarnation')
        _compatible(value['reference'],target)
        return copy.deepcopy(value)


def _compatible(reference,target):
    a,b=reference['raw'],target['raw']
    g.require(len(a['vertices'])==len(b['vertices']) and a['edges']==b['edges'] and a['polygons']==b['polygons'],'reference_topology_or_index_mismatch')
    g.require(a['matrix_world']==b['matrix_world'] and a['unit_scale']==b['unit_scale'],'reference_frame_or_scale_mismatch')


def diagnose(binding,target,*,budget,threshold_m=.0001):
    g.require(type(threshold_m) in (int,float) and math.isfinite(threshold_m) and 0<threshold_m<=.01,'deviation_threshold')
    reference=binding['reference'];_compatible(reference,target)
    raw=reference['raw'];matrix=[[Q(x) for x in row] for row in raw['matrix_world']];scale=Q(raw['unit_scale'])
    g.require(g.dot(matrix[0][:3],g.cross(matrix[1][:3],matrix[2][:3]))!=0,'singular_metric_frame')
    def vector(p):return tuple(sum(matrix[r][c]*Q(p[c]) for c in range(3))*scale for r in range(3))
    # Translation cancels before arithmetic; far-origin precision is not borrowed
    # from Blender's binary32 world coordinates.
    points=[vector(p) for p in raw['vertices']];normals=[(Q(0),)*3 for _ in points];incident=[[] for _ in points]
    for tri in binding['triangles']:
        budget.consume(8,'reference_normals');n=g.normal([points[i] for i in tri])
        for i in tri:normals[i]=g.add(normals[i],n);incident[i].append(n)
    changed=[];unknown=[];changed_unknown=[];rows=[];threshold=Q(threshold_m)**2
    for i,(a,b,n) in enumerate(zip(raw['vertices'],target['raw']['vertices'],normals)):
        budget.consume(8+len(incident[i]),'reference_deviation');nn=g.dot(n,n)
        # Weighted normals at reversed, degenerate or >60deg creases cannot
        # support a unique local normal displacement claim.
        reliable=nn>0 and all(g.dot(v,v)>0 and g.dot(v,n)>0 and 4*g.dot(v,n)**2>=g.dot(v,v)*nn for v in incident[i])
        if not reliable:unknown.append(i)
        delta=vector([Q(y)-Q(x) for x,y in zip(a,b)]);dd=g.dot(delta,delta);dn=g.dot(delta,n)
        normal2=dn*dn/nn if reliable else None;tangent2=dd-normal2 if reliable else None
        if dd>threshold:
            changed.append(i)
            if not reliable:changed_unknown.append(i)
            if len(rows)<128:rows.append(dict(vertex=i,signed_normal_m=((1 if dn>0 else -1)*math.sqrt(float(normal2)) if dn else 0.) if reliable else None,
                tangential_m=math.sqrt(float(tangent2)) if reliable else None,displacement_m=math.sqrt(float(dd)),
                normal_status='reliable_reference_area_weighted' if reliable else 'unknown_reference_normal'))
    adjacency={v:[] for v in changed};chosen=set(changed)
    for a,b in raw['edges']:
        budget.consume(1,'reference_clusters')
        if a in chosen and b in chosen:adjacency[a].append(b);adjacency[b].append(a)
    remaining=set(changed);clusters=[];cluster_count=0
    for seed in changed:
        if seed not in remaining:continue
        remaining.remove(seed);stack=[seed];members=[]
        while stack:
            i=stack.pop();members.append(i);budget.consume(1+len(adjacency[i]),'reference_walk')
            for j in adjacency[i]:
                if j in remaining:remaining.remove(j);stack.append(j)
        cluster_count+=1
        if len(clusters)<64:
            center=[float(sum(points[i][k] for i in members)/len(members)) for k in range(3)]
            clusters.append(dict(members=sorted(members)[:128],member_count=len(members),members_complete=len(members)<=128,
                reference_local_metric_center_m=center,frame='reference_linear_map_without_world_translation'))
    budget.check('reference_report')
    return dict(schema='surface-reference-deviation-v1',status='partial' if unknown else 'observed',source=target['source'],
        reference_source=reference['source'],intent=binding['intent'],threshold_m=threshold_m,
        changed_count=len(changed),delivered_count=len(rows),omitted_count=len(changed)-len(rows),vertices=rows,
        vector_displacement_scan_complete=True,signed_normal_complete=not changed_unknown,
        changed_with_unreliable_normal_count=len(changed_unknown),
        unreliable_normal_count=len(unknown),unreliable_vertices=unknown[:128],clusters=clusters,
        cluster_count=cluster_count,clusters_omitted=cluster_count-len(clusters),
        metric='exact_input_affine_displacement_then_float_display_not_renderer_precision',
        execution_authority=False,damage_classification='reference_deviation_not_semantic_damage',
        not_checked=['noncorresponding_assets','topology_change','rig_pose','intent_inference'])


def preview_restore(binding,target,indices,*,budget,max_displacement_m=.001):
    """A new finite vertex domain preview, never a rigid-body grant."""
    _compatible(binding['reference'],target)
    g.require(type(indices) is list and 1<=len(indices)<=64 and len(set(indices))==len(indices)
        and all(type(i) is int and 0<=i<len(target['raw']['vertices']) for i in indices),'repair_patch_indices')
    g.require(type(max_displacement_m) in (int,float) and math.isfinite(max_displacement_m)
        and 0<max_displacement_m<=.01,'repair_displacement_budget')
    predicted=copy.deepcopy(target);raw=predicted['raw'];reference=binding['reference']['raw'];chosen=set(indices)
    matrix=[[Q(x) for x in row] for row in raw['matrix_world']];scale=Q(raw['unit_scale'])
    for i in indices:
        budget.consume(8,'repair_preview');d=[Q(y)-Q(x) for x,y in zip(raw['vertices'][i],reference['vertices'][i])]
        delta=[sum(matrix[r][c]*d[c] for c in range(3))*scale for r in range(3)]
        g.require(sum(x*x for x in delta)<=Q(max_displacement_m)**2,'repair_displacement_exceeded')
        raw['vertices'][i]=reference['vertices'][i][:]
    # Reject degenerate or flipped affected triangles; checks are against the
    # approved reference, not the damaged current orientation.
    for tri in binding['triangles']:
        budget.consume(2,'repair_orientation')
        if not chosen.intersection(tri):continue
        a=g.normal([tuple(Q(x) for x in reference['vertices'][i]) for i in tri]);b=g.normal([tuple(Q(x) for x in raw['vertices'][i]) for i in tri])
        g.require(g.dot(a,b)>0,'repair_orientation_or_area')
    budget.check('repair_preview_complete')
    return dict(schema='surface-reference-restore-preview-v1',target_source=target['source'],reference_source=binding['reference']['source'],
        indices=sorted(indices),protected_vertex_count=len(raw['vertices'])-len(indices),max_displacement_m=max_displacement_m,
        proposed_local_vertices=[raw['vertices'][i] for i in sorted(indices)],
        proposed_raw_sha256=g.digest(raw),execution_authority=False,executed=False,
        write_domain_support='original_triangles_only' if all(len(p)==3 for p in raw['polygons']) else 'not_eligible_original_ngons',
        status='preview_only',not_checked=['new_self_contacts','actual_setter_and_recovery','authorization_for_vertex_write'])


def make_view_patch(binding,target,report,cluster_ordinal,reference_ref,*,budget):
    """Owner-derived feature only; never accept geometry or ROI from a model."""
    _compatible(binding['reference'],target)
    g.require(type(cluster_ordinal) is int and 0<=cluster_ordinal<len(report['clusters']),'view_cluster')
    cluster=report['clusters'][cluster_ordinal];members=cluster['members']
    g.require(cluster['members_complete'] and 1<=len(members)==cluster['member_count']<=64,'view_complete_members')
    r=binding['reference']['raw'];current=target['raw'];matrix=[[Q(x) for x in row] for row in r['matrix_world']];scale=Q(r['unit_scale'])
    def vector(p):return tuple(sum(matrix[k][j]*Q(p[j]) for j in range(3))*scale for k in range(3))
    vertices=[vector(p) for p in r['vertices']]
    deltas=[vector([Q(y)-Q(x) for x,y in zip(a,b)]) for a,b in zip(r['vertices'],current['vertices'])]
    selected=set(members);candidates=[];normal=(Q(0),)*3
    for i,tri in enumerate(binding['triangles']):
        budget.consume(8,'reference_view_witnesses')
        if not selected.intersection(tri):continue
        n=g.normal([vertices[v] for v in tri]);normal=g.add(normal,n)
        delta=tuple(sum(deltas[v][k] for v in tri)/3 for k in range(3));size=g.dot(delta,delta)
        if size<Q(report['threshold_m'])**2:continue
        center=tuple(sum(vertices[v][k]+deltas[v][k] for v in tri)/3 for k in range(3))
        candidates.append((size,i,delta,center))
    g.require(any(normal) and len(candidates)>=2,'view_witnesses_unavailable')
    largest=max(c[0] for c in candidates);candidates=[c for c in candidates if 4*c[0]>=largest]
    chosen=[max(candidates,key=lambda c:(c[0],-c[1]))]
    while len(chosen)<min(3,len(candidates)):
        candidates_left=[c for c in candidates if c[1] not in {v[1] for v in chosen}]
        chosen.append(max(candidates_left,key=lambda c:(min(g.dot(g.sub(c[3],v[3]),g.sub(c[3],v[3])) for v in chosen),c[0],-c[1])))
    source=target['source'];normal_length=math.sqrt(float(g.dot(normal,normal)))
    g.require(math.isfinite(normal_length) and normal_length>0,'view_normal_unavailable')
    patch=dict(schema='reference-feature-patch-v1',**{k:source[k] for k in ('object_id','object_instance','document_epoch','raw_sha256')},
        reference_raw_sha256=binding['reference']['source']['raw_sha256'],reference_ref=reference_ref,threshold_m=report['threshold_m'],
        tessellation_sha256=g.digest(dict(triangles=binding['triangles'],polygon_indices=binding['polygon_indices'])),
        members=members[:],witnesses=[dict(triangle=c[1],reference_offset_m=[float(x) for x in c[2]]) for c in chosen],
        reference_normal=[float(x)/normal_length for x in normal])
    g.require(len(g.encoded(patch))<=3000,'view_patch_bytes');budget.check('reference_view_patch_complete')
    return patch
