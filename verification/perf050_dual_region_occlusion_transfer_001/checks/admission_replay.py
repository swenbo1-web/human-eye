"""Exercise this batch's real admission and closure paths on prior sealed receipts."""

import argparse
import importlib.util
import json
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory


NS = Path(__file__).resolve().parents[1]
REUSED = NS.parent/'perf050_source_scope_rank_transfer_recovery_001/checks/admission_replay.py'


def main(output):
    retained = run_path(str(REUSED))
    retained['run_sequence'].__globals__['NS'] = NS
    experiment = run_path(str(NS/'experiment.py'))
    closure_file = NS/'harness/closure.py'
    spec = importlib.util.spec_from_file_location('_dual_qualification_closure_replay',closure_file)
    closure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(closure)
    originals, images, pins = retained['fixtures']()
    # Reuse known closed native/MCP receipts only to qualify the control flow.
    # Their historical images do not score this task or enter its model workspace.
    with TemporaryDirectory(prefix='dual_region_admission_replay_') as temporary:
        root = Path(temporary).resolve()
        record = {'passed':True,'provenance':'read-only offline process and gate replay using archived known close receipts',
            'Blender_starts':0,'model_starts':0,
            'original_close_checks':retained['raw_close'](closure,originals),
            'failed_qualification_gate':retained['run_sequence'](experiment,root/'stopped',originals,images,fail=True),
            'passed_qualification_gate':retained['run_sequence'](experiment,root/'accepted',originals,images,fail=False),
            'formal_rejection_controls':retained['failed_formal_gate'](experiment,root/'formal_rejection',originals,images),
            'pins':[*pins,*[retained['pin'](file) for file in (REUSED,Path(__file__),closure_file,NS/'experiment.py',NS/'harness/admission.py')]]}
    with output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(record,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print('Offline closure and current admission replay verified',retained['pin'](output)['sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    main(parser.parse_args().output.resolve())
