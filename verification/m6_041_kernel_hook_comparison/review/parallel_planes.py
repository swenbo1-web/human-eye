"""Exact plane-distance certificate for newly admitted original 129×129 fixture."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path
base=Path(__file__).resolve().parent.parent
components=base/"s0/historical_installed_r3/pair129_geometry.json"
meshes=json.loads(components.read_bytes())
r3=json.loads((components.parent/"pair129.json").read_bytes())["default"]["result"]
old=json.loads((base/"s0/historical_installed_032/pair129.json").read_bytes())["default"]["result"]
planes=[]
nfaces=[]
for obj in meshes:
    plane={sum(map(Fraction,obj["vertices"][i])) for face in obj["faces"] for i in face}
    assert len(plane)==1
    planes.append(plane.pop())
    nfaces.append(len(obj["faces"]))
bound=(planes[1]-planes[0])**2/3
i,j=r3["witness_triangle_indices"]
p=list(map(Fraction,r3["point_a_world"]))
q=list(map(Fraction,r3["point_b_world"]))
assert p in [list(map(Fraction,meshes[0]["vertices"][k])) for k in meshes[0]["faces"][i]]
assert q in [list(map(Fraction,meshes[1]["vertices"][k])) for k in meshes[1]["faces"][j]]
observed=sum((a-b)**2 for a,b in zip(p,q))
assert nfaces==[129,129] and (i,j)==(0,0) and bound==observed==3
assert not old["measurement_valid"] and r3["measurement_valid"]
out={"frozen_input_sha256":hashlib.sha256(components.read_bytes()).hexdigest(),"method":"All native triangle convex hulls lie on x+y+z=0 or 3. Cauchy-Schwarz gives squared separation at least 3. Two original vertices on canonical rows [0,0] attain it.",
     "native_pair_count":129**2,"plane_sums":list(map(str,planes)),"lower_bound_squared":str(bound),
     "attained_squared":str(observed),"points":[list(map(str,p)),list(map(str,q))],"lexicographic_first":[i,j],
     "old_valid":old["measurement_valid"],"r3_valid":True,"status":"PASS_EXACT_INCREASED_COVERAGE"}
with (base/"review/PAIR129_INDEPENDENT.json").open("x",encoding="utf8") as f:
    json.dump(out,f,indent=2)
print(json.dumps(out))

