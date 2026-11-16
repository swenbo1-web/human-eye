"""Demonstrate each R2 correction using data and unchanged prior checkers."""

import ast
import copy
import difflib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def front_expression(path):
    tree = ast.parse(path.read_bytes())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'frame_checks')
    assignment = next(node for node in ast.walk(function) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'front' for target in node.targets))
    return compile(ast.Expression(assignment.value), str(path), 'eval')


def main():
    old = load('original_r1_checker', HERE / 'saved_frames_r1.py')
    new = load('corrected_r2_checker', HERE / 'saved_frames_r2.py')
    synthetic = load('same_analytic_fixture', HERE / 'ray_pure_r2.py')
    scope = dict(np=new.np, F=new.F, facts={'region': {'front_direction_world': [0, '-1/3', 1]}},
                 roi='region', pose={'target_to_eye_unit': [0, 0, 1]})
    controls = []
    try:
        eval(front_expression(HERE / 'saved_frames_r1.py'), scope)
    except ValueError as error:
        old_failure = str(error)
    else:
        raise ValueError('R1_must_reproduce_lossless_rational_parse_error')
    result = eval(front_expression(HERE / 'saved_frames_r2.py'), scope)
    if result is not True:
        raise ValueError('R2_legitimate_directed_rational_normal_must_be_front')
    controls.append(dict(case='lossless_directed_normal_minus_one_third', passed=True,
                         actual_frozen_expression_evaluated=True, R1_failure=old_failure, R2_front_facing=result))
    frame, capture, arrays = synthetic.fixture()
    extended = copy.deepcopy(capture)
    extended['meshes'][0]['vertices'] = [[-2, -2, -1], [2, -2, -1], [2, 2, -1], [-2, 2, -1]]
    try:
        old.ray_winner_checks(frame, extended, arrays, old.Evidence())
    except ValueError as error:
        old_failure = str(error)
    else:
        raise ValueError('R1_must_reproduce_outside_frustum_pixel_error')
    if old_failure != 'independent_ray_full_foreground_mask':
        raise ValueError('unexpected_R1_ray_rejection')
    review = new.ray_winner_checks(frame, extended, arrays, new.Evidence())
    if review['foreground_pixels'] != 511 * 511:
        raise ValueError('R2_must_preserve_entire_interior_and_reject_only_outside_centres')
    controls.append(dict(case='oversize_plane_last_pixel_centres_outside_NDC', passed=True,
                         R1_failure=old_failure, R2_review=review,
                         all_511_squared_interior_pixels_checked=True, excluded_outside_centres=1023))
    sources = []
    for name in ('saved_frames.py', 'saved_frames_r1.py', 'saved_frames_r2.py', 'correction_controls.py'):
        path = HERE / name
        sources.append(dict(path=str(path.resolve()), sha256=new.sha(path), bytes=path.stat().st_size))
    report = dict(schema='m4-global-local-checker-correction-controls-v1', passed_checked_scope=True,
                  denominator=2, passed=2, controls=controls, source_pins=sources,
                  new_operations=dict(Blender=0, MCP=0, raster=0, model=0))
    with (HERE / 'CORRECTION_CONTROLS.json').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + '\n')
    for before, after, filename in (
        ('saved_frames.py', 'saved_frames_r1.py', 'INITIAL_TO_R1.patch'),
        ('saved_frames_r1.py', 'saved_frames_r2.py', 'R1_TO_R2.patch')):
        delta = ''.join(difflib.unified_diff((HERE / before).read_text(encoding='utf8').splitlines(keepends=True),
                                            (HERE / after).read_text(encoding='utf8').splitlines(keepends=True),
                                            fromfile=before, tofile=after))
        with (HERE / filename).open('x', encoding='utf8', newline='\n') as stream:
            stream.write(delta)
    print(json.dumps(dict(passed_checked_scope=True, controls=2)))


if __name__ == '__main__':
    main()
