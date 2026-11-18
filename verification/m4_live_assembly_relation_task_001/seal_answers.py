"""Bind both original slot outcomes before opening either final answer."""

from pathlib import Path
import sys
import time

NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import EXTERNAL, read, save, sha


def main():
    started = time.perf_counter_ns()
    outcomes = []
    for label in ('N1', 'P1'):
        folder = EXTERNAL / 'slots' / label
        result_file = folder / 'SLOT_RESULT.json'
        publication = read(folder / 'SLOT_PUBLICATION.json')
        result = read(result_file)
        if label != result['slot'] or sha(result_file) != publication['result_sha256']:
            raise ValueError('published_slot_identity_mismatch')
        row = {'slot': label, 'status': result['status'], 'slot_result_sha256': sha(result_file),
               'published_ns': publication['published_ns'], 'path': None, 'sha256': None, 'bytes': None}
        answer = result.get('answer')
        if answer is None:
            row['reason'] = 'original_slot_published_without_final_answer'
        else:
            original = folder / 'consumer/PUBLIC_FINAL.txt'
            raw = original.read_bytes()
            if sha(original) != answer['sha256'] or len(raw) != answer['bytes']:
                raise ValueError('original_final_identity_mismatch')
            copy = NS / 'answers' / (label + '.txt')
            copy.parent.mkdir(exist_ok=True)
            with copy.open('xb') as stream:
                stream.write(raw)
            row.update(path=str(copy), original_path=str(original), sha256=sha(copy), bytes=len(raw))
        outcomes.append(row)
    save(NS / 'ANSWERS_SEALED.json', {'started_ns': started, 'sealed_ns': time.perf_counter_ns(),
         'answers': outcomes, 'replacement_consumers': 0,
         'meaning': 'Original pair preserved before content scoring.'})


if __name__ == '__main__':
    main()
