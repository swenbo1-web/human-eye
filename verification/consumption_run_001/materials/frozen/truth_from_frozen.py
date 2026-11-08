"""Four existing assets, exact analytic witnesses; no product algorithm imports."""
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
QA=ROOT/'verification/m4_capture_qa_001'
CASES=[('T01','all_overlap'),('T02','peripheral'),('T03','equal_ties'),('T04','degenerate')]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fraction(value):
    assert type(value) in (int,float) and math.isfinite(value)
    return F(value)
def rational(value):return dict(numerator=str(value.numerator),denominator=str(value.denominator))
def save(path,value):Path(path).write_bytes((json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode())


def main():
    (OUT/'admin').mkdir(exist_ok=True)
    assets_path=QA/'run_01/assets/ASSETS.json'
    assets=json.loads(assets_path.read_bytes())
    seal=json.loads((QA/'DELIVERY_MANIFEST.json').read_bytes())
    sealed={row['path']:row for row in seal['files']}
    assert digest(assets_path)==sealed['run_01/assets/ASSETS.json']['sha256']
    sources=[];answers=[];prompts=[]
    for task,case in CASES:
        index,row=next((i,row) for i,row in enumerate(assets['cases']) if row['case']==case)
        asset=Path(row['asset']);assert digest(asset)==row['sha256']
        recipe=row['recipe']
        assert hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()==row['recipe_sha256']
        raw_path=QA/'run_01'/('case_%02d_'%index+case)/'full_RAW.json'
        relative=raw_path.relative_to(QA).as_posix();assert digest(raw_path)==sealed[relative]['sha256']
        config_path=raw_path.parent/'owned/CONFIG.json'
        config=json.loads(config_path.read_bytes())
        assert config['asset_sha256']==row['sha256'] and Path(config['asset']).resolve()==asset.resolve()
        assert digest(config['asset_copy'])==row['sha256']
        # Only native geometry is used, never the neighbouring M3 result fields.
        scene=json.loads(raw_path.read_bytes())['payload']
        assert scene['unit']=='m' and scene['coordinate_frame']=='world'
        meshes={mesh['name']:mesh for mesh in scene['meshes']}
        assert set(meshes)=={obj['name'] for obj in recipe['objects']}
        assert fraction(recipe['scale_length'])==1
        exact={}
        for obj in recipe['objects']:
            mesh=meshes[obj['name']];matrix=[[fraction(v) for v in r] for r in obj['matrix']]
            assert [[matrix[r][c] for c in range(3)] for r in range(3)]==[[F(int(r==c)) for c in range(3)] for r in range(3)]
            world=[tuple(sum(matrix[r][c]*fraction(point[c]) for c in range(3))+matrix[r][3] for r in range(3)) for point in obj['vertices']]
            raw_world=[tuple(fraction(v) for v in point) for point in mesh['vertices']]
            assert world==raw_world and mesh['faces']==obj['faces']
            assert all(len(face)==3 and all(type(i) is int and 0<=i<len(world) for i in face) for face in mesh['faces'])
            used={i for face in mesh['faces'] for i in face}
            xs={world[i][0] for i in used};assert len(xs)==1
            origin_index=next(i for i in sorted(used) if world[i][1:]==(F(0),F(0)))
            face_index=next(i for i,face in enumerate(mesh['faces']) if origin_index in face)
            exact[obj['name']]=dict(x=next(iter(xs)),point=world[origin_index],vertex_index=origin_index,face_index=face_index)
        focal=exact['M4_Focal'];assert focal['x']==0
        pair_rows=[]
        for name,geometry in exact.items():
            if name=='M4_Focal':continue
            distance=abs(geometry['x']-focal['x'])
            # Lower: every indexed triangle convex combination has fixed x.
            # Upper: two referenced vertices at the same y,z attain that gap.
            assert sum((a-b)**2 for a,b in zip(geometry['point'],focal['point']))==distance**2
            pair_rows.append(dict(name=name,object_id=meshes[name]['object_id'],distance_m=rational(distance),
                                  squared_distance_m2=rational(distance**2),distance_decimal=float(distance),
                                  focal_vertex=focal['vertex_index'],target_vertex=geometry['vertex_index'],
                                  focal_face=focal['face_index'],target_face=geometry['face_index'],
                                  lower_bound='constant-x plane separation over all referenced face points',
                                  attaining_upper_bound='actual referenced vertices with identical y=z=0'))
        best=min(F(r['distance_m']['numerator'])/F(r['distance_m']['denominator']) for r in pair_rows)
        nearest=sorted(r['name'] for r in pair_rows if F(r['distance_m']['numerator'])/F(r['distance_m']['denominator'])==best)
        tri=[tuple(fraction(x) for x in meshes['M4_Focal']['vertices'][i]) for i in meshes['M4_Focal']['faces'][0]]
        u,v=[tuple(tri[j][k]-tri[0][k] for k in range(3)) for j in (1,2)]
        degenerate=not any(u[i]*v[j]-u[j]*v[i] for i,j in ((0,1),(0,2),(1,2)))
        source=dict(task_id=task,case=case,asset_path=str(asset),asset_sha256=row['sha256'],
                    recipe_sha256=row['recipe_sha256'],raw_path=str(raw_path),raw_sha256=digest(raw_path),
                    owned_config_sha256=digest(config_path),old_private_copy_matches_original=True,
                    raw_bytes=raw_path.stat().st_size,objects=len(meshes),vertices=sum(len(m['vertices']) for m in meshes.values()),
                    faces=sum(len(m['faces']) for m in meshes.values()),focal_name='M4_Focal',
                    raw_matches_sealed_prior_QA=True,recipe_world_equals_raw_exactly=True)
        sources.append(source)
        answers.append(dict(task_id=task,minimum_distance_m=rational(best),minimum_distance_decimal=float(best),
                     nearest_names=nearest,clearance_3mm_met=best>=F(3,1000),pairs=pair_rows,
                     geometric_truth_exists=True,focal_first_face_degenerate=degenerate,
                     geometry_semantics='union of closed convex hulls of indexed triangles, including degenerate point/segment hulls',
                     proof_algorithm='exact rational constant-coordinate lower bound plus referenced-point attaining witness; not product M3'))
        prompt=(f'任务 {task}。只观察当前已打开的场景，不移动、不编辑、不保存。以 M4_Focal 为焦点，找出其与场景中所有其他网格的最小无符号几何距离，并列出全部并列最近对象。'
                '每个三角面按其三个顶点的闭凸包处理；退化面保留实际点或线段集合。判断这个最小距离是否至少为0.003米；这只是表面间距判定，不代表实体安全、可移动或修复建议。'
                '名称只作标识，不表示远近。根据本次真实读取作答；必要时可用本轮通用原生读取补查。若仍有会影响结论的未决对象，明确保留unknown，不把它说成全场满足。'
                '输出JSON：task_id、nearest_names（全部名称或null）、minimum_distance_m（数字或null）、clearance_3mm（met/not_met/unknown）、coverage（complete/partial/unknown）、unresolved（对象和原因）、basis（一句几何依据）。')
        prompts.append(dict(task_id=task,prompt=prompt,prompt_utf8_sha256=hashlib.sha256(prompt.encode()).hexdigest()))
    assert len(answers)==4 and len(answers[0]['nearest_names'])==5
    assert answers[1]['nearest_names']==['M4_Near'] and answers[2]['nearest_names']==['M4_Near','M4_Tie']
    assert answers[3]['focal_first_face_degenerate'] and answers[3]['nearest_names']==['M4_Near']
    assert [a['clearance_3mm_met'] for a in answers]==[False,True,True,True]
    save(OUT/'admin/TRUTH.json',dict(status='static_truth_prepared_not_model_results',tasks=answers))
    save(OUT/'admin/ASSET_INDEX.json',dict(assets_manifest_sha256=digest(assets_path),prior_seal_sha256=digest(QA/'DELIVERY_MANIFEST.json'),tasks=sources))
    save(OUT/'consumer_prompts.json',dict(status='questions_only_no_answer_key',tasks=prompts))
    save(OUT/'STATIC_CHECKS.json',dict(task_count=4,all_source_and_fraction_assertions_passed=True,
                                    product_imports=0,blender=0,RPC=0,render=0,model_consumers=0,performance_samples=0))
    print(json.dumps([dict(task_id=a['task_id'],nearest_names=a['nearest_names'],distance=a['minimum_distance_decimal'],degenerate=a['focal_first_face_degenerate']) for a in answers],ensure_ascii=False))


if __name__=='__main__':main()
