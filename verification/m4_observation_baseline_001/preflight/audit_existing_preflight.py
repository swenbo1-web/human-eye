"""Audit preserved N/P preflight bytes; never rerun a backend or request."""
import hashlib
import json
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
RUN=HERE/'run_02'
OUT=HERE/'postprocess_01'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
read=lambda path:json.loads(Path(path).read_bytes())


def main():
    OUT.mkdir(exist_ok=False)
    script=HERE/'run_preflight.py'
    raw=script.read_bytes()
    helper=types.ModuleType('_m4_existing_preflight_pure_checks')
    helper.__file__=str(script)
    exec(compile(raw,str(script),'exec',dont_inherit=True),helper.__dict__)
    original=read(RUN/'RESULTS.json')
    assert original['passed'] is False and original['original_inputs_unchanged'] and original['runtime_source_unchanged']
    assert len(original['cases'])==2
    truth_raw=(BATCH/'scoring/TRUTH.json').read_bytes()
    assert sha(truth_raw)==helper.TRUTH_SHA
    truth=json.loads(truth_raw)
    source_files={str(path.relative_to(BATCH)):sha(path.read_bytes()) for path in RUN.rglob('*') if path.is_file()}
    rows=[];pids=set();common=read(HERE/'COMMON_NATIVE.json')
    for group in ('N','P'):
        folder=RUN/group
        row=read(folder/'PREFLIGHT_RESULT.json')
        thin=read(folder/'thin_probe/RESULT.json')
        assert thin['confirmed'] and thin['client_exit_confirmed'] and thin['runtime_exit']['confirmed']
        close=read(folder/'owner/CLOSE.json');finish=read(folder/'OWNER_FINISH.json')
        assert finish['confirmed'] and finish['exit_code']==0 and finish['close']==close
        assert close['confirmed'] and close['geometry_unchanged'] and close['asset_unchanged'] and not close['errors']
        assert close['zero_new_images_budget_met'] and close['image_construction']['status']=='not_observed_in_recorded_scope'
        assert close['native_close']['source_file_unchanged'] and close['native_close']['protected_files_unchanged']
        assert close['native_close']['exit_code']==0 and close['native_close']['process_reaped']
        assert close['worker_closed']['initial_geometry_fingerprint']==close['worker_closed']['final_geometry_fingerprint']
        helper_source=read(folder/'owner/INITIAL.json')
        final=read(folder/'owner/FINAL.json')
        assert helper_source==final==read(HERE/'SOURCE_SNAPSHOT.json')
        assert len(helper_source['objects'])==28
        replies={reply['id']:reply for reply in thin['responses']}
        tools=replies[2]['result']['tools']
        assert tools==[common]+([] if group=='N' else read(HERE/'P/PUBLIC_TOOLS.json'))
        native=helper.body(replies[3]);counts=json.loads(native['result']['result'])
        assert counts['mesh_objects']==28 and counts['scene_objects']==32 and counts['unit_scale_m']==helper_source['unit_scale_m']
        if group=='N':
            assert row['passed'] and row['errors']==[]
        else:
            # Preserve the author's original red aggregate and attribute its
            # exact assertion; no arbitrary different failure counts as pass.
            assert not row['passed'] and len(row['errors'])==1 and row['errors'][0]['type']=='AssertionError'
            assert "assert 'acquisition_invalid_triangle_structure' in json.dumps(nearest)" in row['errors'][0]['traceback']
            assert replies[4]['result']['isError'] is False
            neutral=helper.body(replies[4]);assert neutral['context']['runtime_source_sha256']==helper.CANONICAL
            assert replies[5]['result']['isError'] is True
            refusal=helper.body(replies[5])
            assert refusal['error'].startswith('BlenderHostError: acquisition_triangle_data_required:blender:')
            assert refusal['execution_authority'] is False and refusal['host_mutation_started'] is False
            assert replies[6]['result']['isError'] is False
            actual=helper.body(replies[6]);pairs=helper.compare_task_relations(actual,truth)
            identity=read(folder/'owner/PLUGIN_INITIALIZE.json')['result']['_meta']['human_eye']
            assert identity['source_kind']=='installed_distribution' and identity['source_sha256']==helper.CANONICAL
            assert identity['distribution_version']==read(BATCH/'installation/READY.json')['version']
            polygon_sizes={item['name']:sorted({len(face) for face in item['faces']}) for item in helper_source['objects']}
            assert polygon_sizes['N01']==[4]
            assert all(any(size!=3 for size in sizes) for sizes in polygon_sizes.values())
            installed=Path(read(BATCH/'installation/READY.json')['install_root'])/'human_eye_plugin/blender_host.py'
            host_source=installed.read_bytes()
            assert b'len(data.loops) != 3 * len(data.polygons)' in host_source
            assert b"raise BlenderHostError('acquisition_triangle_data_required:' + oid)" in host_source
            (OUT/'ACTUAL_THREE_RELATIONS.json').write_text(json.dumps(dict(original_result=actual,
                independently_checked_pairs=pairs,truth_sha256=sha(truth_raw)),indent=2,ensure_ascii=False)+'\n',encoding='utf8')
            (OUT/'NEAREST_SOURCE_GAP.json').write_text(json.dumps(dict(admitted=False,original_refusal=refusal,
                actual_original_polygon_sizes=polygon_sizes,installed_host_source_sha256=sha(host_source),
                source_guard='loop count must equal three times polygon count before triangle validation; this original asset has raw quads/ngons',
                no_source_normalization_or_rerun=True,geometry_queries_replayed=0),indent=2)+'\n',encoding='utf8')
        for value in (finish['actor_pid'],close.get('actor_pid'),close.get('actor_parent_pid'),
            close['native_close'].get('pid'),close['worker_closed'].get('pid'),thin.get('launcher_pid'),thin.get('runtime_pid'),
            (close.get('plugin_close') or {}).get('launcher_pid')):
            if type(value) is int:pids.add(value)
        rows.append(dict(group=group,source_snapshot_sha256=sha((folder/'owner/INITIAL.json').read_bytes()),
            native_counts=counts,thin_receipts_confirmed=True,actor_exit=finish['exit_code'],
            readonly_close_original_record=close,original_aggregate_passed=row['passed']))
    after={str(path.relative_to(BATCH)):sha(path.read_bytes()) for path in RUN.rglob('*') if path.is_file()}
    assert after==source_files
    assert all(sha(Path(name).read_bytes())==value for name,value in original['original_inputs_sha256_before'].items())
    result=dict(readonly_and_source_pipeline_passed=True,main_three_relations_match_independent_truth=True,
        nearest_applicable_to_original_source=False,original_aggregate_passed=False,original_failure_retained=True,
        actual_backend_or_geometry_replays=0,model_calls=0,new_images=0,new_assets=0,
        source_snapshot='preflight/SOURCE_SNAPSHOT.json',source_snapshot_sha256=sha((HERE/'SOURCE_SNAPSHOT.json').read_bytes()),
        recorded_pids=sorted(pids),cases=rows,source_files_sha256=source_files,
        script_sha256=sha(Path(__file__).read_bytes()),
        qualification='Postprocessing the same actual requests only. Main selected-relations task source works; the optional nearest catalogue item rejects this raw polygon asset. Producer readonly flags and snapshots do not prove absence of all transient operations.')
    (OUT/'RESULTS.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({key:result[key] for key in ('readonly_and_source_pipeline_passed','main_three_relations_match_independent_truth','nearest_applicable_to_original_source','actual_backend_or_geometry_replays')}))


if __name__=='__main__':main()
