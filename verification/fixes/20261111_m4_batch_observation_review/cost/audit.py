"""Read-only audit of frozen M4 offline records; never imports or runs product/prototypes."""
import argparse
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

COMMIT = '0bcd1660d1ddb43869d077e2c1b63240cb670826'
PRODUCT = 'e077fce38b5951efff8166b3b688d05ffa2ebf04'
PREFIX = 'verification/m4_batch_observation_coverage_001'
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
ROOT = Path('D:/hefe')
HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'AUDIT.json')
    args = parser.parse_args()
    checks = []
    def check(name, condition, detail=None):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
    def git(*argv, root=WT):
        return subprocess.run(['git', '-C', str(root), *argv], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    batch = WT / PREFIX
    def read(relative):
        return json.loads((batch / relative).read_bytes())
    before = git('status', '--short').decode('utf8')
    check('fixed_HEAD', git('rev-parse', 'HEAD').decode().strip() == COMMIT)
    index = read('ARTIFACT_INDEX.json')
    ready = read('COVERAGE_READY.json')
    plan = read('PLAN.json')
    contract = read('MEASUREMENT_CONTRACT.json')
    listed = [row['path'] for row in index['files']]
    roots = [PREFIX + '/' + name for name in ('ARTIFACT_INDEX.json', 'COVERAGE_READY.json')]
    expected = set(listed + roots)
    tracked = set(git('ls-tree', '-r', '--name-only', COMMIT, '--', PREFIX).decode().splitlines())
    disk_all = {p.relative_to(WT).as_posix() for p in batch.rglob('*') if p.is_file()}
    bytecode = {p for p in disk_all if '__pycache__' in p.split('/') or p.endswith('.pyc')}
    disk = disk_all - bytecode
    check('index_count_unique', len(listed) == len(set(listed)) == index['file_count'] == 169)
    check('git_set_exact_171', expected == tracked and len(tracked) == 171,
          {'missing': sorted(expected - tracked), 'extra': sorted(tracked - expected)})
    check('disk_set_exact_171_excluding_declared_bytecode', expected == disk and len(disk) == 171,
          {'missing': sorted(expected - disk), 'extra': sorted(disk - expected), 'ignored_bytecode': sorted(bytecode)})
    paths = sorted(expected)
    payload = ''.join(COMMIT + ':' + p + '\n' for p in paths).encode()
    proc = subprocess.run(['git', '-C', str(WT), 'cat-file', '--batch'], input=payload,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    pos = 0
    files = []
    pins = {row['path']: row for row in index['files']}
    total_indexed = 0
    for path in paths:
        end = proc.stdout.index(b'\n', pos)
        oid, kind, size = proc.stdout[pos:end].decode().split()
        size = int(size)
        raw = proc.stdout[end + 1:end + 1 + size]
        pos = end + 2 + size
        actual = (WT / path).read_bytes()
        check('git_disk:' + path, kind == 'blob' and raw == actual)
        if path in pins:
            pin = pins[path]
            total_indexed += len(actual)
            check('indexed_hash:' + path, len(actual) == pin['bytes'] and sha(actual) == pin['sha256'])
        files.append({'path': path, 'git_blob': oid, 'bytes': len(actual), 'sha256': sha(actual)})
    check('index_total_bytes', total_indexed == index['bytes'], total_indexed)
    check('ready_index_sha', ready['artifact_index_sha256'] == sha((batch / 'ARTIFACT_INDEX.json').read_bytes()))
    check('ready_PLAN_sha', ready['PLAN_sha256'] == sha((batch / 'PLAN.json').read_bytes()))
    check('ready_counts', ready['indexed_files'] == 169 and ready['root_self_reference_records'] == 2
          and ready['expected_committed_batch_files'] == 171)
    binding = {'manifest_sha256': 'validation/MANIFEST.json',
               'prototype_draft_sha256': 'prototype/draft.py',
               'prototype_final_sha256': 'prototype/final.py',
               'native_sha256': 'validation/native_projection.py',
               'verifier_sha256': 'validation/verify_projection.py',
               'runner_sha256': 'benchmark/run_measurements.py'}
    for key, path in binding.items():
        check('contract:' + key, sha((batch / path).read_bytes()) == contract[key])
    for key, pathkey in [('final_prototype_sha256', 'final_prototype'), ('primary_input_sha256', 'primary_input')]:
        check('plan:' + key, sha((batch / plan[pathkey]).read_bytes()) == plan[key])
    check('plan_product', plan['product_commit'] == PRODUCT and plan['product_source_count'] == 137
          and plan['product_source_sha256'] == '53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732')
    root_plan_path = 'docs/M4_BATCH_OBSERVATION_COVERAGE_001_PLAN.md'
    root_plan = git('show', 'ec20790f:' + root_plan_path, root=ROOT)
    check('original_root_plan_copy', root_plan == (batch / Path(root_plan_path).name).read_bytes())
    unified_path = 'docs/V21_UNIFIED_OBSERVATION_OPTIMIZATION_REVIEW_20261111.md'
    unified = git('show', '7286fac4:' + unified_path, root=ROOT)
    changed = git('diff', '--name-only', PRODUCT, COMMIT).decode().splitlines()
    product_changes = [p for p in changed if not (p.startswith('verification/') or p.startswith('docs/'))]
    check('product_diff_zero', not product_changes, product_changes)
    manifest = read('validation/MANIFEST.json')
    manifest_records = list(manifest['base'].values())
    for variant in manifest['variants']:
        manifest_records.extend(variant['files'])
    for row in manifest_records:
        data = (batch / row['path']).read_bytes()
        check('manifest_file:' + row['path'], len(data) == row['bytes'] and sha(data) == row['sha256'])
    top = read('benchmark/run_01/RESULTS.json')
    for path, digest in top['frozen_files_sha256'].items():
        p = Path(path)
        check('pinned_scope:' + path, p.resolve().is_relative_to(WT.resolve()))
        check('benchmark_pinned:' + path, sha(p.read_bytes()) == digest)
    check('benchmark_matrix', top['fixed_workers'] == 12 and top['samples_per_worker'] == 21
          and len(top['execution_order']) == 12)
    cost = read('COST_TABLE.json')
    rows = []
    pids = []
    for claimed in cost['rows']:
        raw_path = batch / claimed['raw_path']
        raw_bytes = raw_path.read_bytes()
        raw = json.loads(raw_bytes)
        folder = raw_path.parent
        key = (raw['fixture'], raw['lane'])
        check('raw_pointer:' + '/'.join(key), sha(raw_bytes) == claimed['raw_sha256'])
        order = json.loads((folder / 'WORK_ORDER.json').read_bytes())
        process = json.loads((folder / 'PROCESS.json').read_bytes())
        check('order:' + '/'.join(key), order == raw['order'] and order['samples'] == 21
              and order['manifest_sha256'] == contract['manifest_sha256']
              and order['runner_sha256'] == contract['runner_sha256'])
        for field in ('implementation', 'bundle', 'request'):
            check('order_pin:' + '/'.join(key) + ':' + field,
                  sha(Path(order[field]).read_bytes()) == order[field + '_sha256'])
        check('worker_exit:' + '/'.join(key), process['exit_code'] == 0 and process in top['execution_order'])
        check('worker_stderr:' + '/'.join(key), (folder / 'stderr.txt').read_bytes() == b'')
        check('samples:' + '/'.join(key), len(raw['samples']) == raw['sample_count'] == 21
              and [s['sample'] for s in raw['samples']] == list(range(1, 22)) and raw['warmup_calls'] == 1)
        pids.append(raw['runtime_pid'])
        samples = [s['elapsed_ns'] for s in raw['samples']]
        response = {name: (folder / name).read_bytes() for name in ('DIRECTORY.json', 'SELECTED.json')}
        sizes = {name: len(data) for name, data in response.items()}
        check('response_hashes:' + '/'.join(key), all(sha(data) == raw['response_sha256'][name]
              and len(data) == raw['response_bytes'][name] for name, data in response.items()))
        check('sample_bytes:' + '/'.join(key), all(s['directory_bytes'] == sizes['DIRECTORY.json']
              and s['selected_bytes'] == sizes['SELECTED.json'] and s['total_response_bytes'] == sum(sizes.values())
              for s in raw['samples']))
        row = {'fixture': raw['fixture'], 'lane': raw['lane'],
               'directory_bytes': sizes['DIRECTORY.json'], 'selected_bytes': sizes['SELECTED.json'],
               'total_bytes': sum(sizes.values()), 'median_projection_ns': statistics.median(samples),
               'minimum_projection_ns': min(samples), 'maximum_projection_ns': max(samples), 'samples_ns': samples,
               'python_traced_incremental_peak_bytes': raw['tracemalloc']['peak_bytes'] - raw['tracemalloc']['before_current_bytes'],
               'process_lifetime_peak_bytes': raw['OS_memory']['lifetime_peak_bytes']}
        check('cost_row:' + '/'.join(key), all(row[k] == claimed[k] for k in row))
        check('tracemalloc_arithmetic:' + '/'.join(key), row['python_traced_incremental_peak_bytes'] == raw['tracemalloc']['incremental_peak_bytes'])
        check('no_runtime_work_recorded:' + '/'.join(key), all(raw[k] == 0 for k in ('actual_host_requests', 'product_helper_calls', 'model_consumers', 'new_images')))
        rows.append(row)
    check('matrix_unique', len(rows) == len({(r['fixture'], r['lane']) for r in rows}) == len(set(pids)) == 12)
    comparisons = []
    for fixture in top['fixture_order']:
        values = {r['lane']: r for r in rows if r['fixture'] == fixture}
        final, native, draft = (values[k] for k in ('final', 'native', 'draft'))
        same_bytes = {}
        for name in ('DIRECTORY.json', 'SELECTED.json'):
            prefix = batch / 'benchmark/run_01' / fixture
            a, b, d = [(prefix / lane / name).read_bytes() for lane in ('final', 'native', 'draft')]
            same_bytes[name] = a == b
            check('final_native_bytes:' + fixture + ':' + name, a == b)
            jd = json.loads(d)
            if name == 'DIRECTORY.json':
                for obj in jd['objects']:
                    obj.pop('center', None)
            check('center_only_simplification:' + fixture + ':' + name, jd == json.loads(a))
        comparisons.append({'fixture': fixture, 'same_bytes': same_bytes,
                            'final_minus_native_median_ns': final['median_projection_ns'] - native['median_projection_ns'],
                            'final_vs_native_time_increase_percent': 100 * (final['median_projection_ns'] / native['median_projection_ns'] - 1),
                            'final_minus_native_python_peak': final['python_traced_incremental_peak_bytes'] - native['python_traced_incremental_peak_bytes'],
                            'draft_to_final_bytes_saved': draft['total_bytes'] - final['total_bytes'],
                            'draft_to_final_time_saved_percent': 100 * (1 - final['median_projection_ns'] / draft['median_projection_ns']),
                            'draft_to_final_peak_saved_percent': 100 * (1 - final['python_traced_incremental_peak_bytes'] / draft['python_traced_incremental_peak_bytes'])})
    simple = read('SIMPLIFICATION_RESULT.json')
    base = {r['lane']: r for r in rows if r['fixture'] == 'base'}
    for k, metric in [('response_bytes', 'total_bytes'), ('projection_median_ns', 'median_projection_ns'),
                      ('python_peak_bytes', 'python_traced_incremental_peak_bytes')]:
        check('simplification:' + k, simple[k + '_before'] == base['draft'][metric]
              and simple[k + '_after'] == base['final'][metric])
    check('simplification_bytes_removed', simple['bytes_removed'] == base['draft']['total_bytes'] - base['final']['total_bytes'] == 1824)
    optional = read('OPTIONAL_ENCODING.json')
    for row in optional['rows']:
        folder = batch / 'optional_encoding'
        sizes = {name: len((folder / (row['lane'] + '_' + name)).read_bytes())
                 for name in ('DIRECTORY.json', 'SELECTED.json')}
        check('optional_bytes:' + row['lane'], sizes.get('DIRECTORY.json') == row['directory_bytes']
              and sizes.get('SELECTED.json') == row['selected_bytes'] and sum(sizes.values()) == row['total_response_bytes'] == 20228)
    validation = read('validation/RESULTS_01.json')
    check('validation_record_count', validation['check_count'] == len(validation['checks']) == ready['correctness_assertions_passed'] == 674)
    check('validation_record_passed', validation['passed'] is True)
    check('validation_all_recorded_assertions_passed', all(row['passed'] is True for row in validation['checks']))
    after = git('status', '--short').decode('utf8')
    check('worktree_unchanged', before == after, {'before': before, 'after': after})
    output = {'review': 'independent read-only evidence arithmetic and integrity; no benchmark/product execution',
              'fixed_commit': COMMIT, 'product_commit': PRODUCT, 'files': files,
              'indexed_bytes': total_indexed, 'ignored_bytecode': sorted(bytecode),
              'root_plan_sha256': sha(root_plan), 'root_unified_commit': '7286fac4', 'root_unified_sha256': sha(unified),
              'product_diff': product_changes, 'measurement_contract': contract,
              'rows': rows, 'comparisons': comparisons, 'checks': checks,
              'passed': all(c['passed'] for c in checks), 'failed': [c for c in checks if not c['passed']],
              'not_run': ['performance resampling', 'projection/product imports', 'Blender', 'model consumers'],
              'unmeasured': ['native relation computation cost', 'host/MCP lifecycle cost', 'model code generation',
                             'model tool choice/rounds/tokens/fees', 'actual live two-call source currentness', 'cache hits']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'passed': output['passed'], 'check_count': len(checks), 'failed': output['failed'],
                      'files': len(files), 'workers': len(rows), 'samples': sum(len(r['samples_ns']) for r in rows),
                      'comparisons': comparisons, 'output': str(args.output)}, ensure_ascii=False))
    return 0 if output['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
