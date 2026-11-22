"""Exercise installed optional path provenance with sealed frames and derived controls."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch


NS = Path(__file__).resolve().parent
ORIGINAL = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001/slots')
DATA = NS/'install/PRODUCT_RUN_BINDING.json'


def read(path):
    return json.loads(Path(path).read_bytes())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def producer(slot):
    return read(ORIGINAL/slot/'product_full/call_001/SERVICE_RESULT.json')


def repath(result, index, image, arrays=None):
    """Change only caller-owned metadata, preserving the already acquired image identity."""
    frame = result['frames'][index]
    identity = frame['frame_identity']
    old = frame['image_path']
    png, npz = str(image), str(arrays if arrays is not None else Path(image).with_suffix('.npz'))
    for collection in (result['frames'],result['constructed_frames']):
        for row in collection:
            if row['frame_identity'] == identity:
                row.update(image_path=png, arrays_path=npz)
    for scope in result['scopes']:
        for row in scope['facts']['observations']:
            if row['frame_identity'] == identity:
                require(row['image_path'] == old, 'source_synthesized_path_before_control')
                row['image_path'] = png


def paths(packet):
    body = json.loads(packet['content'][0]['text'])
    table = body.get('witness_image_paths')
    return [] if table is None else table['rows']


def run():
    installed = read(DATA)
    sys.path[:0] = [installed['install_root'], installed['dependency_root']]
    from human_eye_plugin import live_service, live_spatial_mcp, read_context
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity(mode='live')['source_sha256'] == installed['source_sha256'],
            'optional_control_imported_wrong_candidate')
    retained_read, retained_resolve, retained_is_file = Path.read_bytes, Path.resolve, Path.is_file
    original = producer('B1')
    independent = producer('A1')
    service = live_service.LiveSpatialService.__new__(live_service.LiveSpatialService)
    service.state_path = ORIGINAL/'B1/product_state.json'
    context = service._read_context = read_context.ReadContext()
    key = read_context.query_key({'mode':'active_observation','include_image':True,
                                  'region_task':original['facts']['region_task']['conditions']})

    def populate(value, capture=None):
        context.reset()
        context.activate(capture or value['binding'],'active_observation',{'original':'control'})
        context.result(key,lambda:(deepcopy(value),()))

    def format_reply(value, callback=service._region_task_observation_producer):
        reads, audit = [], {}

        def record_read(path):
            if path.suffix == '.png':
                reads.append(str(path))
            return retained_read(path)

        with patch.object(Path,'read_bytes',record_read):
            reply = live_spatial_mcp._tool_result(value,is_error=False,response_detail='brief',
                      active_delivery_audit=audit,region_task_observation_producer=callback)
        require(reads == [frame['image_path'] for frame in value['frames']],
                'extra_product_PNG_reads/' + str(reads))
        return reply, audit

    outcomes = {}

    def examine(name, value, expected_indices, *, callback=service._region_task_observation_producer):
        reply, audit = format_reply(value,callback)
        rows = paths(reply)
        require([row[0] for row in rows] == expected_indices,'incorrect_optional_path_control/' + name)
        require(audit['native_blocks_constructed'] == len(value['frames']), 'optional_path_changed_native_delivery/' + name)
        outcomes[name] = {'optional_indices':[row[0] for row in rows],
                          'normal_PNG_reads':len(audit['frames']),'added_PNG_reads':0,
                          'native_blocks':len(reply['content'])-1}
        return reply

    populate(original)
    positive = examine('authored_two_scope_local_ordinals',original,[1,2])
    require(all(Path(path).name.startswith('001-') for _,path in paths(positive)),
            'native_block_ordinal_used_as_scope_file_ordinal')
    examine('no_global_path_for_low_pixel_global_scene',original,[1,2])
    standard, _ = format_reply(original,None)
    require('witness_image_paths' not in json.loads(standard['content'][0]['text']),
            'standard_response_changed_by_optional_path')
    outcomes['standard_has_no_optional_path'] = {'optional_indices':[]}

    current = deepcopy(original)
    replacement = independent['frames'][1]
    require(retained_read(Path(replacement['image_path'])) == retained_read(Path(original['frames'][1]['image_path'])),
            'cross_slot_images_do_not_actually_have_same_bytes')
    repath(current,1,replacement['image_path'],replacement['arrays_path'])
    examine('cross_slot_same_bytes',current,[2])

    current = deepcopy(original)
    actual = Path(original['frames'][1]['image_path'])
    alias = actual.parent.parent.with_name(actual.parent.parent.name.upper())/actual.parent.name/actual.name
    require(str(alias)!=str(actual) and retained_read(alias)==retained_read(actual),'windows_directory_alias_control_unavailable')
    repath(current,1,alias)
    examine('windows_directory_case_alias',current,[2])
    # Even an alternate path in a retained record must have canonical spelling.
    populate(current)
    examine('retained_noncanonical_spelling',current,[2])
    populate(original)

    current = deepcopy(original)
    alternate = actual.parent.parent.with_name('0'*32)/actual.parent.name/actual.name
    repath(current,1,alternate)

    def same_bytes_at_alternate(path):
        return retained_read(actual if path == alternate else path)

    # Create a same-slot alternate generation in the test's file view only.
    # Its encoding sees exactly real bytes. A path-only check would accept it.
    with patch.object(Path,'read_bytes',same_bytes_at_alternate), patch.object(
            Path,'resolve',lambda path,**kw: path if path==alternate else retained_resolve(path,**kw)), patch.object(
            Path,'is_file',lambda path: True if path==alternate else retained_is_file(path)):
        reply = live_spatial_mcp._tool_result(current,is_error=False,response_detail='brief',
                       region_task_observation_producer=service._region_task_observation_producer)
    require([index for index,_ in paths(reply)] == [2] and reply['content'][1:] == positive['content'][1:],
            'same_bytes_generation_alias_published')
    outcomes['same_slot_alternate_generation_virtual_equal_bytes'] = {'optional_indices':[2],
                    'original_png_equal':True,'virtual_file_reader_only':True,'created_files':0}

    with patch.object(Path,'is_file',lambda path: False if str(path)==str(actual) else retained_is_file(path)):
        examine('file_disappears_after_media_encoding',original,[2])

    context.activate(original['binding'],'observation_task')
    examine('same_generation_joint_task_selection_preserves_paths',original,[1,2])
    capture = {'capture_state':{**original['binding']['capture_state'],
                                'revision':original['binding']['capture_state']['revision'] + 1}}
    context.activate(capture,'source_region')
    examine('stale_capture_generation_keeps_original_blocks_without_paths',original,[])
    context.activate({},'active_observation')
    examine('unversioned_or_missing_retained_records',original,[])
    populate(original)
    context.activate(original['binding'],'active_observation',{'original':'ambiguous'})
    context.result(key,lambda:(deepcopy(original),()))
    examine('ambiguous_retained_source_is_omitted',original,[])
    populate(original)
    current = deepcopy(original)
    lost = current['frames'].pop(1)
    task = current['facts']['region_task']
    task['summary']['selected_image_count'] -= 1
    for row in task['rows']:
        witness = row['complete_witness']
        if witness is not None and witness['frame_identity'] == lost['frame_identity']:
            witness['selected_for_delivery'] = False
    populate(current)
    examine('complete_local_frame_not_delivered',current,[2])
    populate(original)

    # Real encoding rejects a fact-consistent image path if the file bytes change.
    wrong_file = Path(original['frames'][0]['image_path'])
    with patch.object(Path,'read_bytes',lambda path: retained_read(wrong_file if path==actual else path)):
        try:
            live_spatial_mcp._tool_result(original,is_error=False,response_detail='brief',
                  region_task_observation_producer=service._region_task_observation_producer)
        except ValueError as error:
            require(str(error)=='Active observation PNG source binding changed','wrong_PNG_error_changed')
            outcomes['bad_PNG_bytes_match_no_path'] = {'original_rejection':str(error)}
        else:
            raise ValueError('wrong_PNG_passed_original_encoding')

    brief = json.loads(standard['content'][0]['text'])
    brief['witnesses']['rows'].append(brief['witnesses']['rows'][0])
    live_spatial_mcp._project_region_task_witness_image_paths(brief,original,positive['content'][1:],
                                                            service._region_task_observation_producer)
    require([row[0] for row in brief['witness_image_paths']['rows']] == [1,2], 'duplicate_frame_path_row')
    outcomes['multiple_complete_witnesses_share_one_optional_row'] = {'optional_indices':[1,2],
                     'scope':'duplicate after verified projection, not a new production scenario'}
    output = NS/'evidence/PRODUCT_CONTROLS.json'
    with output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump({'passed':True,'installed_source':installed['source_sha256'],'controls':outcomes,
                   'control_scope':'direct installed formatter and current read context; no new render/PNG writes',
                   'original_service_result_sha256':sha256(
                        (ORIGINAL/'B1/product_full/call_001/SERVICE_RESULT.json').read_bytes()).hexdigest()},
                   stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(len(outcomes),'optional path controls passed',flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    run()
