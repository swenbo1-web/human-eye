"""Root read-only Git/manifest/PNG binding audit; no candidate execution."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
PREFIX = 'verification/m4_active_coverage_001/'
BATCH = AUTHOR / PREFIX
COMMIT = 'bfcc35e32aab0b724261a5140fc5d05df9ddad48'
checks = []

def check(name, condition, detail=None):
    checks.append({'name': name, 'passed': bool(condition), 'detail': detail})

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def git(*args, data=None):
    return subprocess.run(['git', *args], cwd=AUTHOR, input=data, capture_output=True, check=True).stdout

def read(path):
    return json.loads(Path(path).read_bytes())

manifest_path = BATCH / 'CONTENT_MANIFEST.json'
manifest = read(manifest_path)
check('delivery_manifest_sha', sha(manifest_path.read_bytes()) == 'f107617a7eb444bfdadc315672f44de19108ed057a9235a19c4b829dfe90e824')
check('author_head', git('rev-parse', 'HEAD').decode().strip() == COMMIT)
check('author_tracked_clean', not git('status', '--porcelain', '--untracked-files=no'))
entries = {}
for line in git('ls-tree', '-r', '-z', COMMIT, '--', PREFIX).split(b'\0'):
    if not line:
        continue
    metadata, name = line.split(b'\t', 1)
    entries[name.decode()] = metadata.split()[2].decode()
rows = manifest['files']
listed = {row['path'] for row in rows}
expected = listed | {PREFIX + 'CONTENT_MANIFEST.json'}
actual = {path.relative_to(AUTHOR).as_posix() for path in BATCH.rglob('*') if path.is_file()}
check('manifest_count', len(rows) == manifest['file_count'] == 78)
check('git_exact_79', set(entries) == expected, {'git_count': len(entries)})
check('disk_exact_79', actual == expected, {'extra': sorted(actual-expected), 'missing': sorted(expected-actual)})
raw = git('cat-file', '--batch', data=('\n'.join(entries.values())+'\n').encode())
stream = io.BytesIO(raw)
blobs = {}
for name, oid in entries.items():
    header = stream.readline().decode().split()
    if header[:2] != [oid, 'blob']:
        raise ValueError('unexpected_git_batch_header')
    content = stream.read(int(header[2]))
    if stream.read(1) != b'\n':
        raise ValueError('unexpected_git_batch_delimiter')
    blobs[name] = content
    check('git_bytes:' + name, content == (AUTHOR/name).read_bytes())
total = 0
for row in rows:
    content = (AUTHOR/row['path']).read_bytes()
    total += len(content)
    check('manifest:' + row['path'], len(content) == row['bytes'] and sha(content) == row['sha256'])
check('manifest_total', total == manifest['total_bytes'])
check('root_plan_same_bytes', (BATCH/'admin/ROOT_PLAN.md').read_bytes() == Path('D:/hefe/docs/M4_ACTIVE_COVERAGE_001_PLAN.md').read_bytes())
fixed = read(AUTHOR/'verification/m4_surface_scan_compact_facts_001/installation/run_01/FIXED_BUILD_INPUTS.json')
check('product_138', fixed['source_count'] == len(fixed['manifest']) == 138)
for row in fixed['manifest']:
    # Compare the current source against the accepted product manifest, independently of imported modules.
    check('current_product:' + row['path'], sha((AUTHOR/row['path']).read_bytes()) == row['sha256'])

# Decode already-delivered images and their buffers; this does not generate a new raster.
sys.path.insert(0, str(AUTHOR/'.human-eye/releases/9.7.2+m4.surface.scan.compact.r1/site-packages'))
import numpy as np
from PIL import Image
image_summary = []
cameras = read(BATCH/'inputs/CAMERAS.json')
for pose in cameras['views']:
    name = pose['name']
    meta = read(BATCH/'render'/f'{name}.json')
    png = BATCH/'render'/f'{name}.png'
    arrays = BATCH/'render'/f'{name}.npz'
    check('PNG_hash:'+name, sha(png.read_bytes()) == meta['PNG_sha256'])
    check('buffer_hash:'+name, sha(arrays.read_bytes()) == meta['arrays_sha256'])
    check('pose_exact:'+name, pose == meta['pose'])
    with np.load(arrays, allow_pickle=False) as data:
        colors, depth, owners = data['color'], data['depth'], data['owners']
        check('array_shape:'+name, colors.shape == (512,512,3) and depth.shape == owners.shape == (512,512))
        check('array_dtypes:'+name, str(colors.dtype)=='uint8' and str(depth.dtype)=='float64' and str(owners.dtype)=='int32')
        check('PNG_equals_RGB:'+name, np.array_equal(np.asarray(Image.open(png)), colors))
        foreground = owners >= 0
        check('owner_range:'+name, np.all((owners >= -1) & (owners < 28)))
        check('depth_owner_agreement:'+name, np.array_equal(foreground, np.isfinite(depth) & (depth > 0)) and np.all(np.isposinf(depth[~foreground])))
        check('payload:'+name, colors.nbytes + depth.nbytes + owners.nbytes == meta['array_payload_bytes'])
        image_summary.append({'view':name,'foreground_pixels':int(foreground.sum()),'visible_owner_count':int(np.unique(owners[foreground]).size),'png_bytes':len(png.read_bytes()),'array_bytes':colors.nbytes+depth.nbytes+owners.nbytes})
        check('foreground_count:'+name, int(foreground.sum()) == meta['foreground_pixels'])

result = {'fixed_commit':COMMIT,'passed':all(row['passed'] for row in checks),'checks':len(checks),
          'failed':[row for row in checks if not row['passed']], 'manifest_files':len(rows),'git_delivery_files':len(entries),
          'manifest_bytes':total,'source_product_count':len(fixed['manifest']),'images':image_summary,
          'scope':'Root independent hash/Git identity and existing PNG/array decoding. No source execution, Blender, new raster, formal benchmark or model/API invocation.'}
(HERE/'IDENTITY_CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(HERE/'IDENTITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False))
