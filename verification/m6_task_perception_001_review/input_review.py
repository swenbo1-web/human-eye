"""Bind every new alias to the previously verified current observation and label."""

import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6tp1/batch'
DATA = BASE.parent / 'data'


def main():
    started = time.perf_counter()
    old = json.loads((DATA/'DATASET_INDEX.json').read_bytes())['observations']
    current = json.loads((BASE/'INPUT_INDEX.json').read_bytes())['cases']
    truth = {r['alias']:r for r in json.loads((BASE/'SUPERVISION_INDEX.json').read_bytes())['observations']}
    meshes = {}
    for row in current:
        original = old[row['original_index']]
        entry = original['input']
        source = entry['base_mesh']
        if source not in meshes:
            with np.load(DATA/source) as data:
                meshes[source] = (data['vertices'],data['faces'])
        vertices,faces = meshes[source]
        F = np.load(DATA/entry['region_mapping'])
        expected = vertices.copy()
        with np.load(DATA/entry['current_local_positions']) as local:
            expected[F] = local['positions']
        with np.load(BASE/row['input']['path']) as data:
            assert set(data.files)=={'vertices','faces','F_source_ids'}
            np.testing.assert_array_equal(data['vertices'],expected)
            np.testing.assert_array_equal(data['faces'],faces)
            np.testing.assert_array_equal(data['F_source_ids'],F)
        with np.load(DATA/original['supervision']) as old_label, np.load(BASE/truth[row['alias']]['path']) as new_label:
            np.testing.assert_array_equal(new_label['mask'],old_label['changed_mask'])
    result=dict(status='passed',current_inputs=len(current),masks=len(current),source_arrays=len(meshes),
                current_input_whitelist=['vertices','faces','F_source_ids'],wall_s=time.perf_counter()-started)
    (HERE/'INPUT_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()
