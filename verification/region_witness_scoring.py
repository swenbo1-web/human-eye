"""Condition-blind finite witness grading, independent of product summaries."""
import math


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def near(actual, expected):
    return finite(actual) and finite(expected) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)


def grade(answer, task_sha256, truth, evidence):
    """Truth contains all acceptable witnesses; evidence records actual choices.

    Text interpretation is reviewed by a separate blind reviewer. A numeric pass
    does not imply adequate reasoning, or prove an unsupported negative claim.
    """
    checks = dict(task_binding=False, original_triangle=False, same_face_evidence=False,
                  source_and_frame=False, numbers=False, reliability=False,
                  core_membership=False, confirmation_scope=False, anchor_relation=False)
    issues = []
    try:
        assert type(answer) is dict and set(answer) == {'task_sha256', 'selected_triangle', 'frames', 'interpretation'}
        checks['task_binding'] = answer['task_sha256'] == task_sha256
        face = answer['selected_triangle']
        checks['original_triangle'] = type(face) is int and any(face in f['acceptable_witnesses'] for f in truth['frames'])
        assert type(answer['frames']) is list and len(answer['frames']) == 2
        rows = {f['label']: f for f in answer['frames']}
        assert len(rows) == 2 and set(rows) == {f['label'] for f in truth['frames']}
        checks['same_face_evidence'] = type(face) is int and face in evidence['targeted_triangle_indices'] and evidence['same_original_topology_verified']
        checks['anchor_relation'] = evidence['anchor_ids'] == {f['label']: f['anchor']['anchor_id'] for f in truth['frames']}
        source_ok = numeric_ok = reliable_ok = member_ok = scope_ok = True
        for frame in truth['frames']:
            row = rows[frame['label']]
            assert set(row) == {'label', 'file_sha256', 'principal_stretches', 'area_ratio', 'state', 'reason', 'in_core', 'has_confirmed_mixed_witness'}
            expected = frame['facts'][str(face)] if str(face) in frame['facts'] else frame['facts'][face]
            source_ok &= row['file_sha256'] == frame['source_ref']['scene_sha256']
            reliable_ok &= row['state'] == expected['state'] and row['reason'] == expected['reason']
            member_ok &= type(row['in_core']) is bool and row['in_core'] == (face in frame['members'])
            if expected['state'] == 'unknown':
                numeric_ok &= row['principal_stretches'] is None and row['area_ratio'] is None
            else:
                values = row['principal_stretches']
                numeric_ok &= type(values) is list and len(values) == 2 and all(near(a, b) for a, b in zip(values, expected['principal_stretches'])) and near(row['area_ratio'], expected['area_ratio'])
            core_unknown = any(frame['facts'].get(str(i), frame['facts'].get(i))['state'] == 'unknown' for i in frame['members'])
            confirmation = True if frame['acceptable_witnesses'] else None if core_unknown else False
            actual = row['has_confirmed_mixed_witness']
            scope_ok &= actual is confirmation
        checks.update(source_and_frame=bool(source_ok), numbers=bool(numeric_ok), reliability=bool(reliable_ok),
                      core_membership=bool(member_ok), confirmation_scope=bool(scope_ok))
        assert type(answer['interpretation']) is str and answer['interpretation'].strip()
    except (AssertionError, KeyError, TypeError, ValueError, IndexError) as exc:
        issues.append(type(exc).__name__)
    return dict(checks=checks, mechanical_complete=all(checks.values()), issues=issues,
                interpretation_review='required_separately_blind', tolerance=dict(relative=1e-9, absolute=1e-9))
