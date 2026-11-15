"""Independent saved-geometry metrics and fresh Blender entry verification."""

import ast
from collections import deque
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'_m6rf1/batch'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
LIVE = HERE.parent/'_m6rf_live'


def read(relative):
    return json.loads((BASE/relative).read_bytes())


def loaded(path):
    with np.load(path) as data:
        return {key:data[key].copy() for key in data.files}


def recovery_counterexample():
    """Exercise the fixed save_readback control flow with a prelaunch failure."""
    tree = ast.parse((BASE/'session_api.py').read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='save_readback')
    state = dict(version=1, pending=None, current_blend='already_saved.blend')
    attempted = []
    reserved_labels = set()
    def failing_reader(directory, current, blend, label, output):
        attempted.append(dict(label=label, output=str(output)))
        if label in reserved_labels:
            raise FileExistsError('background job label retained from previous reader failure')
        reserved_labels.add(label)
        raise RuntimeError('injected failure before creating readback output directory')
    namespace = dict(Path=Path, hashlib=hashlib, session_lock=lambda d:nullcontext(),
                     read=lambda p:state.copy(), state_path=lambda d:d/'session.json', read_actual=failing_reader)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(BASE/'session_api.py'), 'exec'), namespace)
    errors = []
    for attempt in range(2):
        try:
            namespace['save_readback'](HERE/'private/empty_session')
        except (RuntimeError, FileExistsError) as error:
            errors.append(type(error).__name__)
    assert errors == ['RuntimeError','FileExistsError']
    assert attempted[0] == attempted[1]
    assert state['version']==1 and state['pending'] is None
    return dict(status='defect_reproduced', errors=errors, attempts=attempted,
                reader_substituted=True, actual_Blender_calls=0, saved_state_preserved=True)


def main():
    started = time.perf_counter()
    sessions = read('QUALITY_VERIFICATION.json')['sessions']
    specs = {r['case_id']:read('private/cases/'+r['case_id']+'/spec.json') for r in read('GEOMETRY.json')['cases']}
    results = []
    for record in sessions:
        session = record['session']
        case = session.split('_')[1]
        initial = loaded(BASE/'private/cases'/case/'initial.npz')
        after_path = BASE/'private/sessions'/session/'versions/001/independent00/readback.npz'
        actual = loaded(after_path)
        spec = specs[case]
        before, after = initial['vertices_world'], actual['vertices_world']
        direction = initial['n0']
        delta = after-before
        normal_delta = np.einsum('ij,ij->i', delta, direction)
        tangential = np.linalg.norm(delta-normal_delta[:,None]*direction, axis=1)
        I, C, center = initial['I_ids'], initial['C_ids'], spec['center_source_id']
        h = spec['h']
        outside = np.setdiff1d(np.arange(len(before)), I)
        assert np.array_equal(actual['vertices_local'][outside], initial['vertices_local'][outside])
        for field in ('poly_offsets','poly_vertices','source_ids','matrix_world'):
            np.testing.assert_array_equal(actual[field], initial[field])
        assert .95*h <= normal_delta[center] <= 1.05*h
        assert np.median(normal_delta[C]) >= .6*h
        assert np.linalg.norm(delta,axis=1).max() <= 1.1*h+spec['world_preservation_tol']
        assert tangential[I].max() <= spec['tangent_abs_tol']
        edges = initial['local_edges']
        lengths = np.linalg.norm(before[edges[:,0]]-before[edges[:,1]],axis=1)
        gradients = np.linalg.norm(delta[edges[:,0]]-delta[edges[:,1]],axis=1)/lengths
        assert gradients.max() <= spec['quality_gate']['max_gradient']
        faces = initial['faces']
        old = before[faces]
        new = after[faces]
        old_cross = np.cross(old[:,1]-old[:,0], old[:,2]-old[:,0])
        new_cross = np.cross(new[:,1]-new[:,0], new[:,2]-new[:,0])
        old_length = np.linalg.norm(old_cross,axis=1)
        new_length = np.linalg.norm(new_cross,axis=1)
        affected = np.isin(faces,I).any(axis=1)
        valid = affected & (old_length>1e-20) & (new_length>1e-20)
        assert not ((new_length<=1e-20)&(old_length>1e-20)).any()
        dot = np.einsum('ij,ij->i',old_cross,new_cross)
        assert not ((dot<=0)&valid).any()
        angles = np.degrees(np.arctan2(np.linalg.norm(np.cross(old_cross[valid],new_cross[valid]),axis=1),dot[valid]))
        assert angles.max() <= spec['quality_gate']['max_normal_change_deg']
        high = set(np.flatnonzero(normal_delta>.5*h).tolist())
        adjacency = {v:set() for v in high}
        for a,b in edges:
            if int(a) in high and int(b) in high:
                adjacency[int(a)].add(int(b));adjacency[int(b)].add(int(a))
        seen = {center};queue = deque([center])
        while queue:
            for neighbor in adjacency.get(queue.popleft(), ()):
                if neighbor not in seen:
                    seen.add(neighbor);queue.append(neighbor)
        assert high <= seen
        results.append(dict(session=session, status='passed', center_over_h=float(normal_delta[center]/h),
                            core_median_over_h=float(np.median(normal_delta[C])/h), max_gradient=float(gradients.max()),
                            maximum_face_angle_deg=float(angles.max()), outside_I_native_unchanged=True,
                            topology_preserved=True, high_region_points=len(high)))
    LIVE.mkdir(exist_ok=True)
    fresh = []
    for case in ('s01','s02'):
        session='v1_'+case+'_facts'
        source=BASE/'private/sessions'/session/'versions/001/model.blend'
        output=LIVE/(case+'.npz')
        command=[str(BLENDER),'--factory-startup','--disable-autoexec','--background',str(source),'--threads','1',
                 '--python-exit-code','23','--python',str(HERE/'blender_reader.py'),'--',
                 '--object-name',specs[case]['object_name'],'--output',str(output)]
        before=time.perf_counter()
        process=subprocess.run(command,capture_output=True)
        (LIVE/(case+'.stdout')).write_bytes(process.stdout)
        (LIVE/(case+'.stderr')).write_bytes(process.stderr)
        assert process.returncode==0, process.stderr.decode(errors='replace')
        actual=loaded(output)
        saved=loaded(BASE/'private/sessions'/session/'versions/001/independent00/readback.npz')
        for name in ('vertices_local','matrix_world','faces','poly_offsets','poly_vertices'):
            np.testing.assert_array_equal(actual[name],saved[name])
        np.testing.assert_allclose(actual['vertices_world'],saved['vertices_world'],rtol=0,atol=1e-15)
        fresh.append(dict(session=session, exit_code=process.returncode, wall_s=time.perf_counter()-before,
                          source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), all_saved_geometry_matched=True))
    result=dict(status='geometry_pass_recovery_defect_open', saved_sessions=results, fresh_Blender_reads=fresh,
                recovery_counterexample=recovery_counterexample(), wall_s=time.perf_counter()-started,
                self_intersection_scope='author exact scans and independent author AABB enumeration reviewed; root did not rerun all pair predicates',
                new_consumer_calls=0, new_training=0)
    (HERE/'RESULTS.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__=='__main__':
    main()
