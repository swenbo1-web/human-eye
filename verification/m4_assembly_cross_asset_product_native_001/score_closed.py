"""Re-adjudicate unchanged formal answers after the frozen scorer's domain error."""

import inspect
import json
from pathlib import Path
from runpy import run_path
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
BATCH = run_path(str(HERE/'experiment.py'))
SCORE = run_path(str(HERE/'score.py'))
RUN = BATCH['RUN']
pin, read, require, write = (BATCH[k] for k in ('pin','read','require','write'))
SKIPPED = {f'{region}.{item}' for region in ('N19','N25')
           for item in ('counts','direction','image','pixel','scope')}


def corrected_checks():
    """Adapt the old coordinate lookup and the path-typed producer loader."""
    old = SCORE['OLD']
    legacy = old.check_claim
    original = inspect.getsource(legacy)
    line = "    binary = geometry['matrix64_regions'][region]\n"
    require(original.count(line) == 1, 'retained_claim_lookup_changed')
    text = original.replace(line, "    binary = geometry['matrix64_regions'][region] if criterion in ('distance','nearest_pair') else None\n")
    namespace = dict(legacy.__globals__)
    exec(compile(text,inspect.getsourcefile(legacy),'exec'),namespace)
    legacy = SimpleNamespace(**{**vars(old),'check_claim':namespace['check_claim']})
    check = old.with_replacements(SCORE['check_claim'],OLD=legacy)
    frame = SCORE['frame_source_binding']
    frame_source = inspect.getsource(frame)
    line = "    producer = load(report['path'])\n"
    require(frame_source.count(line) == 1, 'retained_producer_loader_changed')
    frame_scope = dict(frame.__globals__)
    fixed_frame_source = frame_source.replace(line, "    producer = load(Path(report['path']))\n")
    exec(compile(fixed_frame_source,inspect.getsourcefile(frame),'exec'),frame_scope)
    frames = old.with_replacements(SCORE['qualify_frames'],frame_source_binding=frame_scope['frame_source_binding'])
    return check, old.with_replacements(SCORE['score_slot'],check_claim=check,qualify_frames=frames)


def compare_after_close():
    freeze = BATCH['verify_freeze'](BATCH['FROZEN'])
    journal = RUN/'FORMAL_SEQUENCE.jsonl'
    sequence = [json.loads(line) for line in journal.read_bytes().splitlines()]
    labels = ('N1','P1')
    require([(row['event'],row['label']) for row in sequence] ==
            [(event,label) for label in labels for event in ('start','exit')], 'original_pair_not_complete')
    check, score = corrected_checks()
    results = {}
    for index,label in enumerate(labels):
        start,end = sequence[2*index:2*index+2]
        slot = RUN/'slots'/label
        require(start['freeze_sha256'] == freeze and end['publication'] == pin(slot/'SLOT_PUBLICATION.json')
                and end['exit_code'] == 0 and end['status'] == 'completed' and end['safe_to_continue'],
                'original_slot_not_closed_under_freeze/'+label)
        original_path = RUN/'score'/f'{label}_SCORE.json'
        claims_path = RUN/'score'/f'{label}_CLAIMS.json'
        before = read(original_path)
        criteria = before.get('criteria',{})
        failures = {key for key,row in criteria.items() if row['status'] != 'pass'}
        if label == 'N1':
            require(failures == SKIPPED and before['passed_items'] == 7 and
                    all(criteria[key].get('reason') == repr('matrix64_regions') for key in failures),
                    'original_native_score_has_a_different_failure')
        else:
            require(before['error_type'] == 'AttributeError'
                    and before['error'] == "'str' object has no attribute 'read_bytes'"
                    and before['claims_sha256'] == pin(claims_path)['sha256']
                    and before['frozen_scorer_sha256'] == pin(HERE/'score.py')['sha256']
                    and before['slot_result_sha256'] == pin(slot/'SLOT_RESULT.json')['sha256']
                    and not before['original_cli_receipt_written_by_scorer'],
                    'original_plugin_score_has_a_different_failure')
            failures = set(SCORE['REQUIRED'])
        after = score(slot,claims_path)
        require(after.get('quality_complete') is True and after['passed_items'] == after['total_items'] == 17
                and all(after['criteria'][key] == row for key,row in criteria.items() if key not in failures),
                'derived_correction_does_not_preserve_original_passes/'+label)
        answer = (slot/'consumer/PUBLIC_FINAL.txt').read_text(encoding='utf8')
        claims = read(claims_path)['claims']
        controls = {
            'N19.direction': {'world_unit_direction':[-1,0,0]},
            'N19.image': {'local_image_path':str(slot/'absent.png')},
            'N25.pixel': {'current_object_local_triangle':1_000_000},
        }
        rejected = {}
        for criterion,variation in controls.items():
            try:
                check(criterion,{**claims[criterion],**variation},answer,after['same_slot_geometry'],
                      after['usable_frames'],claims)
            except ValueError as error:
                rejected[criterion] = str(error)
            else:
                raise ValueError('false_direction_path_or_pixel_admitted/'+label+'/'+criterion)
        after['closed_rescore'] = {'original_score':pin(original_path),'original_unjudged_items':sorted(failures),
                                  'claim_source':pin(claims_path),'formal_sequence':pin(journal),
                                  'freeze_sha256':freeze,'rejected_controls':rejected}
        target = RUN/'score'/f'{label}_DERIVED_SCORE.json'
        require(not target.exists(), 'derived_result_already_exists/'+label)
        write(target,after)
        results[label] = after['passed_items']
    print(results,flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    compare_after_close()
