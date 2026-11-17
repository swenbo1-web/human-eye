"""Seal all three original public answers before any content scoring."""

import hashlib
import json
import os
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m1_source_region_facts_first_001')


def main():
    started = time.perf_counter_ns()
    rows = []
    assert sorted(path.name for path in (RUNTIME / 'slots').iterdir()) == ['S1', 'S2', 'S3']
    for case in ('S1', 'S2', 'S3'):
        folder = RUNTIME / 'slots' / case
        publication = json.loads((folder / 'SLOT_PUBLICATION.json').read_bytes())
        result = json.loads((folder / 'SLOT_RESULT.json').read_bytes())
        assert publication['case_id'] == result['case_id'] == case
        original = folder / 'consumer/PUBLIC_FINAL.txt'
        raw = original.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert result['answer']['sha256'] == digest
        copy = HERE / 'answers' / (case + '.txt')
        copy.parent.mkdir(exist_ok=True)
        with copy.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        rows.append({'case_id': case, 'original_path': str(original), 'copy_path': str(copy),
                     'sha256': digest, 'bytes': len(raw), 'slot_status': result['status'],
                     'publication_sha256': hashlib.sha256((folder / 'SLOT_PUBLICATION.json').read_bytes()).hexdigest()})
    value = {'task': 'M1-SOURCE-REGION-FACTS-FIRST-001', 'started_ns': started,
             'sealed_ns': time.perf_counter_ns(), 'answers': rows,
             'real_consumers': 3, 'replacement_consumers': 0,
             'scoring_started_before_all_answers_sealed': False}
    with (HERE / 'ANSWERS_SEALED.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'sealed_original_answers': len(rows), 'real_consumers': 3, 'replacements': 0}))


if __name__ == '__main__':
    main()
