"""Root reconciliation of independent reviews and original timing/quality; offline only."""
from pathlib import Path
from fractions import Fraction
from statistics import median
import hashlib
import json
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = Path('D:/hefe')
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = AUTHOR / 'verification/m4_surface_scan_compact_consumption_001'
HEAD = 'e089a7ba42c276b6f537b62c1a0a4f037fdaec6d'
SEAL = ROOT / 'verification/fixes/20261113_m4_surface_scan_compact_quality_review/QUALITY_SEAL.json'
CHECKS, INPUTS = [], {}

def read(path):
    data = path.read_bytes()
    INPUTS[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data

def load(path):
    return json.loads(read(path))

def check(name, value):
    CHECKS.append({'name': name, 'passed': bool(value)})

def git(*args):
    return subprocess.check_output(['git', *args], cwd=AUTHOR).decode().strip()

check('author_fixed_head', git('rev-parse', 'HEAD') == HEAD)
check('author_clean', git('status', '--porcelain') == '')
seal = load(SEAL)
check('original_seal_unchanged', INPUTS[str(SEAL)]['sha256'] == 'c054d8b5ea8ef672a9b3558c9fd33d485e87593fc53c87df6f2ec0ba6a82d9eb')
byanon = {r['anonymous_id']: r for r in seal['answers']}
account = load(OUT / 'accounting/RESULTS.json')
binding = load(OUT / 'binding/RESULTS.json')
mechanism = load(OUT / 'mechanism/RESULTS.json')
check('accounting_1191', account['checks'] == 1191 and not account['failed_checks'])
check('binding_3067', binding['all_passed'] and binding['check_count'] == 3067 and not binding['failed'])
for name, count in [('accounting', 1191), ('binding', 3067), ('mechanism', 92)]:
    rows = load(OUT / name / 'CHECKS.json')
    check(name + '_check_list', len(rows) == count and all(r['passed'] for r in rows))
    manifest = OUT / name / 'ARTIFACT_MANIFEST.json'
    if manifest.exists():
        for item in load(manifest)['files']:
            raw = read(OUT / name / item['path'])
            check(name + '_artifact_' + item['path'], len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'])

cells = {r['cell']: r for r in account['cells']}
mechanisms = {r['cell']: r for r in mechanism['rows']}
check('nine_cells', set(cells) == {g + str(n) for g in 'NOC' for n in range(1, 4)})
for cell, row in cells.items():
    q = byanon[row['anonymous_id']]
    t = load(BATCH / 'cells' / cell / 'CELL_FINAL_TIMING.json')
    consumer = load(BATCH / 'cells' / cell / 'CONSUMER.json')
    final = read(BATCH / 'cells' / cell / 'PUBLIC_FINAL.txt')
    m = mechanisms[cell]
    check(cell + '_final_seal', hashlib.sha256(final).hexdigest() == q['final_sha256'])
    check(cell + '_quality', row['primary_quality'] == q['primary_classification'] and row['content_quality'] == q['final_content_classification'])
    check(cell + '_execution', row['execution'] == q['execution_state'] == consumer['status'] == m['execution_status'])
    check(cell + '_elapsed', t['business_receipts_closed_ns'] - t['cell_started_ns'] == t['full_cell_wall_ns'] == row['full_ns'])
    check(cell + '_original_deadline', t['within_570s'] and 0 < row['full_ns'] <= 570_000_000_000)
    check(cell + '_tools', row['tool_attempts'] == len(m['tools']))
    check(cell + '_text_bytes', row['CLI_tool_text_utf8_bytes'] == sum(x['text_bytes'] for x in m['tools']))
    usage = row['reported_usage']
    check(cell + '_reported_tokens', row['reported_input_plus_output'] == usage['input_tokens'] + usage['output_tokens'])
    check(cell + '_uncached', row['uncached_input'] == usage['input_tokens'] - usage['cached_input_tokens'])
    check(cell + '_facts_interval', abs((m['final_cli_ns'] - m['first_sufficient_cli_ns']) / 1e9 - m['first_sufficient_to_final_s']) < 1e-9)
    if cell.startswith('C'):
        check(cell + '_one_brief', len(m['tools']) == 1 and m['tools'][0]['response_detail'] == 'brief' and m['tools'][0]['text_bytes'] == 7911 and m['post_sufficient_tool_s'] == 0)

groups = {}
for group in 'NOC':
    rows = [cells[group + str(i)] for i in range(1, 4)]
    groups[group] = {'full_ns': sum(r['full_ns'] for r in rows), 'reported_tokens': sum(r['reported_input_plus_output'] for r in rows), 'effective_correct': sum(r['primary_quality'] == 'complete_correct' for r in rows)}
check('retained_failed_cells', {k for k, v in cells.items() if v['execution'] == 'failed'} == {'N2', 'O2'})
check('quality_denominators', seal['primary_counts']['complete_correct'] == 7 and seal['primary_counts']['execution_failure'] == 2 and seal['content_counts']['complete_correct'] == 9)
comparisons = {}
for group in 'NO':
    ratios = [Fraction(cells['C' + str(i)]['full_ns'], cells[group + str(i)]['full_ns']) for i in range(1, 4)]
    ratio = median(ratios)
    tokens = Fraction(groups['C']['reported_tokens'], groups[group]['reported_tokens'])
    actual = account['comparisons']['C/' + group]
    stated = actual['median_pair_ratio']
    check(group + '_paired_ratio', ratio == Fraction(stated['numerator'], stated['denominator']))
    stated_tokens = actual['reported_token_ratio']
    check(group + '_token_ratio', tokens == Fraction(stated_tokens['numerator'], stated_tokens['denominator']))
    check(group + '_formal_gate_false', actual['formal_gate_passed'] is False and actual['both_3_of_3_effective_complete'] is False)
    comparisons['C/' + group] = {'paired_time_ratio': str(ratio), 'reported_token_ratio': str(tokens), 'formal_gate_passed': False}

result = {'fixed_delivery': HEAD, 'checks': len(CHECKS), 'failed': [x for x in CHECKS if not x['passed']], 'groups': groups, 'comparisons': comparisons, 'inputs': INPUTS, 'checks_detail': CHECKS, 'new_Blender_model_API_runs': 0, 'scope': 'Root independent raw elapsed/final/seal reconciliation and cross-review agreement; detailed source/accounting checks are separately attributed to reviewer reports.'}
(OUT / 'ROOT_CROSSCHECK.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'checks': result['checks'], 'failed': result['failed'], 'comparisons': comparisons}, ensure_ascii=False))
raise SystemExit(bool(result['failed']))
