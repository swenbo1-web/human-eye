"""Prepare the predeclared binary32-exact, separate Blender QA fixture.

This module uses only the standard library. It never imports the engine or
Blender. The controller invokes prepare before freezing the actual run.
"""

import argparse
import hashlib
import json
import struct
from fractions import Fraction
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'm4_active_observation_core_integration_001/inputs/scene_grid16_permuted_alternating.json'
SOURCE_SHA256 = 'a1996369aa5808dca7f049a2701ae9b9d0d64e7890879618e8ee44bad6cb3fdc'
SCALE = Fraction(375, 256)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8')


def prepare(output_directory):
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256
    scene = json.loads(raw)
    count = 0
    max_numerator_bits = 0
    for obj in scene['objects']:
        for vertex in obj['vertices']:
            for axis, text in enumerate(vertex):
                value = Fraction(text) * SCALE
                actual = struct.unpack('<f', struct.pack('<f', float(value)))[0]
                assert Fraction.from_float(actual) == value
                vertex[axis] = str(value)
                count += 1
                max_numerator_bits = max(max_numerator_bits, abs(value.numerator).bit_length())
    assert count == 5730 and len(scene['objects']) == 28
    scene['scope'] = 'Separate temporary QA fixture. Every original coordinate is multiplied exactly by 375/256 before Blender creation.'
    fixture_raw = encoded(scene)
    fixture = output / 'QA_GEOMETRY.json'
    fixture.write_bytes(fixture_raw)
    result = {
        'schema': 'm4-host-bridge-qa-fixture-v1',
        'source': str(SOURCE.resolve()), 'source_sha256': SOURCE_SHA256,
        'fixture': str(fixture), 'fixture_sha256': hashlib.sha256(fixture_raw).hexdigest(),
        'scale': str(SCALE), 'coordinates_checked': count,
        'all_coordinates_binary32_exact': True, 'max_scaled_numerator_bits': max_numerator_bits,
        'objects': len(scene['objects']),
        'vertices': sum(len(obj['vertices']) for obj in scene['objects']),
        'triangles': sum(len(obj['triangles']) for obj in scene['objects']),
        'object_matrices': 'identity', 'unit_system': 'METRIC', 'scale_length': 1.0,
        'new_Blender_processes': 0, 'new_rasters': 0, 'product_calls': 0,
        'nonplanar_control': {
            'name': 'QA_NonPlanar',
            'vertices': [['0', '0', '0'], ['1', '0', '0'], ['1', '1', '1/256'], ['0', '1', '0']],
            'triangles': [[0, 1, 2], [0, 2, 3]],
        },
        'rename_control': {'from': scene['objects'][0]['name'], 'to': 'QA_Renamed_' + scene['objects'][0]['name']},
    }
    (output / 'FIXTURE.json').write_bytes(encoded(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), sort_keys=True))
