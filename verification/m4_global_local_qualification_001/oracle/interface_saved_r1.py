"""Counterexamples execute the actual saved-adapter predicate ASTs."""
import ast
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_oracle_saved_r1",HERE/"check_saved_R1.py")
saved = importlib.util.module_from_spec(spec)
spec.loader.exec_module(saved)


def predicate(marker):
    tree = ast.parse((HERE/"check_saved_R1.py").read_bytes())
    matches = [node.args[0] for node in ast.walk(tree) if isinstance(node,ast.Call)
               and isinstance(node.func,ast.Attribute) and node.func.attr=="require"
               and len(node.args)>=2 and marker in ast.unparse(node.args[1])]
    if len(matches)!=1:
        raise ValueError("saved_predicate_not_unique")
    return compile(ast.Expression(body=matches[0]),str(HERE/"check_saved_R1.py"),"eval")


def main():
    rows = []
    direction_predicate = predicate("oriented_rational_direction_exact_positive_parallel")
    for name,direction,normal,expected in [
        ("published_fraction_scaled_direction",[0,"-1/3",1],[0,-1,3],True),
        ("alternate_positive_scale",[0,-2,6],[0,-1,3],True),
        ("reversed_direction_rejected",[0,1,-3],[0,-1,3],False),
        ("off_axis_direction_rejected",[1,"-1/3",1],[0,-1,3],False),
        ("zero_direction_rejected",[0,0,0],[0,-1,3],False),
    ]:
        value = eval(direction_predicate,{"oracle":saved.oracle},{"published_direction":tuple(map(F,direction)),"expected_normal":tuple(map(F,normal))})
        if value is not expected:
            raise AssertionError(name)
        rows.append(dict(case=name,passed=True))
    center_predicate = predicate("exact_region_center/")
    for name,current,reference,expected in [
        ("rational_string_center_decodes_exactly",[0,0,1],["0","0","1"],True),
        ("changed_center_rejected",[0,0,F(1)+F(1,2**30)],["0","0","1"],False),
    ]:
        value = eval(center_predicate,{"F":F},{"fact":{"center_world_m":current},"expected":{"center_world_m":reference}})
        if value is not expected:
            raise AssertionError(name)
        rows.append(dict(case=name,passed=True))
    try:
        F("nan")
    except ValueError:
        rows.append(dict(case="nonfinite_rational_direction_rejected",passed=True))
    else:
        raise AssertionError("nonfinite_rational_direction_rejected")
    result = dict(schema="global-local-saved-r1-interface-v1",passed=True,case_count=len(rows),cases=rows,
                  actual_predicate_AST_used=True,new_actual_operations=0,
                  source_pins=[saved.oracle.pin(__file__),saved.oracle.pin(HERE/"check_saved_R1.py"),saved.oracle.pin(HERE/"static_oracle.py")])
    path = HERE/"INTERFACE_SAVED_R1.json"
    with path.open("x",encoding="utf8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print(json.dumps(dict(case_count=len(rows),passed=True,sha256=saved.oracle.pin(path)["sha256"])))


if __name__=="__main__":
    main()
