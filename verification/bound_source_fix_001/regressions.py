"""Preserve raw legacy-double failures, then supply only missing RNA fields."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from verification.bound_source_fix_001.test_source_validation import enrich_data, m
from verification.test_m4_capture_001 import TriangleObject

OUT = Path(__file__).resolve().parent
LEGACY = ['verification.test_m4_capture_001', 'verification.m4_capture_opt_001.test_nine_pairs']
OTHERS = ['verification.test_blender_host_contracts', 'verification.test_selected_task_host',
          'verification.test_host_identity_contract', 'verification.test_host_forward_deadline']


def suite_run(names, name):
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (OUT/(name+'.txt')).write_bytes(stream.getvalue().encode())
    return dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                skipped=len(result.skipped), successful=result.wasSuccessful())


def main():
    previous = json.loads((OUT/'REGRESSIONS_INITIAL.json').read_bytes()) if '--complete-adapter' in sys.argv else None
    raw = previous['raw_legacy'] if previous else suite_run(LEGACY, 'LEGACY_RAW')
    real = m._acquisition_validate_triangles
    def adapted(data, **kwargs):
        enrich_data(data)
        return real(data, **kwargs)
    initial = TriangleObject.__init__
    def make_rna_double(obj, *args, **kwargs):
        initial(obj, *args, **kwargs)
        enrich_data(obj.data)
    # Generated transport code loads another product module but uses the same
    # fixture objects, so enrich at construction as well as before local calls.
    with patch.object(TriangleObject, '__init__', make_rna_double), patch.object(m, '_acquisition_validate_triangles', side_effect=adapted):
        adapted_result = suite_run(LEGACY, 'LEGACY_RNA_ADAPTED')
    other = previous['host_selected'] if previous else suite_run(OTHERS, 'HOST_SELECTED_REGRESSION')
    summary = dict(raw_legacy=raw, adapted_legacy=adapted_result, host_selected=other,
                   adapter_scope='Only missing fake RNA face/loop fields supplied; real helper always runs. No product fallback.',
                   product_changes_to_satisfy_legacy_doubles=False)
    (OUT/'REGRESSIONS.json').write_bytes((json.dumps(summary,indent=2)+'\n').encode())
    print(json.dumps(summary,indent=2))
    if not adapted_result['successful'] or not other['successful']:
        raise SystemExit(1)


if __name__=='__main__':main()
