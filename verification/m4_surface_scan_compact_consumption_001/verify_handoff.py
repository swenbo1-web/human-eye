"""Verify the fixed run, receipt closure and anonymous bytes without grading."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HANDOFF = HERE/'runtime/handoff_01'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def request_projection(value):
    projected = {key:item for key,item in value.items() if key not in ('id','jsonrpc','_meta')}
    params = projected.get('params')
    if isinstance(params,dict):
        projected['params'] = {key:item for key,item in params.items() if key != '_meta'}
    return projected


def response_projection(value):
    return {key:item for key,item in value.items() if key not in ('id','jsonrpc','_meta')}


def main():
    plan,run = read(HERE/'PLAN.json'),read(HERE/'RUN_RESULT.json')
    assert sha(HERE/'PLAN.json') == read(HERE/'FREEZE.json')['plan_sha256'] == read(HERE/'GO.json')['plan_sha256']
    assert [row['cell'] for row in plan['sequence']] == ['N1','O1','C1','O2','C2','N2','C3','N3','O3']
    assert plan['logical_denominator'] == 9 and len(run['records']) <= 9
    assert run['started_cells'] == len(run['records']) and run['maximum_consumers'] == 9
    assert run['no_replacements'] and (len(run['records']) == 9 or run['stop'])
    for name,expected in plan['dispatch_input_sha256'].items():
        assert sha(HERE/name) == expected,name
    for name,expected in plan['external_input_sha256'].items():
        assert sha(Path(name)) == expected,name
    for name,expected in read(HERE/'preflight/PROTECTED_BEFORE.json').items():
        assert sha(Path(name)) == expected,name
    profiles = read(HERE/'preflight/SOURCE_BINDING.json')['profiles']
    assert set(profiles) == {'O', 'C'} and plan['source_count'] == 138
    for name, profile in profiles.items():
        ready = read(HERE/('installations/'+name+'_READY.json'))
        manifest = profile['source_manifest']
        assert len(manifest) == 138 and ready['source_sha256'] == profile['source_sha256']
        for row in manifest:
            assert sha(Path(ready['install_root'])/row['path']) == row['sha256']
            if name == 'C':
                assert sha(ROOT/row['path']) == row['sha256']
        assert sha(Path(ready['entry'])) == ready['launcher_sha256']
    terminal = read(HERE/'FORMAL_PROCESS.json')
    assert terminal['status'] == 'terminal' and terminal['started_cells'] == len(run['records'])
    threads = []
    timing_checked = 0
    closure = Counter()
    for slot,row in zip(plan['sequence'],run['records'],strict=False):
        assert all(slot[key] == row[key] for key in ('cell','group','task','round'))
        folder = HERE/'cells'/slot['cell']
        if (folder/'CELL_FINAL_TIMING.json').exists() and (folder/'CELL_TIMING_PUBLICATION.json').exists():
            timing = read(folder/'CELL_FINAL_TIMING.json')
            publication = read(folder/'CELL_TIMING_PUBLICATION.json')
            assert timing['cell'] == row['cell'] and timing['cell_started_ns'] == row['cell_started_ns']
            assert timing['full_cell_wall_ns'] == timing['business_receipts_closed_ns']-timing['cell_started_ns']
            assert timing['within_570s'] == (timing['full_cell_wall_ns'] < 570*10**9)
            assert timing['business_receipts_closed_ns'] >= row['cell_ended_ns']
            assert publication['business_receipts_closed_ns'] == timing['business_receipts_closed_ns']
            assert publication['timing_receipt_publication_started_ns'] <= publication['timing_receipt_publication_closed_ns']
            assert publication['timing_receipt_publication_ns'] == (
                publication['timing_receipt_publication_closed_ns']-publication['timing_receipt_publication_started_ns'])
            timing_checked += 1
        else:
            closure['missing_final_timing_receipts'] += 1
        consumer = row.get('consumer')
        if isinstance(consumer,dict):
            assert read(folder/'CONSUMER.json') == consumer
            assert consumer['input_sha256'] == plan['inputs']['prompt_sha256']
            if consumer.get('thread_id'):
                threads.append(consumer['thread_id'])
            argv = consumer['argv']
            for flag in ('--ignore-user-config','--ignore-rules','--ephemeral','--strict-config'):
                assert flag in argv
            assert argv[argv.index('-m')+1] == 'gpt-6.1-sol' and '--image' not in argv
            if consumer.get('status') == 'completed':
                assert consumer['valid_completion'] and consumer['process_reaped']
                assert consumer['exit_code'] == 0
        finish = row.get('finish')
        if isinstance(finish,dict) and finish.get('confirmed'):
            closure['confirmed_owner_cleanup'] += 1
            assert finish['exit_code'] == 0 and read(folder/'OWNER_FINISH.json') == finish
            closed = read(folder/'owner/CLOSE.json')
            assert closed['confirmed'] and closed['geometry_unchanged'] and closed['asset_unchanged']
            assert closed['native_close']['process_reaped'] and closed['native_close']['exit_code'] == 0
            assert closed['zero_new_images_budget_met']
            if slot['group'] == 'N':
                assert closed['plugin_close'] is None and closed['product_runtime_exit'] is None
                assert not (folder/'owner/plugin').exists()
            else:
                assert closed['plugin_close']['confirmed']
                assert closed['product_runtime_exit']['confirmed']
                assert closed['product_runtime_exit']['exit_code'] == 0
        else:
            closure['unconfirmed_owner_cleanup'] += 1
    assert len(threads) == len(set(threads)), 'consumer context was reused'
    public = HANDOFF/'public'
    provenance = read(HANDOFF/'private/PROVENANCE.json')
    files = {path.relative_to(public).as_posix():sha(path) for path in public.rglob('*') if path.is_file()}
    assert files == provenance['public_files_sha256']
    index = read(public/'INDEX.json')
    assert index['fixed_slots'] == 9 and len(index['answers']) == 9 and not index['scoring_performed']
    mapping = read(HERE/'private/ANON_MAP.json')
    by_id = {row['anonymous_id']:row for row in mapping['rows']}
    execution = Counter()
    answer_states = Counter()
    final_bytes = tool_projections = 0
    for answer in index['answers']:
        anonymous_id = answer['anonymous_id']
        slot = by_id[anonymous_id]
        original = HERE/'cells'/slot['cell']
        directory = public/answer['directory']
        execution[answer['cell_execution_state']] += 1
        answer_states[answer['answer_state']] += 1
        assert all(field not in answer for field in ('group','round','cell','usage','full_cell_wall_ns'))
        if answer['answer_file'] is not None:
            raw = (original/'PUBLIC_FINAL.txt').read_bytes()
            assert (directory/answer['answer_file']).read_bytes() == raw
            assert hashlib.sha256(raw).hexdigest() == answer['answer_original_sha256']
            final_bytes += 1
        archive_path = HANDOFF/'private/raw'/(anonymous_id+'.zip')
        if original.exists():
            with zipfile.ZipFile(archive_path) as archive:
                original_files = {path.relative_to(original).as_posix():path.read_bytes()
                    for path in original.rglob('*') if path.is_file()}
                assert set(archive.namelist()) == set(original_files)
                assert all(archive.read(name) == raw for name,raw in original_files.items())
        else:
            assert not archive_path.exists()
        attempts = read(directory/answer['evidence_file'])['owner_attempts']
        folders = sorted((original/'owner').glob('tool_*'),key=lambda path:int(path.name.split('_')[1]))
        assert len(attempts) == len(folders)
        for attempt,folder in zip(attempts,folders,strict=True):
            request_file = folder/'REQUEST.json'
            assert attempt['request'] == (request_projection(read(request_file)) if request_file.exists() else None)
            responses = [path for path in (folder/'RESPONSE.json',folder/'ERROR_RESPONSE.json') if path.exists()]
            assert len(responses) == len(attempt['responses'])
            for path,response in zip(responses,attempt['responses'],strict=True):
                assert response['value'] == response_projection(read(path))
            tool_projections += 1
    manifest = [{'path':name,'bytes':(public/name).stat().st_size,'sha256':digest}
                for name,digest in sorted(files.items())]
    result = dict(task=plan['cycle_id'],quality_scoring_performed=False,
        group_quality_or_cost_disclosed=False,fixed_slots=9,execution_counts=dict(execution),
        answer_states=dict(answer_states),unchanged_final_files_verified=final_bytes,
        business_attempt_projections_verified=tool_projections,full_cell_receipts_verified=timing_checked,
        closure=dict(closure),unique_model_contexts=len(threads),runtime_sources_verified_per_profile=138,source_profiles_verified=2,
        public_files=manifest,anonymous_packet_sha256=hashlib.sha256(canonical(manifest)).hexdigest(),
        original_errors_and_unknowns_retained=True,perfect_blinding=False,
        blinding_scope='Group and cost envelopes masked; actual business content can reveal the route.')
    with (HERE/'HANDOFF_VERIFICATION.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps({key:value for key,value in result.items() if key != 'public_files'},ensure_ascii=False))


if __name__ == '__main__':
    main()
