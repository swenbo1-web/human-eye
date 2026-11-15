import hashlib, json, pathlib, zipfile

root = pathlib.Path('D:/he_source_face_001/preparation/Q01')
out = pathlib.Path('D:/hefe/verification/fixes/20261115_m1_source_face_001_review/code_identity')
checks = []
def check(label, ok):
    checks.append({'label': label, 'passed': bool(ok)})
def read(path):
    return json.loads(pathlib.Path(path).read_bytes())
def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

a = read(root / 'QA/o/product_call_01/SERVICE_RESULT.json')
b = read(root / 'QB/o/product_call_01/SERVICE_RESULT.json')
check('same full patch source map', a['facts']['scope']['patch_support'] == b['facts']['scope']['patch_support'])
check('same selected view count', len(a['frames']) == len(b['frames']) == 3)
views = []
member_count = 0
for left, right in zip(a['frames'], b['frames']):
    view = left['view_name']
    views.append(view)
    check(view + ' identity', view == right['view_name'])
    for side, frame in [('A',left), ('B',right)]:
        for kind in ['image','arrays']:
            check(view + side + kind + ' digest', digest(frame[kind + '_path']) == frame[kind + '_sha256'])
    check(view + ' PNG exact bytes', pathlib.Path(left['image_path']).read_bytes() == pathlib.Path(right['image_path']).read_bytes())
    with zipfile.ZipFile(left['arrays_path']) as lzip, zipfile.ZipFile(right['arrays_path']) as rzip:
        check(view + ' NPZ members', set(lzip.namelist()) == set(rzip.namelist()))
        for name in lzip.namelist():
            member_count += 1
            check(view + ':' + name, lzip.read(name) == rzip.read(name))
q = read(root / 'QUALIFICATION_RUN.json')
check('one qualification attempt zero retries', q['attempt'] == 1 and q['outer_retries'] == 0 and q['prior_attempts'] == 0)
result = {'passed': all(c['passed'] for c in checks), 'checks':len(checks), 'failures':[c for c in checks if not c['passed']], 'views':views, 'compared_npy_members':member_count, 'new_product_model_Blender_raster_calls':0, 'scope':'Saved qualification A/B files only; compressed container metadata is not an array-value change.'}
with (out / 'SUPPLEMENT.json').open('x', encoding='utf8', newline='\n') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False))
