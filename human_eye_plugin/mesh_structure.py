"""Bounded static raw-mesh facts. No triangulation, repair or action authority.

Dependency-free so the exact same source can run inside Blender's typed host.
Surface links, finite degeneracy predicates and source-bound positions extend
the first three facts. A boundary is not a damage or visibility diagnosis.
"""
from __future__ import annotations
import hashlib
import json
import math
import time
import uuid
from fractions import Fraction

PROTOCOL = 'raw-mesh-structure-v2'
DEFAULT_CATEGORIES = ('boundary_edges', 'loose_edges', 'isolated_vertices')
SUPPORTED = DEFAULT_CATEGORIES + ('nonmanifold_edges','nonmanifold_vertices','degenerate_polygons')
EDGE_CATEGORIES = frozenset(('boundary_edges','loose_edges','nonmanifold_edges'))
VERTEX_CATEGORIES = frozenset(('isolated_vertices','nonmanifold_vertices'))
ALGORITHM = {'revision':'raw-topology-link-degeneracy-v1',
    'vertex_link':'connected_multigraph_cycle_or_path_with_surface_wire_nodes',
    'duplicate_face_link':'unclassified_incident_vertices',
    'degeneracy':'exact_collinearity_or_relative_near_triangle; other_ngons_simple_exactly_planar_max64',
    'triangle_relative_squared_threshold':'2^-80',
    'near_ngon_quality':'not_checked',
    'positions':'binary64_forward_map_metres_not_certified_error_bound'}
CATEGORIES = ('boundary_edges','nonmanifold_edges','nonmanifold_vertices',
    'isolated_vertices','loose_edges','duplicate_positions','degenerate_polygons',
    'duplicate_polygons','winding_conflicts')
UNEXAMINED = ('self_intersection','near_coincident_surfaces','surface_damage','rig_pose','skin_deformation')
LIMITS = {'vertices':16384,'edges':32768,'polygons':16384,'corners':65536,
          'source_bytes':4*1024*1024,'report_bytes':64*1024,
          'work_units':262144,'regions':128,'members_per_region':64}


class StructureRefused(ValueError):
    """Invalid/unsupported source; never a clean bill of geometry health."""


class StructureStopped(ValueError):
    pass


def _require(condition, reason):
    if not condition:raise StructureRefused(reason)


def _integer(value, low=0, high=2**53):
    return type(value) is int and low <= value <= high


def _identifier(value):
    return type(value) is str and 0 < len(value) <= 256 and bool(value.strip())


def _finite(value):
    try:return type(value) in (int,float) and math.isfinite(value)
    except OverflowError:return False


def _bytes(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,
                          allow_nan=False).encode('utf8')
    except (ValueError,TypeError,UnicodeError,OverflowError,RecursionError) as exc:
        raise StructureRefused('invalid_structure_json') from exc


def _digest(value):return hashlib.sha256(_bytes(value)).hexdigest()


class WorkBudget:
    """Cooperative checks, not OS preemption or a cross-request task ledger."""
    def __init__(self, *, deadline_ns=None, max_work=262144, clock=time.perf_counter_ns):
        _require(callable(clock) and _integer(max_work,0,LIMITS['work_units']), 'invalid_work_budget')
        self.clock=clock;now=clock()
        self.deadline_ns=now+30_000_000_000 if deadline_ns is None else deadline_ns
        _require(_integer(self.deadline_ns,0,2**63-1) and self.deadline_ns<=now+30_000_000_000,
                 'invalid_original_deadline')
        self.maximum=max_work;self.used=0;self.stage='admission'
        self.check()

    def check(self, stage=None):
        if stage is not None:self.stage=stage
        if self.clock() >= self.deadline_ns:raise StructureStopped('deadline_exhausted')

    def consume(self, count=1, stage=None):
        self.check(stage)
        if self.used+count>self.maximum:raise StructureStopped('work_budget_exhausted')
        self.used+=count


def _counts(raw):
    _require(type(raw) is dict and set(raw)=={'vertices','edges','polygons','matrix_world','unit_scale'},
             'raw_fields')
    for name in ('vertices','edges','polygons'):
        _require(type(raw[name]) is list and len(raw[name])<=LIMITS[name], 'raw_'+name+'_budget')
    # Bound every polygon before summing or allocating connectivity.
    corners=0
    for polygon in raw['polygons']:
        _require(type(polygon) is list and 3<=len(polygon)<=LIMITS['corners'], 'raw_polygon_arity')
        corners+=len(polygon)
        _require(corners<=LIMITS['corners'],'raw_corner_budget')
    return dict(vertices=len(raw['vertices']),edges=len(raw['edges']),
                polygons=len(raw['polygons']),corners=corners)


def _metadata(value):
    _require(type(value) is dict and set(value)=={'object_id','object_instance','document_epoch','capture_id'},
             'identity_fields')
    _require(all(_identifier(v) for v in value.values()),'source_identity_required')


def prepare_raw(raw, identity, *, budget=None):
    """Detach and validate source indices before building any geometry arrays.

    The source values stay in Blender local units; scale/matrix are committed by
    the digest. The public metre-local source keeps indices exactly unchanged.
    """
    budget=budget or WorkBudget();budget.check('raw_admission');_metadata(identity)
    counts=_counts(raw);scale=raw['unit_scale'];matrix=raw['matrix_world']
    _require(_finite(scale) and scale>0, 'invalid_unit_scale')
    _require(type(matrix) is list and len(matrix)==4 and all(type(r) is list and len(r)==4
             and all(_finite(x) for x in r) for r in matrix) and matrix[3]==[0,0,0,1], 'invalid_affine_matrix')
    detached={'vertices':[],'edges':[],'polygons':[],
              'matrix_world':[r[:] for r in matrix],'unit_scale':scale}
    vertex_count=counts['vertices'];edge_lookup={};used_vertices=bytearray(vertex_count)
    edge_use=[0]*counts['edges']
    for start in range(0,vertex_count,256):
        budget.consume(min(256,vertex_count-start),'validate_vertices')
        for vertex in raw['vertices'][start:start+256]:
            _require(type(vertex) is list and len(vertex)==3, 'invalid_vertex')
            for v in vertex:
                _require(_finite(v),'invalid_vertex')
                _require(math.isfinite(v*scale),'metre_coordinate_overflow')
            detached['vertices'].append(vertex[:])
    for start in range(0,counts['edges'],256):
        budget.consume(min(256,counts['edges']-start),'validate_edges')
        for offset,edge in enumerate(raw['edges'][start:start+256],start):
            _require(type(edge) is list and len(edge)==2,'invalid_source_edge')
            a,b=edge
            _require(type(a) is int and type(b) is int and 0<=a<vertex_count
                     and 0<=b<vertex_count and a!=b,'invalid_source_edge')
            key=(a,b) if a<b else (b,a)
            _require(key not in edge_lookup,'ambiguous_duplicate_source_edge')
            edge_lookup[key]=offset;detached['edges'].append(edge[:])
            used_vertices[edge[0]]=used_vertices[edge[1]]=1
    # Repeated-index polygons remain visible as unsupported source, not repaired
    # or counted twice. A later degenerate-polygon capability can extend this.
    for start in range(0,counts['polygons'],256):
        batch=raw['polygons'][start:start+256]
        budget.consume(sum(len(p)+1 for p in batch),'validate_polygon_incidence')
        for polygon in batch:
            previous=polygon[-1]
            _require(type(previous) is int and 0<=previous<vertex_count,'invalid_polygon_index')
            seen=set()
            for v in polygon:
                _require(type(v) is int and 0<=v<vertex_count,'invalid_polygon_index')
                _require(v not in seen,'repeated_polygon_vertex_unsupported');seen.add(v)
                key=(previous,v) if previous<v else (v,previous)
                edge_index=edge_lookup.get(key)
                _require(edge_index is not None,'polygon_source_edge_missing')
                edge_use[edge_index]+=1;previous=v
            detached['polygons'].append(polygon[:])
    budget.check('source_encode')
    committed={'identity':{k:v for k,v in identity.items() if k!='capture_id'},'raw':detached}
    encoded=_bytes(committed);_require(len(encoded)<=LIMITS['source_bytes'],'source_byte_budget')
    budget.check('source_encoded')
    source={**identity,'raw_sha256':hashlib.sha256(encoded).hexdigest(),'source_kind':'raw_mesh',
            'coordinate_frame':'local','length_unit':'m','counts':counts,
            'capture_scope':'target_mesh_only','geometry_complete':True}
    return {'source':source,'raw':detached,'edge_lookup':edge_lookup,
            'used_vertices':used_vertices,'edge_use':edge_use,'encoded_source_bytes':len(encoded)}


def _empty_check(state, counts, reason):
    return dict(state=state,scanned={k:0 for k in counts},found=0,total=None,regions=[],
                omitted=0,reason=reason,omission_reason=None)


def _edge_components(indices, edges, budget):
    """Connected source-edge components without triangle or position welding."""
    incident={}
    for i in indices:
        budget.consume(1,'component_adjacency')
        for v in edges[i]:incident.setdefault(v,[]).append(i)
    remaining=set(indices);components=[]
    for seed in indices:
        if seed not in remaining:continue
        pending=[seed];remaining.remove(seed);component=[]
        while pending:
            i=pending.pop();component.append(i);budget.consume(1,'component_walk')
            for v in edges[i]:
                neighbours=incident.pop(v,())
                budget.consume(len(neighbours),'component_links')
                for other in neighbours:
                    if other in remaining:remaining.remove(other);pending.append(other)
        components.append(sorted(component))
    return components


def _vertex_components(selected, edges, budget):
    chosen=set(selected);adjacency={v:[] for v in selected}
    budget.consume(len(edges),'flagged_vertex_adjacency')
    for a,b in edges:
        if a in chosen and b in chosen:adjacency[a].append(b);adjacency[b].append(a)
    groups=[];remaining=set(selected)
    for seed in sorted(selected):
        if seed not in remaining:continue
        stack=[seed];remaining.remove(seed);group=[]
        while stack:
            v=stack.pop();group.append(v);budget.consume(1+len(adjacency[v]),'flagged_vertex_walk')
            for other in adjacency[v]:
                if other in remaining:remaining.remove(other);stack.append(other)
        groups.append(sorted(group))
    return groups


def _vertex_link_groups(prepared, budget):
    raw=prepared['raw'];links=[{} for _ in raw['vertices']];face_use=[0]*len(links)
    canonical={};ambiguous=set()
    for polygon in raw['polygons']:
        budget.consume(len(polygon),'vertex_link_build')
        first=polygon.index(min(polygon));cycle=polygon[first:]+polygon[:first]
        key=min(tuple(cycle),tuple([cycle[0]]+cycle[:0:-1]))
        if key in canonical:ambiguous.update(polygon)
        else:canonical[key]=True
        for i,v in enumerate(polygon):
            a,b=polygon[i-1],polygon[(i+1)%len(polygon)];graph=links[v]
            graph.setdefault(a,[]).append(b);graph.setdefault(b,[]).append(a);face_use[v]+=1
    budget.consume(len(raw['edges']),'vertex_link_wire_nodes')
    for a,b in raw['edges']:
        if face_use[a]:links[a].setdefault(b,[])
        if face_use[b]:links[b].setdefault(a,[])
    bad=[]
    for v,graph in enumerate(links):
        budget.consume(1,'vertex_link_classify')
        if not face_use[v] or v in ambiguous:continue
        budget.consume(len(graph),'vertex_link_degrees')
        degrees=[len(neighbours) for neighbours in graph.values()]
        admissible=all(d in (1,2) for d in degrees) and degrees.count(1) in (0,2)
        reached=set();pending=[next(iter(graph))]
        while pending:
            node=pending.pop()
            if node in reached:continue
            reached.add(node);budget.consume(1+len(graph[node]),'vertex_link_connectivity')
            pending.extend(other for other in graph[node] if other not in reached)
        if not admissible or len(reached)!=len(graph):bad.append(v)
    return _vertex_components(bad,raw['edges'],budget),sorted(ambiguous)


def _cross_exact(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _minus(a,b):return tuple(x-y for x,y in zip(a,b))
def _norm2(a):return sum(x*x for x in a)


def _degenerate_kind(polygon, raw, cache, budget):
    points=[]
    for v in polygon:
        budget.consume(1,'degenerate_exact_coordinate')
        if v not in cache:cache[v]=tuple(Fraction(x) for x in raw['vertices'][v])
        points.append(cache[v])
    origin=points[0];direction=next((_minus(p,origin) for p in points[1:] if p!=origin),None)
    if direction is None:return 'exact_zero',None
    normal=None
    for point in points[1:]:
        budget.consume(1,'degenerate_rank')
        candidate=_cross_exact(direction,_minus(point,origin))
        if any(candidate):normal=candidate;break
    if normal is None:return 'exact_zero',None
    if len(points)==3:
        cross=_cross_exact(_minus(points[1],origin),_minus(points[2],origin))
        longest=max(_norm2(_minus(points[i],points[j])) for i,j in ((0,1),(0,2),(1,2)))
        return ('relative_near' if _norm2(cross)*(1<<80)<=longest*longest else None),None
    if len(points)>64:return None,'ngon_predicate_arity_budget'
    for point in points:
        budget.consume(1,'ngon_planarity')
        if sum(a*b for a,b in zip(normal,_minus(point,origin)))!=0:return None,'nonplanar_ngon'
    drop=max(range(3),key=lambda i:abs(normal[i]));axes=[i for i in range(3) if i!=drop]
    projected=[(p[axes[0]],p[axes[1]]) for p in points]
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,p):return min(a[0],b[0])<=p[0]<=max(a[0],b[0]) and min(a[1],b[1])<=p[1]<=max(a[1],b[1])
    n=len(points)
    for i in range(n):
        a,b=projected[i],projected[(i+1)%n]
        if a==b:return None,'non_simple_ngon'
        # Adjacent sides may share their endpoint, but cannot double back along
        # the same segment. Non-adjacent tests alone do not establish simplicity.
        c=projected[(i+2)%n];budget.consume(1,'ngon_adjacent_edge_test')
        if orient(a,b,c)==0 and sum((a[k]-b[k])*(c[k]-b[k]) for k in (0,1))>0:
            return None,'non_simple_ngon'
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1):continue
            budget.consume(1,'ngon_nonadjacent_edge_test')
            c,d=projected[j],projected[(j+1)%n]
            ab_c,ab_d,cd_a,cd_b=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
            if (ab_c*ab_d<0 and cd_a*cd_b<0 or ab_c==0 and on(a,b,c)
                or ab_d==0 and on(a,b,d) or cd_a==0 and on(c,d,a) or cd_b==0 and on(c,d,b)):
                return None,'non_simple_ngon'
    return None,None


def _polygon_components(selected, prepared, budget):
    polygons=prepared['raw']['polygons'];lookup=prepared['edge_lookup'];incident={};members={}
    for p in selected:
        polygon=polygons[p];budget.consume(len(polygon),'degenerate_polygon_adjacency')
        edges=[lookup[tuple(sorted((polygon[i-1],v)))] for i,v in enumerate(polygon)]
        members[p]=edges
        for e in edges:incident.setdefault(e,[]).append(p)
    groups=[];remaining=set(selected)
    for seed in selected:
        if seed not in remaining:continue
        pending=[seed];remaining.remove(seed);group=[]
        while pending:
            p=pending.pop();group.append(p);budget.consume(1+len(members[p]),'degenerate_polygon_walk')
            for edge in members[p]:
                neighbours=incident.pop(edge,());budget.consume(len(neighbours),'degenerate_polygon_links')
                for other in neighbours:
                    if other in remaining:remaining.remove(other);pending.append(other)
        groups.append(sorted(group))
    return groups


def _degenerate_groups(prepared,budget):
    kinds={};unknown=[];reasons=set();cache={}
    for i,polygon in enumerate(prepared['raw']['polygons']):
        kind,reason=_degenerate_kind(polygon,prepared['raw'],cache,budget)
        if kind:kinds[i]=kind
        if reason:unknown.append(i);reasons.add(reason)
    return _polygon_components(list(kinds),prepared,budget),kinds,unknown,sorted(reasons)


def _patch_position(category,indices,raw,budget):
    try:
        if category in VERTEX_CATEGORIES:vertices=list(indices)
        else:
            table=raw['edges'] if category in EDGE_CATEGORIES else raw['polygons']
            vertices=[]
            for i in indices:
                budget.consume(len(table[i]),'patch_source_vertices');vertices.extend(table[i])
            vertices=sorted(set(vertices))
        local=[];world=[];scale=raw['unit_scale'];matrix=raw['matrix_world']
        for i in vertices:
            budget.consume(1,'patch_positions')
            point=raw['vertices'][i];a=[float(v*scale) for v in point]
            b=[float((sum(matrix[r][c]*point[c] for c in range(3))+matrix[r][3])*scale) for r in range(3)]
            if not all(math.isfinite(v) for v in a+b):return {'status':'unknown','reason':'position_nonfinite'}
            local.append(a);world.append(b)
        def bounds(points):return [[min(p[i] for p in points) for i in range(3)],
                                   [max(p[i] for p in points) for i in range(3)]]
        return {'status':'known','length_unit':'m','method':ALGORITHM['positions'],
                'scope':'all_source_vertices_of_reported_elements',
                'local_bounds_m':bounds(local),'world_bounds_m':bounds(world),
                'witness_vertex_index':vertices[0],'witness_local_m':local[0],'witness_world_m':world[0]}
    except StructureStopped as exc:return {'status':'unknown','reason':str(exc)}
    except (OverflowError,ValueError):return {'status':'unknown','reason':'position_nonfinite'}


def analyze_prepared(prepared, *, task_id, categories=DEFAULT_CATEGORIES, budget=None):
    """Internal prepared snapshot only; public untrusted input uses analyze_raw.

    Incomplete scans do not expose an unproven total or call the mesh normal.
    Coverage records describe the actual completed prefixes and scan stages.
    """
    budget=budget or WorkBudget()
    _require(_identifier(task_id),'task_id')
    _require(type(categories) in (tuple,list) and 1<=len(categories)<=len(SUPPORTED)
             and all(type(c) is str and c in SUPPORTED for c in categories)
             and len(set(categories))==len(categories),'unsupported_diagnostic_categories')
    source=prepared['source'];raw=prepared['raw'];counts=source['counts']
    checks={c:_empty_check('not_checked',counts,'not_started') for c in categories}
    coverage=dict(vertices_prefix=0,edges_prefix=0,polygons_prefix=0,polygon_corners=0,
                  component_categories_completed=[],unclassified={})
    patches=[];groups={};stop=None;degenerate_kinds={}
    try:
        # Reuse the exact incidence already checked during source validation;
        # rebuilding the same dictionary lookup per face corner costs another
        # full pass and cannot add evidence to this immutable local snapshot.
        uses=prepared['edge_use']
        coverage['polygons_prefix']=counts['polygons'];coverage['polygon_corners']=counts['corners']
        coverage['edges_prefix']=counts['edges'];coverage['vertices_prefix']=counts['vertices']
        for category in categories:
            budget.check(category)
            unknown=[];unknown_reasons=[]
            if category=='isolated_vertices':
                budget.consume(counts['vertices'],'isolated_vertices')
                members=[[i] for i,used in enumerate(prepared['used_vertices']) if not used]
            elif category=='nonmanifold_vertices':
                members,unknown=_vertex_link_groups(prepared,budget)
                if unknown:unknown_reasons=['duplicate_face_link_ambiguous']
            elif category=='degenerate_polygons':
                members,degenerate_kinds,unknown,unknown_reasons=_degenerate_groups(prepared,budget)
            else:
                budget.consume(counts['edges'],'edge_classification')
                wanted=1 if category=='boundary_edges' else 0
                selected=[i for i,degree in enumerate(uses)
                          if (degree>2 if category=='nonmanifold_edges' else degree==wanted)]
                members=_edge_components(selected,raw['edges'],budget)
            groups[category]=members
            if unknown:
                coverage['unclassified'][category]={'count':len(unknown),'source_indices':unknown[:64],'reasons':unknown_reasons}
            else:coverage['component_categories_completed'].append(category)
            checks[category]=dict(state='partial' if unknown else 'complete',scanned=counts.copy(),found=len(members),
                                  total=None if unknown else len(members),regions=[],omitted=len(members),
                                  reason='predicate_domain_incomplete' if unknown else None,
                                  omission_reason='output_budget' if members else None)
    except StructureStopped as exc:
        stop=str(exc)
        for category in categories:
            if category not in groups:
                checks[category]=_empty_check('partial',counts,stop)
                checks[category]['scanned']=dict(vertices=coverage['vertices_prefix'],edges=coverage['edges_prefix'],
                    polygons=coverage['polygons_prefix'],corners=coverage['polygon_corners'])
    report=dict(schema='mesh-structure-evidence-v1',
        task=dict(schema='spatial-readonly-task-v1',kind='mesh_structure',task_id=task_id,
                  object_ids=[source['object_id']],read_only=True,categories=list(categories)),
        source=source,checks=checks,
        not_checked=[c for c in CATEGORIES if c not in categories]+list(UNEXAMINED),
        execution_authority=False,natural_visibility='not_checked')
    # Budgeted output: whole components only; missing member lists are never
    # labelled complete localization. Keep source-bound category backreferences.
    slots=LIMITS['regions'];text_estimate=0;position_unknown=False
    for category,members in groups.items():
        record=checks[category]
        for ordinal,indices in enumerate(members):
            if len(indices)>LIMITS['members_per_region'] or not slots:continue
            region=[raw['edges'][i][:] for i in indices] if category in EDGE_CATEGORIES else indices
            kind='edge' if category in EDGE_CATEGORIES else ('vertex' if category in VERTEX_CATEGORIES else 'polygon')
            patch=dict(category=category,cluster_ordinal=ordinal,element_kind=kind,source_indices=indices,
                membership_sha256=_digest(indices),raw_sha256=source['raw_sha256'],
                object_instance=source['object_instance'],document_epoch=source['document_epoch'],
                classification=[degenerate_kinds[i] for i in indices] if category=='degenerate_polygons' else [],
                position=_patch_position(category,indices,raw,budget))
            cost=len(_bytes(region))+len(_bytes(patch))+4
            if text_estimate+cost>48*1024:continue
            text_estimate+=cost;slots-=1
            record['regions'].append(region);record['omitted']-=1
            patches.append(patch);position_unknown|=patch['position']['status']=='unknown'
        record['omission_reason']='output_budget' if record['omitted'] else None
    result=dict(protocol=PROTOCOL,algorithm=ALGORITHM.copy(),status='partial' if stop or position_unknown or coverage['unclassified'] else 'observed',report=report,patches=patches,
        coverage=coverage,omitted_reference=dict(object_id=source['object_id'],object_instance=source['object_instance'],
            document_epoch=source['document_epoch'],raw_sha256=source['raw_sha256'],
            query='repeat_structure_on_fresh_matching_raw_source',retrieval_endpoint_available=False),
        accounting=dict(work_units=budget.used,max_work_units=budget.maximum,
                        source_bytes=prepared['encoded_source_bytes'],deadline_ns=budget.deadline_ns,
                        deadline_scope='single_call_cooperative_checkpoints',task_wide_budget_enforced=False),
        execution_authority=False,images=[])
    encoded=_bytes(result)
    _require(len(encoded)<=LIMITS['report_bytes'],'diagnostic_output_byte_budget')
    # Stop at the final deadline too; do not turn a late computation into an
    # on-time success. The caller's original deadline remains in the result.
    if not stop and not position_unknown:
        budget.check('result_encoded')
    return result


def analyze_raw(raw, identity, *, task_id, categories=DEFAULT_CATEGORIES, budget=None):
    budget=budget or WorkBudget()
    return analyze_prepared(prepare_raw(raw,identity,budget=budget),task_id=task_id,
                            categories=categories,budget=budget)


def _host_header(host, obj):
    _require(getattr(obj,'type',None)=='MESH' and getattr(obj,'mode',None)=='OBJECT','static_mesh_object_mode_required')
    guards=host._guard_description(obj)
    _require(not any(guards[k] for k in ('parent','constraints','modifiers','animation','data_animation',
        'rigid_body','rigid_body_constraint','shape_keys','linked','edit_mode')),'static_raw_source_required')
    mesh=obj.data
    _require(getattr(mesh,'library',None) is None and getattr(obj,'instance_type','NONE')=='NONE'
             and not bool(getattr(obj,'is_instancer',False)),'local_uninstanced_raw_mesh_required')
    uid=getattr(mesh,'session_uid',None)
    _require(_integer(uid,1),'raw_datablock_incarnation_required')
    identity=host._identity_metadata([obj])
    _require(type(identity) is dict,'host_identity_required')
    scale=host._scale()
    matrix=[[float(v) for v in row] for row in obj.matrix_world]
    counts=dict(vertices=len(mesh.vertices),edges=len(mesh.edges),polygons=len(mesh.polygons),corners=len(mesh.loops))
    _require(all(_integer(counts[k],0,LIMITS[k]) for k in counts),'raw_geometry_budget')
    return dict(object_id=host.object_id(obj),object_instance=identity['object_instances'][host.object_id(obj)]+':'+str(uid),
                document_epoch=identity['document_epoch'],counts=counts,scale=scale,matrix=matrix,guards=guards)


def capture_raw(host, object_id, *, budget=None):
    """Use a trusted BlenderSceneHost on its main thread, only the named target.

    Synchronous Blender main-thread access excludes legal UI writers while
    reading. This is not a proof against native memory mutation by extensions.
    """
    budget=budget or WorkBudget();_require(_identifier(object_id),'target_object_id')
    host._main_thread()
    with host._lock:
        budget.check('resolve_raw_target')
        # Bounded namespace lookup without requiring every other scene asset to
        # qualify for rigid capture. A target-only result never proves visibility.
        _require(len(host.scene.objects)<=65536,'target_namespace_budget')
        obj=None
        for index,candidate in enumerate(host.scene.objects):
            if index%256==0:budget.check('resolve_raw_target')
            if host.object_id(candidate)==object_id:
                _require(obj is None,'ambiguous_target_identity');obj=candidate
        _require(obj is not None,'target_not_found')
        before=_host_header(host,obj);mesh=obj.data
        raw=dict(vertices=[],edges=[],polygons=[],matrix_world=before['matrix'],unit_scale=before['scale'])
        for name in ('vertices','edges','polygons'):
            values=getattr(mesh,name)
            for start in range(0,len(values),256):
                budget.consume(min(256,len(values)-start),'capture_'+name)
                for item in values[start:start+256]:
                    if name=='vertices':raw[name].append([float(v) for v in item.co])
                    else:raw[name].append([int(i) for i in item.vertices])
        budget.consume(before['counts']['corners'],'capture_corners')
        _require(_host_header(host,obj)==before,'raw_source_changed_during_capture')
        identity={k:before[k] for k in ('object_id','object_instance','document_epoch')}
        identity['capture_id']=uuid.uuid4().hex
        return prepare_raw(raw,identity,budget=budget)


def observe_raw(host, object_id, *, request_id, categories=DEFAULT_CATEGORIES, deadline_ns=None):
    budget=WorkBudget(deadline_ns=deadline_ns)
    prepared=capture_raw(host,object_id,budget=budget)
    return analyze_prepared(prepared,task_id=request_id,categories=categories,budget=budget)
