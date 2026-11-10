"""Root read-only geometry audit of completed A/B native records.

No product, fixture oracle, Blender or model imports. Outputs independent
checks, never treats the producer's `passed` flag as verification.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

MATH = Path(__file__).parents[1] / '20261109_architecture_completion/arm_execution_opt_review/evidence/raw_math.py'
spec = importlib.util.spec_from_file_location('root_review_math', MATH)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def read(path):
    def reject(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=reject)


def audit(path):
    raw = read(path)
    checks = []
    def need(condition, label):
        checks.append({'check': label, 'passed': bool(condition)})
    before, after, receipt = raw['native_before'], raw['native_after'], raw['receipt']
    audit_data = raw['product_audit']
    task = audit_data['task']
    static = before['static']
    rest, vertices0, vertices1 = static['rest_vertices'], before['current_vertices'], after['current_vertices']
    sections = task['selection']['sections']
    need(len(rest) == len(vertices0) == len(vertices1) == len(static['raw_weights']), 'full vertex and weight arrays')
    need(before['static'] == after['static'], 'static source preserved')
    need(before['sentinel'] == after['sentinel'], 'external sentinel preserved')
    need(raw['product_error'] is None, 'product returned without exception')
    need(receipt == audit_data['receipt'], 'receipt matches actual host audit')
    ratio0, j0 = g.objective(rest, vertices0, sections)
    ratio1, j1 = g.objective(rest, vertices1, sections)
    need(abs(j0 - raw['actual_before']['max_section_area_loss']) < 1e-10, 'independent before area')
    need(abs(j1 - raw['actual_after']['max_section_area_loss']) < 1e-10, 'independent after area')
    ids = task['protected_vertex_ids']
    protected = g.point_error([vertices0[i] for i in ids], [vertices1[i] for i in ids])
    rotation = max(g.rotation_error(before['world_poses'][i], after['world_poses'][i]) for i in (0, 2))
    translation = max(math.dist([before['world_poses'][i][k][3] for k in range(3)],
                                [after['world_poses'][i][k][3] for k in range(3)]) for i in (0, 2))
    centerline = max(g.point_error(before['heads'], after['heads']), g.point_error(before['tails'], after['tails']))
    centers = g.point_error([g.centroid([vertices0[i] for i in s]) for s in sections],
                            [g.centroid([vertices1[i] for i in s]) for s in sections])
    weights = [[w / math.fsum(row) for w in row] for row in static['raw_weights']]
    rests = [b['rest_matrix'] for b in static['bones']]
    lbs = max(g.point_error(g.lbs(rest, weights, rests, before['poses']), vertices0),
              g.point_error(g.lbs(rest, weights, rests, after['poses']), vertices1))
    fk = max(g.difference(g.fk(rests, before['basis']), before['poses']),
             g.difference(g.fk(rests, after['basis']), after['poses']))
    need(max(protected, translation, centerline, centers, lbs, fk) <= 5e-6, 'independent geometry and protected positions')
    need(rotation <= .001, 'independent endpoint rotation')
    need(audit_data['input_patch']['current_vertices'] == vertices0, 'product consumed actual before vertices')
    need(audit_data['input_patch']['weights'] == weights, 'product consumed native normalized weights')
    status = receipt['status']
    need(status in ('satisfied', 'no_op', 'unreachable', 'not_applicable'), 'supported completed status')
    need(receipt['setter_attempts'] == receipt['setter_returns'] == (2 if status == 'satisfied' else 0), 'actual setter counts')
    target = task['max_section_area_loss'] + task['area_tolerance']
    if status == 'satisfied':
        need(j1 <= target, 'actual target attained')
        need(receipt['task_succeeded'] and receipt['executed'], 'successful execution receipt')
        need(receipt['feedback']['source'] == 'actual_after_capture', 'feedback uses actual after')
        need(abs(receipt['feedback']['max_section_area_loss'] - j1) < 1e-10, 'feedback matches independent area')
        need(audit_data['after_capture']['current_vertices'] == vertices1, 'actual after capture reused')
    else:
        need(before == after, 'entire native record unchanged')
        need(not receipt['executed'], 'no false execution claim')
        need(receipt['task_succeeded'] == (status == 'no_op'), 'no false achievement')
        if status == 'no_op':
            need(j0 <= target, 'no-op already meets target')
        if status == 'unreachable':
            need(j0 > target, 'unreachable actual geometry remains unsatisfied')
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'case_id': raw['case_id'], 'status': status, 'before_j': j0, 'after_j': j1,
            'protected_m': protected, 'endpoint_angle_deg': rotation, 'lbs_m': lbs,
            'checks': checks, 'passed': all(c['passed'] for c in checks)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('files', nargs='+', type=Path)
    args = p.parse_args()
    results = []
    for path in args.files:
        try:
            results.append(audit(path))
        except Exception as exc:
            results.append({'path': str(path), 'passed': False, 'error': repr(exc)})
    report = {'schema': 'root-plugin-ab-geometry-review-v1', 'source': str(MATH),
              'math_sha256': hashlib.sha256(MATH.read_bytes()).hexdigest(),
              'passed': all(r['passed'] for r in results), 'records': results}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'records': len(results),
                      'checks': sum(len(r.get('checks', [])) for r in results), 'output': str(args.output)}))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
