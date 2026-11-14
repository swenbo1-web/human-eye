"""Reproduce only the deepest saved repair's endpoint contact result."""
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
SNAP = HERE/'snapshot'
PRIVATE = SNAP/'verification/m6_shape_pairs_001/private'
labels = json.loads((PRIVATE/'LABELS.json').read_bytes())
saved = json.loads((PRIVATE/'sample_06_repair_contact.json').read_bytes())
observed = np.load(PRIVATE/'sample_06_abnormal.npy', allow_pickle=False)
after = np.load(PRIVATE/'sample_06_repaired.npy', allow_pickle=False)
triangles = np.load(PRIVATE/'triangles.npy', allow_pickle=False)
spec = importlib.util.spec_from_file_location('fixed_contact002', SNAP/'verification/m6_coupled_probe_002/evaluate.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
packet = {'state': {'source_id': 'shape-pairs-observed/'+hashlib.sha256(observed.tobytes()).hexdigest(), 'frame': 1, 'coordinate_frame': 'saved_world_binary64_m'},
          'vertices_before': observed.tolist(), 'vertices_candidate': after.tolist(), 'triangles': triangles.tolist(),
          'write_ids': labels['region_ids'], 'target_vertices': None, 'protected_ids': [],
          'shape_tolerance_m': 0., 'preservation_tolerance_m': 0., 'require_no_new_intersections': True}
started = time.perf_counter()
value,_,_ = module.evaluate(packet)
serial = module.serializable_result(value)
fields = ['affected_face_ids','contact_complete','contact_ok','shape_ok','before_pairs','after_pairs','new_pairs','removed_pairs','changed_relations']
for key in fields:
    assert serial[key] == saved[key], key
checks = ['same '+key for key in fields]
for stage in ['before_scan','after_scan']:
    for key in ['scan_complete','spatial_candidates','exact_tests','unknown_pairs','degenerate_face_ids']:
        assert serial[stage][key] == saved[stage][key], stage+'/'+key
        checks.append('same '+stage+'/'+key)
summary={'fixed_delivery':'9b016c8720b709a6382438ddd505c7b154d4fac2','case':'sample_06','stage':'observed_to_saved_broad_repair','checks':checks,'check_count':len(checks),'endpoint_queries':2,'contact_complete':value['contact_complete'],'contact_ok':value['contact_ok'],'shape_ok':value['shape_ok'],'affected_faces':len(value['affected_face_ids']),'new_pairs':len(value['new_pairs']),'exact_pair_attempts':sum(value[s]['exact_tests'] for s in ['before_scan','after_scan']),'wall_s':time.perf_counter()-started,'oracle_result':False,'limits':'Finite endpoint surface intersections only. Shape target omitted in this isolated contact evaluation; not a passed shape repair.'}
(HERE/'CONTACT_REPLAY.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(summary))
