"""Unwrap sealed receipt envelopes for the frozen scorer without changing the seals."""

import argparse
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def project(seals, destination):
    destination.mkdir(parents=True, exist_ok=False)
    originals = {}
    projections = {}
    for name, key in (('ANSWERS_SEALED.json', 'answers'), ('FIRST_PACKETS_SEALED.json', 'first_packets')):
        source, target = seals / name, destination / name
        blob = source.read_bytes()
        document = json.loads(blob)
        for row in document[key]:
            if key == 'answers':
                row.setdefault('original_path', None)
            elif row.get('original_rpc_receipt') is not None:
                wrapper = row['original_rpc_receipt']
                verify.require('receipt' in wrapper, 'original RPC receipt has no nested wire receipt')
                row['original_rpc_receipt'] = wrapper['receipt']
        write(target, document)
        originals[name] = {'path': str(source), 'sha256': verify.sha(blob)}
        projections[name] = {'path': str(target), 'sha256': verify.sha(target.read_bytes())}
    return {'originals': originals, 'projections': projections,
            'differences': ['project FIRST_PACKETS_SEALED.original_rpc_receipt.receipt',
                            'supply explicit null original_path when the answer seal records no original']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    projection = args.runtime / 'scoring_seal_projection'
    receipt = project(HERE.parent, projection)
    frozen = verify.fixed.fixed_inputs()['second_assembly']['meshes']
    verdict = verify.inspect(args.runtime, projection, frozen)
    verdict['seal_projection'] = receipt
    verdict['frozen_scorer_sha256'] = verify.sha((HERE / 'verify.py').read_bytes())
    write(args.output, verdict)
