"""Preserve the Windows alias replay while running the previous frozen verifier."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys


OLD_COMMIT = 'd7b07861'
OLD_NS = 'verification/m1_target_observation_first_image_path_001/checks/'
OLD_RECEIPTS = {
    'replay.py': '85648622745a97216a3b243acea6037f63cb808e66756f8bd81a642b845810ae',
    'BASELINE_DISPATCH_RX.bin': 'd3ffd9e4c290d180a1c139c3e5f180c7b396f94b6a0b9cf568c9127751de8215',
    'CANDIDATE_DISPATCH_RX.bin': '1b633b584220d6440813934903b487b8dbbdf35cf1bf00909c0d4845e6746acf',
    'CASE_ALIAS_DISPATCH_RX.bin': '65d3f6509a0409410a97463990b7f2539abe5fa5595d2cba1b74e7bf91778d13',
}


def main(repo, baseline, candidate, out):
    from hashlib import sha256

    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    def from_git(member):
        data = subprocess.check_output(['git', 'show', OLD_COMMIT + ':' + OLD_NS + member], cwd=repo)
        require(sha256(data).hexdigest() == OLD_RECEIPTS[member], 'previous_frozen_git_blob_changed/' + member)
        return data

    out.mkdir(parents=True, exist_ok=False)
    staging_script = out / 'replay.py'
    with staging_script.open('xb') as sink:
        sink.write(from_git('replay.py'))
    frozen = run_path(str(staging_script))
    scope = frozen['run'].__globals__
    actual_worker, wire, save_wire = (scope[name] for name in ('run_worker', 'replay_wire', 'save_wire'))
    image_paths, image_bytes = (scope[name] for name in ('image_paths', 'image_bytes'))
    captures = []

    def record_worker(repo, binding):
        context = actual_worker(repo, binding)
        captures.append({
            'source_sha256': context['source_sha256'],
            'packet': {**context['primary_packet'], 'result': context['controls']['path_case_alias']},
        })
        return context

    scope['run_worker'] = record_worker
    replay_path = out / 'REPLAY.json'
    fixed = scope['run'](repo, baseline, candidate, replay_path, out)
    require(len(captures) == 2, 'frozen_replay_must_use_two_workers')
    old_a, old_b, old_failure = (from_git(name) for name in (
        'BASELINE_DISPATCH_RX.bin', 'CANDIDATE_DISPATCH_RX.bin', 'CASE_ALIAS_DISPATCH_RX.bin'))
    archived = {
        'previous_git_baseline': save_wire(out / 'PREVIOUS_BASELINE_DISPATCH_RX.bin', old_a),
        'previous_git_candidate': save_wire(out / 'PREVIOUS_CANDIDATE_DISPATCH_RX.bin', old_b),
        'previous_git_actual_alias_failure': save_wire(out / 'PREVIOUS_CASE_ALIAS_DISPATCH_RX.bin', old_failure),
        'new_baseline_alias': save_wire(out / 'BASELINE_ALIAS_DISPATCH_RX.bin', wire(captures[0]['packet'])),
        'new_candidate_alias': save_wire(out / 'CANDIDATE_ALIAS_DISPATCH_RX.bin', wire(captures[1]['packet'])),
    }
    failure = json.loads(old_failure)
    paths_before = image_paths(failure['result'])
    require(len(paths_before) == 2 and paths_before[0] is None and '/SLOTS/' in paths_before[1],
            'old_case_alias_output_must_be_actual_failure')
    actual_alias = captures[1]['packet']['result']
    old_failure_without_path = deepcopy(failure)
    body = scope['value'](failure['result'], strip_target=True)[0]
    old_failure_without_path['result']['content'][0]['text'] = json.dumps(
        body, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    checks = {
        'frozen_replay_passed': fixed,
        'baseline_positive_unchanged': (out / 'BASELINE_DISPATCH_RX.bin').read_bytes() == old_a,
        'candidate_positive_bytes_equal_prior_candidate': (out / 'CANDIDATE_DISPATCH_RX.bin').read_bytes() == old_b,
        'candidate_alias_exact_baseline_alias': wire(captures[1]['packet']) == wire(captures[0]['packet']),
        'candidate_alias_exact_old_failed_alias_stripping_only_path': wire(captures[1]['packet']) ==
            wire(old_failure_without_path),
        'candidate_alias_has_no_path': not image_paths(actual_alias),
        'candidate_alias_retains_both_actual_PNGs': len(image_bytes(actual_alias)) == 2 and
            image_bytes(actual_alias) == image_bytes(failure['result']),
        'candidate_alias_reply_is_success': actual_alias['isError'] is False,
    }
    receipt = {
        'schema': 'm1-target-observation-first-image-path-windows-byte-controls-v1',
        'passed': all(checks.values()), 'checks': checks,
        'prior_git_commit': subprocess.check_output(['git', 'rev-parse', OLD_COMMIT], cwd=repo).decode().strip(),
        'replay_script': scope['pin'](staging_script), 'frozen_replay': scope['pin'](replay_path),
        'artifacts': {**archived,
            'new_baseline': scope['pin'](out / 'BASELINE_DISPATCH_RX.bin'),
            'new_candidate': scope['pin'](out / 'CANDIDATE_DISPATCH_RX.bin')},
        'old_failure_published_paths': paths_before,
        'new_alias_published_paths': image_paths(actual_alias),
        'candidate_source_sha256': captures[1]['source_sha256'],
        'baseline_source_sha256': captures[0]['source_sha256'],
        'new_positive_response_and_alias_scope': 'Actual installed in-process JSON-RPC responses with CRLF.',
        'Blender_starts': 0, 'model_consumers': 0, 'new_rasters': 0,
    }
    receipt_path = out / 'BYTE_CONTROLS.json'
    with receipt_path.open('x', encoding='utf8', newline='\n') as sink:
        json.dump(receipt, sink, ensure_ascii=False, indent=2, allow_nan=False)
        sink.write('\n')
    print(receipt_path, scope['pin'](receipt_path)['sha256'], receipt['passed'], flush=True)
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit('use isolated Python -I -B')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--repo', required=True, type=Path)
    cli.add_argument('--baseline', type=Path)
    cli.add_argument('--candidate', required=True, type=Path)
    cli.add_argument('--out', required=True, type=Path)
    args = cli.parse_args()
    baseline = args.baseline or args.repo / 'verification/m1_source_region_final_image_001/install/PRODUCT_RUN_BINDING.json'
    raise SystemExit(main(args.repo, baseline, args.candidate, args.out))
