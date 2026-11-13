"""Offline compare every unchanged raster to accepted001; no render imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification')
OLD=BASE/'m4_active_coverage_001/render'
NEW=BASE/'m4_active_coverage_003/runs'
checks=[]
for run in sorted(NEW.iterdir()):
    if not run.is_dir(): continue
    result=json.loads((run/'RESULT.json').read_bytes())
    for frame in result['frames']:
        view=frame['view_name']; png=Path(frame['PNG']); arrays=Path(frame['owner_depth_RGB_arrays'])
        record=dict(run=run.name,view=view,png_sha256=hashlib.sha256(png.read_bytes()).hexdigest())
        with Image.open(png) as im: rgb=np.array(im.convert('RGB'))
        with np.load(arrays,allow_pickle=False) as a:
            record['published_png_matches_RGB']=bool(np.array_equal(rgb,a['color']))
            if run.name.startswith('control') and view=='BACK':
                record['comparison']='changed_span64_control'
                record['passed']=record['published_png_matches_RGB'] and png.read_bytes()!=(OLD/(view+'.png')).read_bytes()
            else:
                with np.load(OLD/(view+'.npz'),allow_pickle=False) as b:
                    record['all_arrays_equal_001']=all(np.array_equal(a[k],b[k]) for k in ('color','owners','depth'))
                record['png_equal_001']=png.read_bytes()==(OLD/(view+'.png')).read_bytes()
                record['comparison']='unchanged_camera'
                record['passed']=record['published_png_matches_RGB'] and record['all_arrays_equal_001'] and record['png_equal_001']
        checks.append(record)
out=dict(scope='Decode all58 stored frames; compare56 unchanged frames to accepted001. Two changed BACK64 controls are independently recounted in feedback review.',
         new_renders=0,frames=len(checks),unchanged=sum(r['comparison']=='unchanged_camera' for r in checks),
         checks=checks,failed=[r for r in checks if not r['passed']])
(HERE/'FRAMES.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in out.items() if k!='checks'}))
