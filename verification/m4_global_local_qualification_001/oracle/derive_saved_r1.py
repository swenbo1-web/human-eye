"""Preserve frozen scorer and derive saved-format corrections explicitly."""
import difflib
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def main():
    original_path = HERE/"check_saved.py"
    original = original_path.read_bytes().decode("utf-8")
    candidate = original
    changes = [
        ('label+"_FRAMES.json"','label+"_FRAMES_R2.json"',2),
        ('tuple(expected["center_world_m"])','tuple(map(F,expected["center_world_m"]))',1),
        ('        normal = oracle.inormalize(tuple(oracle.Interval(x) for x in expected["plane_normal_integer"]))\n'
         '        audit.require(all(interval_contains(axis,value) for axis,value in zip(normal,fact["front_direction_world"])),"oriented_unit_normal_rounding_enclosure/"+label+"/"+roi)',
         '        expected_normal = tuple(map(F,expected["plane_normal_integer"]))\n'
         '        published_direction = tuple(map(F,fact["front_direction_world"]))\n'
         '        audit.require(oracle.cross(published_direction,expected_normal)==(0,0,0) and oracle.dot(published_direction,expected_normal)>0,\n'
         '                      "oriented_rational_direction_exact_positive_parallel/"+label+"/"+roi)',1),
        ('                                 status=fact["status"],reason=fact["reason"],unobserved_reason=evidence_row["unobserved_reason"],',
         '                                 independent_normal_integer=expected["plane_normal_integer"],\n'
         '                                 independent_unit_normal_exact={"numerator":expected["plane_normal_integer"],"denominator":"sqrt("+str(oracle.dot(expected["plane_normal_integer"],expected["plane_normal_integer"]))+")"},\n'
         '                                 public_front_direction_world=fact["front_direction_world"],\n'
         '                                 status=fact["status"],reason=fact["reason"],unobserved_reason=evidence_row["unobserved_reason"],',1),
    ]
    for old,new,count in changes:
        if candidate.count(old)!=count:
            raise ValueError("derivation_anchor_count")
        candidate = candidate.replace(old,new)
    target = HERE/"check_saved_R1.py"
    with target.open("x",encoding="utf-8",newline="\n") as stream:
        stream.write(candidate)
    diff = HERE/"SAVED_R1.diff"
    with diff.open("x",encoding="utf-8",newline="\n") as stream:
        stream.write("".join(difflib.unified_diff(original.splitlines(keepends=True),candidate.splitlines(keepends=True),
                     fromfile="frozen/check_saved.py",tofile="derived/check_saved_R1.py")))
    record = dict(schema="global-local-saved-adapter-correction-v1",original=pin(original_path),derived=pin(target),diff=pin(diff),
        original_result=pin(HERE/"QUALIFICATION_INITIAL.json"),
        original_stdout=pin(HERE/"INITIAL.stdout.log"),original_stderr=pin(HERE/"INITIAL.stderr.log"),
        corrections=[
            dict(issue="Separate frame checker preserves failed initial runs and publishes three final reports with _R2 suffix.",change="Read explicit final R2 report paths and preserve original report hashes."),
            dict(issue="Static exact JSON stores rational centres as strings. Frozen saved checker compared those to Fraction current coordinates without decoding.",change="Decode expected centres to Fraction before exact equality."),
            dict(issue="Published front_direction_world is an oriented rational direction, including [0,'-1/3',1]. It carries no unit-length contract.",change="Decode Fraction and require exact positive parallelism to the independent geometric normal. Preserve the public direction. Report independent unit normal symbolically from the geometric primitive.")],
        unchanged=["Frozen geometry and source triangles","3 eligible regions","Area and nz thresholds","Original public facts and images","Static six-view strict occlusion proof","Published camera validation","Current identity and per-scope binding","Pixel16/boundary4/contrast24 gates","Three actual sessions with no replacement"],
        live_operations=0,product_changes=0)
    out = HERE/"SAVED_ADAPTER_CORRECTION_01.json"
    with out.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(record,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print(json.dumps(dict(derived=pin(target),record=pin(out))))


if __name__=="__main__":
    main()
