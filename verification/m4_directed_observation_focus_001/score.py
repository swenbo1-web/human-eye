"""Read a closed pair. Verify original PNG, float depth, owner and evaluated source row."""
import base64
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

BASE = '7075c79b8aff6821e3cb37882b7123be2728cbf38972f34b93e05ef8afa8e50c'
CAND = '00ba6e251415847878e7ed028a5ba704f6e8ee6ba4bd567dd3fea0e8076bb72e'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def slot_review(folder, arm, truth, fixture_hash):
    ledger = read(folder/'ledger.json')
    ready,closed = read(folder/'ready.json'),read(folder/'closed.json')
    post = read(folder/'post_capture.json')
    assert ready['source_kind'] == 'installed_distribution'
    assert (ready['source_sha256'],ready['source_files']) == ((BASE,145) if arm=='A' else (CAND,146))
    assert closed['blender_exit']==ledger['server_exit']==0 and ledger['stdout_eof']
    assert ready['fixture_before']==closed['fixture_after']==sha((folder/'cube.blend').read_bytes())==fixture_hash
    assert closed['pid']==ready['pid'] and len(post['meshes'])==1
    mesh=post['meshes'][0]
    assert (mesh['vertices'],mesh['faces'],mesh['name'])==(truth['vertices'],truth['faces'],truth['name'])
    assert post['display_snapshot']['objects'][0]['visible_get']
    assert all(mesh['vertices'][i][2]==-1 for i in mesh['faces'][0])
    assert all(mesh['vertices'][i][2]==1 for i in mesh['faces'][2])
    items=[]
    arrays_by_ref={}
    for n,row in enumerate(ledger['requests'],1):
        label=row['label']
        prefix=folder/f'{n:02d}-{label}'
        tx=prefix.with_suffix('.tx').read_bytes()
        rx=prefix.with_suffix('.rx').read_bytes()
        assert sha(tx)==row['tx_sha'] and sha(rx)==row['rx_sha']
        request, reply=json.loads(tx),json.loads(rx)
        if label in ('init','tools'):
            if label=='tools':
                tools=reply['result']['tools']
                spec=next(x for x in tools if x['name']=='human_eye_scene_observe')['inputSchema']
                assert ('"focus"' in json.dumps(spec)) == (arm=='B')
            continue
        assert not reply['result']['isError'] and reply['id']==request['id']==n
        blocks=reply['result']['content']
        body=json.loads(blocks[0]['text'])
        expected=None if arm=='A' else ('auto' if label in ('cold','repeat') else {'source_triangle_index':2})
        assert request['params']['arguments']['query'].get('focus')==expected
        meta=body['image_delivery']
        assert len(blocks)-1==len(body['frames'])==meta['mcp_content_constructed_image_count']
        frames=[]
        for frame,block in zip(body['frames'],blocks[1:]):
            assert block['type']=='image' and block['mimeType']=='image/png'
            img=base64.b64decode(block['data'],validate=True)
            path=Path(frame['image_path']).resolve(strict=True)
            assert path.is_relative_to(folder.resolve()) and path.read_bytes()==img and sha(img)==frame['image_sha256']
            npz=Path(frame.get('arrays_path',path.with_suffix('.npz'))).resolve(strict=True)
            assert npz.is_relative_to(folder.resolve())
            if 'arrays_sha256' in frame:
                assert sha(npz.read_bytes())==frame['arrays_sha256']
            with np.load(npz,allow_pickle=False) as arr, Image.open(path) as png:
                assert np.array_equal(arr['color'],np.asarray(png.convert('RGB')))
                owners,ids,depth=arr['owners'],arr['triangle_ids'],arr['depth']
                assert depth.dtype==np.float64 and owners.shape==depth.shape==ids.shape==(512,512)
                visible=(owners==0)&np.isfinite(depth)
                counts={str(i):int(np.count_nonzero(visible & (ids==i))) for i in (0,1,2)}
                anchor=None
                if arm=='B':
                    facts=body['facts']['focus']
                    pixel=facts['sample']['sampled_pixel']
                    i=facts['region_ref']['source_triangle_indices'][0]
                    r,c=pixel['row'],pixel['column']
                    assert visible[r,c] and ids[r,c]==i==pixel['source_triangle_index']
                    assert counts[str(i)]==facts['sample']['selected_surface_pixels']
                    anchor=dict(row=r,column=c,source_triangle=i)
            frames.append(dict(view=frame['view_name'],png_bytes=len(img),png_sha256=sha(img),
                frame_identity=frame['frame_identity'],source_pixels=counts,anchor=anchor))
            arrays_by_ref[frame['image_ref']]=npz
        entry=dict(call=label, raster_attempts=meta['new_raster_attempts'],published=frames,
            actual_capture_calls=body.get('work',{}).get('capture_calls'),rtt_ms=row['rtt_ms'])
        if arm=='B':
            facts=body['facts']['focus']
            assert facts['complete_surface_visibility']=='unknown'
            assert facts['minimum_sample_pixels']==16 and len(facts['views'])<=2
            entry.update(reason=facts['stop_reason'], attempted=facts['views'], selection=facts['selection'],
                triangle=facts['region_ref']['source_triangle_indices'][0],
                direction=facts['sample']['target_to_eye_unit'] if facts['sample'] else None,
                selection_ms=(body.get('stages',{}).get('focus_selection',{}).get('elapsed_ns',0)/1e6))
            if label=='cold':
                assert [v['view_name'] for v in facts['views']]==['SCENE','FOCUS']
                assert facts['views'][0]['verified_pixels']==0
                assert facts['region_ref']['source_triangle_indices']==[0] and entry['direction']==[0,0,-1]
                path=arrays_by_ref[body['frames'][0]['image_ref']]
                first,=path.parent.glob('001-*.npz')
                with np.load(first,allow_pickle=False) as arr:
                    assert not np.any((arr['owners']==0)&(arr['triangle_ids']==0))
            elif label=='plan-top':
                assert entry['reason']=='image_not_requested' and not frames
            elif label=='cold-top':
                assert entry['triangle']==2 and len(facts['views'])==1 and frames[0]['view']=='SCENE'
            elif label=='repeat':
                assert frames==items[0]['published'] and facts['views']==items[0]['attempted']
        items.append(entry)
    expected_counts=[3,0] if arm=='A' else [2,0,1,0]
    assert [row['raster_attempts'] for row in items]==expected_counts
    archives=list(folder.glob('state.json.active_observation/**/*.npz'))
    assert len(archives)==sum(expected_counts)
    events=[json.loads(line) for line in (folder/'audit.jsonl').read_bytes().splitlines()]
    assert sum(e.get('event')=='active_observation_render_attempt' for e in events)==sum(expected_counts)
    if arm=='A':
        assert [f['view'] for f in items[0]['published']]==['SCENE','LEFT','BACK']
        assert all(f['source_pixels']['0']==f['source_pixels']['1']==0 for f in items[0]['published'])
        assert items[0]['published']==items[1]['published']
    return dict(arm=arm, source_sha256=ready['source_sha256'], installed_sources=ready['source_files'],
        stdout_eof=True, blender_exit=0, server_exit=0, mesh_count=1, triangles=12, images_constructed=len(archives),
        original_fixture_unchanged=True, calls=items)

if __name__=='__main__':
    a,b,truth_path,dest=map(Path,sys.argv[1:])
    truth=read(truth_path)
    fixture_hash=sha(truth_path.with_suffix('').with_suffix('.blend').read_bytes())
    arms=[slot_review(s,arm,truth,fixture_hash) for s,arm in [(a,'A'),(b,'B')]]
    dest.write_text(json.dumps(dict(fixture_sha256=fixture_hash, blender=truth['blender'], arms=arms),
                               indent=2),encoding='utf8')
    print('Two closed slots. Independent pixel, source, ownership and frame checks passed.')
