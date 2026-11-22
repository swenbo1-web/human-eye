"""Exercise the real shared ordinary owner on a pinned historical Yanyite array."""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ROOT = Path('D:/he_m4_yanyite_dual_curved_region_native_001')
ARCHIVE = Path('D:/he_m4_live_source_region_task_003/slots/N1/raw_sources/live-source-001.json')
ARCHIVE_SHA = '8053d8cdbb09b8d22bb75cd48b24ad6f913c8b348c2adbabc985493d6469dd83'
ASSET_SHA = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
PRODUCT = V / 'm4_region_task_global_first_frame_001/install/PRODUCT_RUN_BINDING.json'
SHARED = V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'


def require(test, reason):
    if not test:
        raise ValueError(reason)


def main(output):
    binding = json.loads(PRODUCT.read_bytes())
    shared = json.loads(SHARED.read_bytes())
    sys.path[:0] = [str(NS/'runtime'),str(HERE),str(NS),binding['install_root'],
                    binding['dependency_root'],shared['dependency_root']]
    import numpy as np
    import shapely
    from bridge import Owner, PRODUCT_TOOL, TOOLS
    from frame_device import FrameDevice
    from human_eye_plugin import attention_raster

    require(Path(attention_raster.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'preflight_raster_source_not_same_installed_distribution')
    raw = ARCHIVE.read_bytes()
    require(sha256(raw).hexdigest()==ARCHIVE_SHA,'old_raw_array_changed')
    scene = json.loads(raw)
    require(scene['source']['asset_sha256']==ASSET_SHA,'old_raw_source_wrong_asset')
    scene['source_ref'] = 'offline-yanyite-native-archive'
    visible, = [obj for obj in scene['objects'] if obj['visible_get']]
    hidden, = [obj for obj in scene['objects'] if not obj['visible_get']]
    require(len(visible['vertices'])==27304 and len(visible['triangles'])==53264
            and hidden['name']=='Cube' and len(hidden['triangles'])==12,
            'wrong_old_exact_geometry_or_display')
    output = output.resolve()
    require(output.is_relative_to(ROOT/'preflight'),'preflight_owned_output_required')
    output.mkdir(parents=True,exist_ok=False)
    deadline = time.perf_counter_ns()+120_000_000_000

    def fail(*args, **kwargs):
        raise AssertionError('native_preflight_cannot_use_Blender_or_product_dispatch')

    class ArchiveDevice(FrameDevice):
        def _capture(self, *, terminal):
            require(not terminal,'preflight_dir_holds_archived_raw_route_only')
            marker = {'event':'offline_archived_raw_source','sha256':ARCHIVE_SHA,'bytes':len(raw)}
            self.source_reads.append(marker)
            return scene

    class Runtime:
        def __init__(self, root, group):
            self.folder = root
            root.mkdir()
            self.device = ArchiveDevice(root,ASSET_SHA,group,group+'1',fail)
            self.buffers, self.cameras = self.device.buffers, self.device.cameras
            old_catalogue = V/'m4_dense_sweep_integrated_native_startup_001/inputs/EVIDENCE_TOOLS_SCHEMA.json'
            self.product_tools = json.loads(old_catalogue.read_bytes()) if group=='P' else []

        def __getattr__(self, name):
            if name in ('scene_data','render_views','render_local','image_specification'):
                return getattr(self.device,name)
            if name in ('public_request','native_run'):
                return fail
            raise AttributeError(name)

    def owner(group):
        rt = Runtime(output/group,group)
        return Owner(rt,{'group':group,'label':group+'1','phase':'formal','worker_deadline_ns':deadline,
                         'output':str(rt.folder/'owner')})

    def call(n, name, arguments):
        request = {'jsonrpc':'2.0','id':n,'method':'tools/call','params':{'name':name,'arguments':arguments}}
        response = original.handle(request,n)['result']
        require(not response['isError'],str(response['content'][0]))
        return response['content']

    original, other = owner('N'), owner('P')
    try:
        n_tools = original.handle({'id':0,'method':'tools/list'})['result']['tools']
        p_tools = other.handle({'id':0,'method':'tools/list'})['result']['tools']
        require(n_tools==TOOLS and [item for item in p_tools if item['name']!=PRODUCT_TOOL]==n_tools
                and len(p_tools)==len(n_tools)+1,'ordinary_tool_catalogues_diverged')
        # Keep the two archived mesh arrays and intermediate selection in the
        # real persistent consumer namespace. Only terse evidence leaves it.
        commands = [
            "data=scene_data()",
            "area=next(obj for obj in data['objects'] if obj['visible_get'])",
            "cube=next(obj for obj in data['objects'] if not obj['visible_get'])",
            "xyz=np.asarray(area['vertices'])",
            "mesh=np.asarray(area['triangles'])",
            "tri=xyz[mesh]",
            "box_low=np.array([-.09,.13,.565])",
            "box_high=np.array([.09,.18,.63])",
            "rows=np.flatnonzero(((tri>=box_low)&(tri<=box_high)).all(axis=(1,2)))",
            "target=(box_low+box_high)/2",
            "print(len(mesh),len(cube['triangles']),len(rows))",
        ]
        first = call(1,'execute_python',{'code':'\n'.join(commands)})
        m = json.loads(first[0]['text'])
        require(m['error'] is None and len(first[0]['text'])<200,'large_resident_arrays_leaked_in_ordinary_reply')
        # Invoke the genuine native renderer and inspect source id arrays in a
        # later tool call. PNG retrieval is deliberately through read_images.
        second = call(2,'execute_python',{'code':"""
frame=render_local('BACK',target.tolist(),0.25)
target_index=frame['object_names'].index(area['name'])
ids=buffers[frame['ref']]['triangle_ids']
owners=buffers[frame['ref']]['owners']
local_ids=ids[owners==target_index]-frame['source_face_offsets'][target_index]
sample_rows=np.intersect1d(np.unique(local_ids),rows)
print(frame['ref'],len(sample_rows),int(sample_rows[0]) if len(sample_rows) else None)
"""})
        stdout = json.loads(second[0]['text'])['stdout'].strip().split()
        require(len(stdout)==3 and int(stdout[1])>0,'actual_native_local_frame_has_no_upper_source_samples')
        ref,count,sample = stdout[0],int(stdout[1]),int(stdout[2])
        attachment = call(3,'read_images',{'refs':[ref]})
        require(len(attachment)==2 and attachment[0]['type']=='text'
                and attachment[1]['type']=='image' and attachment[1]['mimeType']=='image/png',
                'ordinary_original_mixed_image_delivery_missing')
        caption = json.loads(attachment[0]['text'].splitlines()[1])
        png = Path(caption['local_image_path']).resolve(strict=True)
        require(png.is_relative_to(original.runtime.folder) and caption['local_image_path']==png.as_posix()
                and base64.b64decode(attachment[1]['data'],validate=True)==png.read_bytes()
                and caption['image_sha256']==sha256(png.read_bytes()).hexdigest(),
                'ordinary_same_slot_png_unchanged_or_readback_failed')
        frame = original.runtime.device.by_ref[ref]
        with np.load(frame['NPZ'],allow_pickle=False) as evidence:
            require(evidence['display_object_mask'].tolist()==[True,False]
                    and np.any((evidence['owners']==0)&(evidence['triangle_ids']==sample))
                    and not np.any(evidence['owners']==1),'archived_native_hidden_cube_or_sample_binding_failed')
        require(len(original.runtime.device.source_reads)==1 and
                len([ev for ev in original.runtime.device.events if ev['event']=='native_raster_attempt'])==1,
                'unexpected_number_of_offline_raw_reads_or_rasters')
        receipt = {'passed':True,'archived_capture':{'path':str(ARCHIVE),'bytes':len(raw),'sha256':ARCHIVE_SHA},
                   'actual_ordinary_tool_count':len(n_tools),'product_tool_only_in_P':True,
                   'raster_source':str(Path(attention_raster.__file__).resolve()),
                   'ordinary_deps':{'numpy':np.__version__,'shapely':shapely.__version__},
                   'old_native_render_only':{'native_attempts':1,'ordinary_calls':3,'actual_sampled_selected_triangles':count,
                    'source_triangle_witness':sample,'original_frame':frame},
                   'new_Blender_starts':0,'new_models':0}
    finally:
        require(original.close()['confirmed'] and other.close()['confirmed'],'ordinary_bridge_close_failed')
    (output/'NATIVE_PREFLIGHT.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n',
                                               encoding='utf8',newline='\n')
    print(json.dumps({'passed':True,'sampled_triangles':count,'root':str(output)}),flush=True)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_preflight_python_required')
    main(args.output)
