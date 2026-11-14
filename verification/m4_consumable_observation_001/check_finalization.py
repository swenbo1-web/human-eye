"""Four literal-only finalizer checks. No CLI, product, model or image work."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    def guard(event, values):
        if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.spawn',
                     'socket.connect', 'socket.bind'):
            raise RuntimeError('forbidden_in_literal_finalizer_check:' + event)
        if event == 'import' and str(values[0]).split('.')[0] in ('human_eye_plugin', 'numpy', 'PIL', 'bpy'):
            raise RuntimeError('forbidden_product_or_image_import:' + str(values[0]))

    sys.addaudithook(guard)
    path = HERE / 'launcher.py'
    specification = importlib.util.spec_from_file_location('_literal_finalizer_launcher', path)
    launcher = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(launcher)
    cases = []
    for case in ('success', 'ordinary_failed_route', 'route_exception', 'postcheck_exception'):
        folder = output / case
        folder.mkdir()
        calls = []
        row = {'outer_valid_completion': case != 'ordinary_failed_route',
               'consumer_pid': None, 'observed_thread_id': None,
               'literal_fixture': case}

        def route():
            calls.append('route')
            if case == 'route_exception':
                raise ValueError('literal_route_failure_preserved')
            return row

        retained_route = route
        retained_code = route.__code__

        def postcheck():
            calls.append('postcheck')
            constants_retained_after_route = list(route.__code__.co_consts)
            assert route is retained_route and route.__code__ is retained_code
            assert constants_retained_after_route == list(retained_code.co_consts)
            if case == 'postcheck_exception':
                raise RuntimeError('literal_postcheck_failure_preserved')
            return {'literal_only': True, 'same_function_reference': True, 'same_code_reference': True}

        caught = None
        returned = None
        try:
            returned = launcher.execute_and_finalize(route, postcheck, folder,
                {'literal_fixture': case, 'new_model_sessions': 0, 'new_raster_attempts': 0})
        except (ValueError, RuntimeError) as error:
            caught = {'type': type(error).__name__, 'message': str(error)}
        result = json.loads((folder / 'RUN_RESULT.json').read_bytes())
        launch = json.loads((folder / 'LAUNCH_RESULT.json').read_bytes())
        timing = json.loads((folder / 'LAUNCH_TIMING.json').read_bytes())
        expected_phase = {'route_exception': 'route', 'postcheck_exception': 'post_route_checks'}.get(case)
        expected_success = case == 'success'
        assert calls == ['route', 'postcheck']
        assert result['launcher_succeeded'] is expected_success
        assert launch['launcher_succeeded'] is expected_success
        assert result['records'] == ([] if case == 'route_exception' else [row])
        if case != 'route_exception':
            expected_route_state = 'failed' if case == 'ordinary_failed_route' else 'completed'
            assert result['records'][0]['execution_state'] == expected_route_state
        assert [item['phase'] for item in result['terminal_errors']] == ([] if expected_phase is None else [expected_phase])
        assert launch['terminal_errors'] == result['terminal_errors'] == timing['terminal_errors']
        assert timing['publication_errors'] == []
        assert timing['started_ns'] <= timing['route_started_ns'] <= timing['route_closed_ns'] <= timing['launch_results_closed_ns']
        assert timing['elapsed_ns'] == timing['launch_results_closed_ns'] - timing['started_ns']
        assert timing['route_elapsed_ns'] == timing['route_closed_ns'] - timing['route_started_ns']
        if expected_phase is None:
            assert caught is None and returned == result
        else:
            expected_type = 'ValueError' if case == 'route_exception' else 'RuntimeError'
            expected_message = 'literal_route_failure_preserved' if case == 'route_exception' else 'literal_postcheck_failure_preserved'
            assert caught == {'type': expected_type, 'message': expected_message}
        cases.append({'case': case, 'passed': True, 'caught': caught,
                      'route_calls': calls.count('route'), 'postcheck_calls': calls.count('postcheck'),
                      'published': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                                    for name in ('RUN_RESULT.json', 'LAUNCH_RESULT.json', 'LAUNCH_TIMING.json')}})
    result = {'schema': 'consumable-observation-literal-finalization-check-v1', 'passed': True,
              'cases': cases, 'new_model_sessions': 0, 'new_CLI_processes': 0,
              'new_actor_processes': 0, 'new_raster_attempts': 0, 'new_image_constructions': 0,
              'launcher_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'check_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Literal route returns/exceptions only; no accepted execution chain or product function called.'}
    launcher.save(output / 'RESULTS.json', result, exclusive=True)
    print(json.dumps({'passed': result['passed'], 'cases': len(cases), 'output': str(output)}))


if __name__ == '__main__':
    main()
