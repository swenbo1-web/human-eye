"""Independent exact topology, occlusion and conservative pixel qualification.

This file imports no product module and performs no rasterization. Camera
equations are the preregistered source specification. All geometric decisions
use rational arithmetic. Binary64 interval arithmetic includes every modeled
camera arithmetic stage and an independent barycentric acceptance envelope.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import json
from math import gcd, isqrt, lcm
from pathlib import Path


VIEWS = {
    "SCENE": (4, -4, 3), "TOP": (0, 0, 1),
    "LEFT": (-1, 0, 1), "RIGHT": (1, 0, 1),
    "FRONT": (0, -1, 1), "BACK": (0, 1, 1),
}
U = F(1, 2**53)
GRID = 2**96
PIXEL_ENVELOPE = F(1, 2**16)


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), F(0))


def cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def ceil(q):
    return -((-q.numerator) // q.denominator)


def floor(q):
    return q.numerator // q.denominator


def rational_vector(v):
    return tuple(F(x) for x in v)


def primitive(v):
    denominator = lcm(*(x.denominator for x in v))
    values = tuple(int(x * denominator) for x in v)
    divisor = gcd(*values)
    if not divisor:
        raise ValueError("zero normal")
    return tuple(x // divisor for x in values)


def pin(path):
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def rational_json(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, tuple):
        return [rational_json(x) for x in value]
    if isinstance(value, list):
        return [rational_json(x) for x in value]
    if isinstance(value, dict):
        return {str(k): rational_json(v) for k, v in value.items()}
    return value


class Interval:
    """Outward dyadic interval with a binary64 rounding allowance per op.

    Endpoint quantization expands to a 2^-96 grid. The relative error bound
    u/(1-u), plus a subnormal absolute term, covers round-to-nearest arithmetic.
    Dot products use a gamma bound independent of sum ordering/FMA contraction.
    """
    __slots__ = ("lo", "hi")

    def __init__(self, lo, hi=None):
        self.lo = F(lo)
        self.hi = self.lo if hi is None else F(hi)
        if self.lo > self.hi:
            raise ValueError("inverted interval")

    @classmethod
    def rounded(cls, lo, hi):
        error = max(abs(lo), abs(hi)) * U / (1-U) + F(1, 2**1074)
        return cls(F(floor((lo-error)*GRID), GRID), F(ceil((hi+error)*GRID), GRID))

    @staticmethod
    def coerce(value):
        return value if isinstance(value, Interval) else Interval(value)

    def __add__(self, other):
        other = self.coerce(other)
        return self.rounded(self.lo+other.lo, self.hi+other.hi)

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def __sub__(self, other):
        return self + (-self.coerce(other))

    def __mul__(self, other):
        other = self.coerce(other)
        products = [a*b for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return self.rounded(min(products), max(products))

    def __truediv__(self, other):
        other = self.coerce(other)
        if other.lo <= 0 <= other.hi:
            raise ValueError("interval division by zero")
        quotients = [a/b for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return self.rounded(min(quotients), max(quotients))

    def sqrt(self):
        if self.lo < 0:
            raise ValueError("negative square root")
        low_int = isqrt(floor(self.lo*GRID*GRID))
        high_int = isqrt(floor(self.hi*GRID*GRID)) + 1
        return self.rounded(F(low_int,GRID), F(high_int,GRID))

    def abs(self):
        lower = 0 if self.lo <= 0 <= self.hi else min(abs(self.lo),abs(self.hi))
        return Interval(lower, max(abs(self.lo),abs(self.hi)))

    def pair(self):
        return [self.lo,self.hi]


def idot(a, b):
    products = [Interval.coerce(x)*Interval.coerce(y) for x,y in zip(a,b)]
    lower, upper = sum(x.lo for x in products), sum(x.hi for x in products)
    magnitude = sum(max(abs(x.lo),abs(x.hi)) for x in products)
    gamma = 4*U/(1-4*U)
    allowance = gamma*magnitude + F(4,2**1074)
    return Interval(F(floor((lower-allowance)*GRID),GRID), F(ceil((upper+allowance)*GRID),GRID))


def icross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def inormalize(vector):
    length = idot(vector,vector).sqrt()
    return tuple(x/length for x in vector)


def imax(intervals):
    return Interval(max(x.lo for x in intervals),max(x.hi for x in intervals))


def camera_intervals(vertices, direction, center):
    """Independently propagate the declared camera construction arithmetic."""
    d = inormalize(tuple(Interval(x) for x in direction))
    seed = tuple(Interval(x) for x in ((0,1,0) if direction == (0,0,1) else (0,0,1)))
    right = inormalize(icross(tuple(-x for x in d),seed))
    up = icross(right,tuple(-x for x in d))
    relative = [tuple(Interval(p)-Interval(c) for p,c in zip(vertex,center)) for vertex in vertices]
    h0 = imax([idot(p,axis).abs() for p in relative for axis in (right,up)])
    margin = Interval(1) + Interval(2)*Interval(F.from_float(.05))
    half_span = h0*margin
    span = Interval(2)*half_span
    front = imax([idot(p,d) for p in relative])
    distance = imax([Interval(F.from_float(.1)),front+Interval(F.from_float(.1)),span])
    eye = tuple(Interval(c)+axis*distance for c,axis in zip(center,d))
    forward = inormalize(tuple(Interval(c)-e for c,e in zip(center,eye)))
    published_right = inormalize(icross(forward,seed))
    published_up = icross(published_right,forward)
    translations = tuple(-idot(axis,eye) for axis in (published_right,published_up))
    projection_scale = Interval(1)/half_span
    return {
        "right":published_right,"up":published_up,"translation":translations,
        "scale":projection_scale,"half_span":half_span,"unpadded_half_span":h0,
    }


def screen_point(vertex, camera):
    point = tuple(Interval(x) for x in vertex)
    output = []
    for axis_index,axis in enumerate((camera["right"],camera["up"])):
        view_coordinate = idot(point,axis) + camera["translation"][axis_index]
        ndc = view_coordinate*camera["scale"]
        coordinate = (ndc+Interval(1)) if axis_index == 0 else (Interval(1)-ndc)
        output.append(coordinate*Interval(511)/Interval(2))
    return output


def component_analysis(name, vertices, triangles):
    normals, planes = [], []
    edges = defaultdict(list)
    for index,face in enumerate(triangles):
        if len(face)!=3 or len(set(face))!=3 or any(i<0 or i>=len(vertices) for i in face):
            raise ValueError("invalid triangle")
        a,b,c = (vertices[i] for i in face)
        normal = primitive(cross(sub(b,a),sub(c,a)))
        normals.append(normal)
        planes.append((normal,dot(a,normal)))
        for i,j in zip(face,face[1:]+face[:1]):
            edges[tuple(sorted((i,j)))].append((index,i,j))
    if any(len(rows)>2 for rows in edges.values()):
        raise ValueError("nonmanifold source edge")
    adjacent = defaultdict(set)
    for rows in edges.values():
        if len(rows)==2:
            (a,i,j),(b,k,l) = rows
            if planes[a]==planes[b]:
                if (i,j)!=(l,k):
                    raise ValueError("inconsistent coplanar winding")
                adjacent[a].add(b)
                adjacent[b].add(a)
    remaining = set(range(len(triangles)))
    result = []
    while remaining:
        seed = min(remaining)
        stack, group = [seed],set()
        while stack:
            index = stack.pop()
            if index in group:
                continue
            group.add(index)
            stack.extend(adjacent[index]-group)
        remaining -= group
        boundary = []
        vector_area = [F(0),F(0),F(0)]
        for index in sorted(group):
            face = triangles[index]
            a,b,c = (vertices[i] for i in face)
            face_cross = cross(sub(b,a),sub(c,a))
            vector_area = [x+y/2 for x,y in zip(vector_area,face_cross)]
            for i,j in zip(face,face[1:]+face[:1]):
                if sum(row[0] in group for row in edges[tuple(sorted((i,j)))])==1:
                    boundary.append((i,j))
        outgoing = dict(boundary)
        if len(outgoing)!=len(boundary) or Counter(j for _,j in boundary)!=Counter(i for i,_ in boundary):
            raise ValueError("invalid boundary cycle")
        unvisited = set(outgoing)
        loops = []
        while unvisited:
            initial = min(unvisited)
            loop, current = [],initial
            while current not in loop:
                loop.append(current)
                unvisited.remove(current)
                current = outgoing[current]
            if current!=initial:
                raise ValueError("nonclosing boundary")
            changed = True
            while changed and len(loop)>3:
                changed = False
                for i in range(len(loop)):
                    p,q,r = (vertices[loop[j%len(loop)]] for j in (i-1,i,i+1))
                    if cross(sub(q,p),sub(r,q))==(0,0,0) and dot(sub(q,p),sub(r,q))>0:
                        del loop[i]
                        changed = True
                        break
            loops.append(loop)
        rectangular = False
        if len(loops)==1 and len(loops[0])==4:
            corners = [vertices[i] for i in loops[0]]
            sides = [sub(corners[(i+1)%4],corners[i]) for i in range(4)]
            rectangular = (sides[0]==tuple(-x for x in sides[2]) and
                           sides[1]==tuple(-x for x in sides[3]) and dot(sides[0],sides[1])==0)
            if rectangular and dot(vector_area,vector_area)!=dot(sides[0],sides[0])*dot(sides[1],sides[1]):
                raise ValueError("rectangle area/topology mismatch")
        area_squared = dot(vector_area,vector_area)
        nx,ny,nz = normals[seed]
        area_in_domain = F(1,128)**2 <= area_squared <= F(1,32)**2
        normal_in_domain = nz>0 and 16*nz*nz>=9*(nx*nx+ny*ny+nz*nz)
        used_vertices = sorted({i for index in group for i in triangles[index]})
        bounds = [[min(vertices[i][axis] for i in used_vertices) for axis in range(3)],
                  [max(vertices[i][axis] for i in used_vertices) for axis in range(3)]]
        result.append({
            "object_name":name,"source_triangle_indices":sorted(group),"vertex_indices":used_vertices,
            "plane_normal_integer":list(normals[seed]),"plane_offset":planes[seed][1],
            "boundary_loops":loops,"rectangle_supported":rectangular,"area_squared_m4":area_squared,
            "area_in_domain":area_in_domain,"normal_nz_in_domain":normal_in_domain,
            "eligible":rectangular and area_in_domain and normal_in_domain,"bounds_world_m":bounds,
            "center_world_m":[(a+b)/2 for a,b in zip(*bounds)],
        })
    return result


def barycentric_envelope():
    """A priori error bound for accepted samples around these tiny triangles.

    After the camera interval proof, width <2 and screen coordinates in [0,512]
    imply that all sampled subtraction operands differ by <=4. Exact triangle
    determinants exceed 1/2. Each subtraction error <=512u/(1-u). Products and
    determinant/subsequent division bounds below are explicit rational bounds.
    The envelope includes the existing -1e-10 acceptance and w2=1-w0-w1.
    """
    subtraction_error = 512*U/(1-U)
    product_error = 8*subtraction_error+subtraction_error**2 + (16+8*subtraction_error+subtraction_error**2)*U/(1-U)
    determinant_error = 2*product_error+(32+2*product_error)*U/(1-U)
    denominator_lower = F(1,2)-determinant_error
    division_error = determinant_error/F(1,2)+(32+determinant_error)*determinant_error/(F(1,2)*denominator_lower)
    division_error += (32+determinant_error)/denominator_lower*U/(1-U)
    w2_error = 2*division_error+(1+2*(32+determinant_error)/denominator_lower)*2*U/(1-U)
    epsilon = F(1,10**10)+max(division_error,w2_error)
    # Two possibly negative barycentric weights extend an axis by at most 2eW.
    extension = 4*epsilon
    return {"subtraction_error_px":subtraction_error,"determinant_error_px2":determinant_error,
            "division_error":division_error,"w2_error":w2_error,"acceptance_epsilon":epsilon,
            "pixel_axis_extension_bound":extension,"analysis_envelope_px":PIXEL_ENVELOPE,
            "envelope_sufficient":extension<PIXEL_ENVELOPE}


def pixel_proof(objects, eligible):
    vertices = [p for obj in objects for p in obj["vertices"]]
    low = tuple(min(p[a] for p in vertices) for a in range(3))
    high = tuple(max(p[a] for p in vertices) for a in range(3))
    center = tuple((x+y)/2 for x,y in zip(low,high))
    by_name = {obj["name"]:obj for obj in objects}
    views = []
    for name,direction_raw in VIEWS.items():
        direction = rational_vector(direction_raw)
        seed = (F(0),F(1),F(0)) if name=="TOP" else (F(0),F(0),F(1))
        r = cross(tuple(-x for x in direction),seed)
        up = cross(r,tuple(-x for x in direction))
        raw_maxima = [max(abs(dot(sub(p,center),axis)) for p in vertices) for axis in (r,up)]
        h0_sq = max(m*m/dot(axis,axis) for m,axis in zip(raw_maxima,(r,up)))
        h_sq = h0_sq*F(121,100)
        camera = camera_intervals(vertices,direction_raw,center)
        rows = []
        for region in eligible:
            obj = by_name[region["object_name"]]
            points = [obj["vertices"][i] for i in region["vertex_indices"]]
            widths_sq = []
            for axis in (r,up):
                values = [dot(p,axis) for p in points]
                widths_sq.append(F(511**2)*(max(values)-min(values))**2/(4*h_sq*dot(axis,axis)))
            determinants_sq = []
            for face_index in region["source_triangle_indices"]:
                a,b,c = [obj["vertices"][i] for i in obj["triangles"][face_index]]
                projected_cross_sq = dot(cross(sub(b,a),sub(c,a)),direction)**2/dot(direction,direction)
                determinants_sq.append(projected_cross_sq*F(511**4)/(16*h_sq*h_sq))
            screen = [screen_point(p,camera) for p in points]
            screen_by_vertex = dict(zip(region["vertex_indices"],screen))
            actual_determinant_intervals = []
            for face_index in region["source_triangle_indices"]:
                a,b,c = [screen_by_vertex[i] for i in obj["triangles"][face_index]]
                determinant = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                actual_determinant_intervals.append(determinant.abs().pair())
            boxes = [[min(p[a].lo for p in screen)-PIXEL_ENVELOPE,
                      max(p[a].hi for p in screen)+PIXEL_ENVELOPE] for a in range(2)]
            counts = [max(0,floor(hi-F(1,2))-ceil(lo-F(1,2))+1) for lo,hi in boxes]
            width_checks = [hi-lo<2 for lo,hi in boxes]
            determinant_check = min(determinants_sq)>F(1,4) and min(pair[0] for pair in actual_determinant_intervals)>F(1,2)
            if not all(width_checks) or not determinant_check:
                raise ValueError("pixel qualification numerical premise failed")
            rows.append({"object_name":region["object_name"],"source_triangle_indices":region["source_triangle_indices"],
                         "ideal_width_squared_px2":widths_sq,"ideal_triangle_determinant_squared_px4":determinants_sq,
                         "binary64_abs_triangle_determinant_intervals_px2":actual_determinant_intervals,
                         "all_triangle_abs_determinants_gt_half_pixel2":determinant_check,
                         "outward_screen_xy_bounds_px":boxes,"axis_pixel_center_upper_counts":counts,
                         "pixel_center_bbox_upper":counts[0]*counts[1],"strictly_below_16":counts[0]*counts[1]<16})
        views.append({"view":name,"direction_rational":list(direction),"right_integer":list(r),"up_integer":list(up),
                      "unpadded_half_span_squared_m2":h0_sq,"half_span_squared_m2":h_sq,
                      "binary64_half_span_interval_m":camera["half_span"].pair(),"regions":rows})
    return {"size_px":[512,512],"global_bounds_world_m":[low,high],"common_center_world_m":center,
            "margin_per_side":F(1,20),"rounding_model":"outward 2^-96 dyadic intervals; binary64 u/(1-u) and subnormal absolute error; order-independent gamma4 dot bound",
            "barycentric_error_certificate":barycentric_envelope(),"projection_by_view":views}


def occlusion_proofs(objects, roles):
    by_name = {obj["name"]:obj for obj in objects}
    role_names = {role:name for name,role in roles.items()}
    covered = by_name[role_names["covered_horizontal"]]
    lid = by_name[role_names["cover_box"]]
    lid_low = [min(p[a] for p in lid["vertices"]) for a in range(3)]
    lid_high = [max(p[a] for p in lid["vertices"]) for a in range(3)]
    rows = []
    for view,d in VIEWS.items():
        hits = []
        for point in covered["vertices"]:
            parameter = (lid_low[2]-point[2])/d[2]
            if parameter<=0:
                raise ValueError("nonpositive cover intersection")
            hits.append(tuple(point[a]+parameter*d[a] for a in range(3)))
        hit_bounds = [[min(p[a] for p in hits),max(p[a] for p in hits)] for a in (0,1)]
        margins = [min(lo-lid_low[a],lid_high[a]-hi) for a,(lo,hi) in enumerate(hit_bounds)]
        if min(margins)<=0:
            raise ValueError("cover is not strict")
        rows.append({"view":view,"hit_bottom_xy_intervals_m":hit_bounds,"strict_interior_margins_m":margins,
                     "whole_rectangle_strictly_occluded":True,"blocker_object_name":lid["name"]})
    opened = by_name[role_names["open_horizontal"]]
    panel_low = [min(p[a] for p in opened["vertices"]) for a in range(3)]
    panel_high = [max(p[a] for p in opened["vertices"]) for a in range(3)]
    exclusions = []
    for obj in objects:
        if obj["name"]==opened["name"]:
            continue
        lo = [min(p[a] for p in obj["vertices"]) for a in range(3)]
        hi = [max(p[a] for p in obj["vertices"]) for a in range(3)]
        below = hi[2]<=panel_low[2]
        separating_axes = [a for a in (0,1) if hi[a]<panel_low[a] or lo[a]>panel_high[a]]
        if not below and not separating_axes:
            raise ValueError("open TOP cannot be proven unobstructed")
        exclusions.append({"object_name":obj["name"],"all_at_or_below_panel":below,"strict_xy_separating_axes":separating_axes})
    return {"covered_six_directions":rows,"open_horizontal_TOP":{"object_name":opened["name"],
            "whole_rectangle_unobstructed":True,"other_object_exclusions":exclusions}}


def read_objects(document):
    objects = []
    for row in document["objects"]:
        vertices = row.get("vertices_world_m",row.get("vertices"))
        triangles = row.get("triangles",row.get("source_triangles"))
        objects.append({"name":row["name"],"vertices":[rational_vector(v) for v in vertices],
                        "triangles":[tuple(face) for face in triangles]})
    return objects


def evaluate(geometry_path, role_path):
    geometry = json.loads(Path(geometry_path).read_bytes())
    role_document = json.loads(Path(role_path).read_bytes())
    roles = role_document.get("roles_by_name",role_document.get("objects",role_document.get("roles",role_document)))
    if isinstance(roles,list):
        roles = {row["name"]:row["role"] for row in roles}
    objects = read_objects(geometry)
    components = [component for obj in objects for component in component_analysis(obj["name"],obj["vertices"],obj["triangles"])]
    eligible = [row for row in components if row["eligible"]]
    unsupported = [row for row in components if not row["rectangle_supported"]]
    expected_roles = {"open_horizontal","open_inclined","covered_horizontal"}
    actual_roles = {roles[row["object_name"]] for row in eligible}
    unsupported_roles = {roles[row["object_name"]] for row in unsupported}
    checks = {
        "metre_identity_fixed_frame":geometry.get("unit")=="metre" and geometry.get("scale_length")==1 and geometry.get("frame")==1 and geometry.get("subframe")==0
            and all(row.get("matrix_world")==[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]] for row in geometry["objects"]),
        "object_count_9":len(objects)==9,"source_triangle_count_56":sum(len(obj["triangles"]) for obj in objects)==56,
        "component_count_24":len(components)==24,"eligible_count_3":len(eligible)==3,
        "eligible_roles_exact":actual_roles==expected_roles,
        "unsupported_roles_exact":unsupported_roles=={"open_square_ring","L_shape"},
        "unsupported_triangle_count_12":sum(len(row["source_triangle_indices"]) for row in unsupported)==12,
        "supported_triangle_count_44":sum(len(row["source_triangle_indices"]) for row in components if row["rectangle_supported"])==44,
        "eligible_exact_area_squared":all(row["area_squared_m4"]==(F(10,65536) if roles[row["object_name"]]=="open_inclined" else F(1,4096)) for row in eligible),
        "ring_has_two_boundary_loops":all(len(row["boundary_loops"])==2 for row in unsupported if roles[row["object_name"]]=="open_square_ring"),
        "L_has_six_boundary_corners":all(len(row["boundary_loops"])==1 and len(row["boundary_loops"][0])==6 and row["area_squared_m4"]==F(5,256)**2 for row in unsupported if roles[row["object_name"]]=="L_shape"),
    }
    pixels = pixel_proof(objects,eligible)
    occlusion = occlusion_proofs(objects,roles)
    checks["all_18_pixel_bounds_strictly_below_16"] = len(eligible)==3 and all(row["strictly_below_16"] for view in pixels["projection_by_view"] for row in view["regions"])
    checks["barycentric_analysis_envelope_sufficient"] = pixels["barycentric_error_certificate"]["envelope_sufficient"]
    return {"schema":"global-local-static-qualification-v1","passed_checked_scope":all(checks.values()),
            "passed":all(checks.values()),"status":"qualified" if all(checks.values()) else "not_realized",
            "disposition":"static_qualified" if all(checks.values()) else "not_realized",
            "checks":checks,"components":components,"eligible":eligible,"unsupported":unsupported,
            "occlusion":occlusion,"pixels":pixels,
            "independence":{"product_modules_imported":False,"product_partition_or_occlusion_called":False,
                            "raster_or_blender_executed":False,"actual_result_used":False,
                            "camera_equations_source_spec_only":True},
            "limits":["Static fit and geometric evidence only. Actual local readability and source/frame identity await three owned sessions.",
                      "Source face IDs refer to the fixed capture triangle ordering, with no general original-asset polygon mapping claim.",
                      "The 2^-16 pixel allowance is an analysis enclosure. Renderer thresholds and camera fitting are unchanged."],
            "input_pins":[pin(geometry_path),pin(role_path),pin(__file__)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry",required=True)
    parser.add_argument("--roles",required=True)
    parser.add_argument("--output",required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    result = evaluate(args.geometry,args.roles)
    output.write_text(json.dumps(rational_json(result),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(output),"sha256":pin(output)["sha256"],"passed_checked_scope":result["passed_checked_scope"],"checks":result["checks"]}))


if __name__ == "__main__":
    main()
