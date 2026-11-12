"""Run synthetic quality and archive regressions; formal answers remain unscored."""

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import traceback
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    attempts = HERE/'attempts'
    attempts.mkdir(exist_ok=True)
    index = 1
    while (attempts/f'run_{index:02d}').exists():
        index += 1
    output = attempts/f'run_{index:02d}'
    output.mkdir()
    sources = [HERE/name for name in ('score_answer.py','test_score_answer.py',
        'test_pack_bindings.py','test_compact_contract.py','check_packager.py','SCORING_CONTRACT.json')]
    sources.append(HERE.parent/'runtime/pack_quality.py')
    before = {str(path):sha(path) for path in sources}
    stream = io.StringIO()
    began = time.perf_counter_ns()
    error = None
    result = None
    archive = None
    try:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite(loader.loadTestsFromModule(load('_quality_test_'+str(i), HERE/name))
            for i,name in enumerate(('test_score_answer.py','test_pack_bindings.py','test_compact_contract.py')))
        result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        checker = load('_quality_synthetic_archiver',HERE/'check_packager.py')
        with patch.object(sys,'argv',['check_packager',f'synthetic_{index:02d}']),redirect_stdout(stream):
            archive_exit = checker.main()
        archive = json.loads((HERE/f'synthetic_{index:02d}/RESULTS.json').read_bytes())
        assert archive_exit == 0 and archive['passed'], 'synthetic archive checks failed'
    except BaseException:
        error = traceback.format_exc()
        stream.write(error)
    unchanged = all(sha(Path(path)) == digest for path,digest in before.items())
    record = {'schema':'nine_slot_quality_offline_regressions_v1','attempt':index,
        'successful':error is None and result is not None and result.wasSuccessful() and unchanged,
        'unittest_methods':0 if result is None else result.testsRun,
        'failures':[] if result is None else [{'test':test.id(),'traceback':message} for test,message in result.failures],
        'errors':[] if result is None else [{'test':test.id(),'traceback':message} for test,message in result.errors],
        'skipped':[] if result is None else [test.id() for test,_ in result.skipped],
        'unexpected_error':error,'source_unchanged':unchanged,'source_sha256':before,
        'archive_checks':None if archive is None else len(archive['checks']),
        'archive_pass':None if archive is None else archive['passed'],
        'elapsed_ns':time.perf_counter_ns()-began,'formal_answers_scored':0,
        'new_model_Blender_product_API_runs':0,
        'AL_binding':{'context_bound':False,'host_epoch':5,'rebind_required':True},
        'scope':'Synthetic records and frozen representation fixtures only; no formal-run scoring or group analysis.'}
    (output/'STDOUT.txt').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    (output/'RESULT.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({key:record[key] for key in ('successful','attempt','unittest_methods','archive_checks','archive_pass','unexpected_error')}))
    return 0 if record['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
