"""Neutral, owned persistent Blender execution and image-accounting fixture.

No Human Eye import, object inventory, task selector or geometry solver is
provided. This is an audited experiment boundary, not a Python security sandbox.
"""
from __future__ import annotations
import argparse,contextlib,hashlib,io,json,math,os,shutil,socket,struct,subprocess,sys,threading,time,traceback,uuid,zlib
from pathlib import Path

MAX_CODE=256*1024;MAX_OUTPUT=8*1024*1024;MAX_WIRE=20*1024*1024
IMAGE_LIMITS=dict(max_images=8,max_single_pixels=1024**2,max_total_pixels=4*768**2)

def need(value,reason):
    if not value:raise ValueError('visual004_native_'+reason)
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def save(path,value,*,replace=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);raw=encoded(value)
    temporary=path.with_name(path.name+'.next-'+uuid.uuid4().hex) if replace else path
    with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if replace:os.replace(temporary,path)
    need(path.read_bytes()==raw,'persist_readback')
def append(path,value):
    with Path(path).open('ab') as stream:stream.write(encoded(value));stream.flush();os.fsync(stream.fileno())
def check(deadline_ns):need(type(deadline_ns) is int and time.perf_counter_ns()<deadline_ns,'original_deadline')

def publish_ready(path,value,*,deadline_ns):
    """Publish one complete readiness record without replacing an existing one.

    The link is the only publication operation. A failed or late publication is
    never retried through replace, and only this call's staging file is removed.
    """
    path=Path(path);need(path.name in ('READY.json','BROKER_READY.json'),'ready_filename');check(deadline_ns)
    raw=encoded(value);decoded=json.loads(raw);stage=path.with_name(path.name+'.ready-stage-'+uuid.uuid4().hex)
    owned=False
    try:
        stream=stage.open('xb');owned=True
        with stream:
            offset=0
            while offset<len(raw):
                check(deadline_ns);written=stream.write(raw[offset:])
                need(type(written) is int and 0<written<=len(raw)-offset,'ready_staging_write');offset+=written
            stream.flush();os.fsync(stream.fileno())
        staged=stage.read_bytes();need(staged==raw and json.loads(staged)==decoded,'ready_staging_readback')
        check(deadline_ns);os.link(stage,path)
        check(deadline_ns);published=path.read_bytes()
        need(published==raw and json.loads(published)==decoded,'ready_persist_readback');check(deadline_ns)
    finally:
        if owned:
            original=sys.exc_info()[1]
            try:stage.unlink()
            except FileNotFoundError:pass
            except BaseException as exc:
                if original is None:raise
                original.add_note('ready staging cleanup failed: '+repr(exc))
    check(deadline_ns)

def protected_files_intact(config):
    return (sha(config['asset'])==config['asset_sha256'] and sha(config['asset_copy'])==config['asset_sha256']
        and all(sha(row['path'])==row['sha256'] for row in config.get('protected_public_images',[]))
        and ('management_steps' not in config or sha(config['management_steps']['path'])==config['management_steps']['sha256'])
        and ('qa_vertex_patch' not in config
             or sha(config['qa_vertex_patch']['path'])==config['qa_vertex_patch']['sha256']))

def _load_qa_vertex_patch(path,expected_sha256=None):
    """Validate the fixed coordinator patch before any vertex setter runs."""
    raw=Path(path).read_bytes()
    need(len(raw)<=MAX_CODE,'qa_patch_bytes')
    digest=hashlib.sha256(raw).hexdigest()
    need(expected_sha256 is None or digest==expected_sha256,'qa_patch_source_changed')
    patch=json.loads(raw)
    need(type(patch) is dict and set(patch)=={'target_name','vertices'},'qa_patch_fields')
    need(type(patch['target_name']) is str and 0<len(patch['target_name'])<=256,'qa_patch_target')
    need(type(patch['vertices']) is list and 0<len(patch['vertices'])<=4096,'qa_patch_vertices')
    indices=set()
    vertices=[]
    for row in patch['vertices']:
        need(type(row) is dict and set(row)=={'index','co'},'qa_patch_vertex_fields')
        index=row['index']
        need(type(index) is int and index>=0 and index not in indices,'qa_patch_index')
        co=row['co']
        need(type(co) is list and len(co)==3
             and all(type(value) in (int,float) and abs(value)<=3.4028234663852886e38
                     and math.isfinite(value) for value in co),'qa_patch_coordinate')
        # Blender mesh coordinates are float32. Bind readback to the same
        # representable values.
        try:normalized=[struct.unpack('f',struct.pack('f',value))[0] for value in co]
        except (OverflowError,struct.error):raise ValueError('visual004_native_qa_patch_coordinate_range')
        need(all(math.isfinite(value) for value in normalized),'qa_patch_coordinate_range')
        indices.add(index)
        vertices.append(dict(index=index,co=normalized))
    return dict(target_name=patch['target_name'],vertices=vertices),digest

def png_metadata(raw):
    need(type(raw) is bytes and 33<=len(raw)<=16*1024*1024 and raw[:8]==b'\x89PNG\r\n\x1a\n','PNG_signature_or_size')
    offset=8;width=height=None;ended=False;idat=False
    while offset<len(raw):
        need(offset+12<=len(raw),'PNG_chunk');length=struct.unpack('>I',raw[offset:offset+4])[0]
        kind=raw[offset+4:offset+8];end=offset+12+length;need(end<=len(raw),'PNG_chunk')
        payload=raw[offset+8:end-4];crc=struct.unpack('>I',raw[end-4:end])[0]
        need((zlib.crc32(kind+payload)&0xffffffff)==crc,'PNG_crc')
        if width is None:
            need(kind==b'IHDR' and length==13,'PNG_IHDR');width,height=struct.unpack('>II',payload[:8])
            need(0<width<=8192 and 0<height<=8192,'PNG_dimensions')
        elif kind==b'IHDR':need(False,'PNG_duplicate_IHDR')
        if kind==b'IDAT':idat=True
        if kind==b'IEND':need(length==0 and end==len(raw),'PNG_IEND');ended=True
        offset=end
    need(ended and idat,'PNG_incomplete')
    return dict(width=width,height=height,pixels=width*height,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

def decoded_png_metadata(raw):
    """Parent-side decode qualification; the Blender worker does not use PIL."""
    meta=png_metadata(raw)
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        need(image.format=='PNG' and image.size==(meta['width'],meta['height']),'PNG_decode_metadata')
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:image.load()
    return dict(meta,pixels_fully_decoded=True)

class ImageLedger:
    """Construction and delivery are separate; identical redisplays cost again.

    reserve_delivery spends the entire reservation even on unknown outcome.
    Completion is a host-observed claim supplied by the trial coordinator, not
    an assertion by this helper that a model actually received any image.
    """
    def __init__(self,workspace,*,limits=None):
        self.workspace=Path(workspace).resolve();self.folder=self.workspace/'images';self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'LEDGER.json';self.limits=dict(IMAGE_LIMITS if limits is None else limits)
        need(set(self.limits)==set(IMAGE_LIMITS) and all(type(v) is int and 0<v<=IMAGE_LIMITS[k] for k,v in self.limits.items()),'image_limits')
        if not self.path.exists():save(self.path,dict(schema='visual004-image-ledger-v1',limits=self.limits,constructions=[],reservations=[],reserved_images=0,reserved_pixels=0))
        need(load(self.path)['limits']==self.limits,'image_limits_changed')
    @contextlib.contextmanager
    def _locked(self):
        lock=self.folder/'ACTIVE';lock.mkdir()
        try:yield load(self.path)
        finally:lock.rmdir()
    def register_external_image(self,png_bytes,*,label='',origin='external'):
        meta=decoded_png_metadata(png_bytes)
        with self._locked() as state:
            number=len(state['constructions'])+1;image_id='image-'+str(number);path=self.folder/(image_id+'.png')
            with path.open('xb') as stream:stream.write(png_bytes);stream.flush();os.fsync(stream.fileno())
            need(path.read_bytes()==png_bytes,'PNG_persist_readback')
            row=dict(image_id=image_id,path=str(path),label=str(label),origin=str(origin),constructed_at_ns=time.perf_counter_ns(),
                **meta,construction_ordinal=number,delivery_state='not_delivered',
                same_bytes_previously_registered=any(r['sha256']==meta['sha256'] for r in state['constructions']))
            state['constructions'].append(row);save(self.path,state,replace=True);return row
    def reserve_delivery(self,image_ids):
        need(type(image_ids) is list and 1<=len(image_ids)<=8 and all(type(v) is str for v in image_ids),'delivery_ids')
        with self._locked() as state:
            index={r['image_id']:r for r in state['constructions']};need(all(i in index for i in image_ids),'unknown_image')
            rows=[index[i] for i in image_ids]
            for row in rows:
                need(sha(row['path'])==row['sha256'],'image_changed')
                need(row['width']<=1024 and row['height']<=1024 and row['pixels']<=self.limits['max_single_pixels'],'single_image_pixel_budget')
            pixels=sum(row['pixels'] for row in rows)
            need(state['reserved_images']+len(rows)<=self.limits['max_images'],'image_count_budget')
            need(state['reserved_pixels']+pixels<=self.limits['max_total_pixels'],'total_pixel_budget')
            result=dict(reservation_id='delivery-'+str(len(state['reservations'])+1),image_ids=image_ids[:],
                images=len(rows),pixels=pixels,state='reserved_unknown_until_host_receipt',at_ns=time.perf_counter_ns(),
                model_received=None)
            state['reserved_images']+=len(rows);state['reserved_pixels']+=pixels;state['reservations'].append(result)
            save(self.path,state,replace=True);return result
    def complete_delivery(self,reservation_id,*,outcome,host_event_id):
        need(outcome in ('shown','failed','unknown') and type(host_event_id) is str and host_event_id,'delivery_outcome')
        with self._locked() as state:
            rows=[r for r in state['reservations'] if r['reservation_id']==reservation_id];need(len(rows)==1,'reservation')
            row=rows[0];need(row['state']=='reserved_unknown_until_host_receipt','duplicate_completion')
            row.update(state=outcome,host_event_id=host_event_id,completed_at_ns=time.perf_counter_ns(),
                model_received=None,receipt_scope='coordinator_host_evidence_required; helper_is_not_consumption_attestation')
            save(self.path,state,replace=True);return row
    def status(self):return load(self.path)

class _LimitedText(io.StringIO):
    def __init__(self):super().__init__();self.written_bytes=0
    def write(self,value):
        count=len(value.encode('utf8'));need(self.written_bytes+count<=MAX_OUTPUT,'stdout_byte_budget')
        result=super().write(value);self.written_bytes+=count;return result

def _read_request(connection,deadline_ns):
    data=bytearray()
    while True:
        check(deadline_ns);connection.settimeout(max(.001,(deadline_ns-time.perf_counter_ns())/1e9))
        chunk=connection.recv(min(65536,MAX_CODE+4096-len(data)));need(chunk,'request_EOF');data.extend(chunk)
        need(len(data)<=MAX_CODE+4096,'request_bytes')
        try:request=json.loads(data)
        except (ValueError,UnicodeDecodeError):continue
        need(type(request) is dict,'request_object');return request

def _scene_state(bpy):
    """Terminal original geometry/identity check, not a source validator/solver."""
    rows=[]
    for obj in sorted(bpy.data.objects,key=lambda x:x.name):
        if obj.type in ('CAMERA','LIGHT'):continue
        material_rows=[]
        for mat in obj.data.materials if hasattr(obj.data,'materials') else []:
            if mat is None:material_rows.append(None);continue
            nodes=[]
            if mat.use_nodes:
                for node in sorted(mat.node_tree.nodes,key=lambda n:n.name):
                    values=[]
                    for inp in node.inputs:
                        if hasattr(inp,'default_value'):
                            val=inp.default_value
                            try:val=list(val)
                            except TypeError:pass
                            if isinstance(val,(str,bool,int,float,list)):values.append([inp.identifier,val])
                    nodes.append([node.bl_idname,node.name,values])
            links=[] if not mat.use_nodes else sorted([link.from_node.name,link.from_socket.identifier,link.to_node.name,link.to_socket.identifier]
                for link in mat.node_tree.links)
            material_rows.append([mat.name,list(mat.diffuse_color),mat.use_nodes,nodes,links])
        row=dict(name=obj.name,type=obj.type,parent=None if obj.parent is None else obj.parent.name,
            matrix_world=[list(r) for r in obj.matrix_world],hide_render=obj.hide_render,hide_viewport=obj.hide_viewport,
            hide_set=obj.hide_get(),materials=material_rows)
        if obj.type=='MESH':row.update(vertices=[list(v.co) for v in obj.data.vertices],edges=[list(edge.vertices) for edge in obj.data.edges],
            polygons=[dict(vertices=list(f.vertices),material_index=f.material_index,use_smooth=f.use_smooth) for f in obj.data.polygons])
        rows.append(row)
    return dict(objects=rows,unit_scale=bpy.context.scene.unit_settings.scale_length,
        frame_number=getattr(bpy.context.scene,'frame_current',0),subframe=getattr(bpy.context.scene,'frame_subframe',0))

def _scene_fingerprint(bpy):
    return hashlib.sha256(encoded(_scene_state(bpy))).hexdigest()

def _apply_qa_vertex_patch(bpy,patch):
    """Apply the preregistered local coordinates and verify the full readback."""
    before=_scene_state(bpy)
    targets=[obj for obj in bpy.data.objects if obj.name==patch['target_name']]
    need(len(targets)==1 and targets[0].type=='MESH','qa_patch_target_mesh')
    target=targets[0]
    need(sum(obj.type=='MESH' and obj.data is target.data for obj in bpy.data.objects)==1,'qa_patch_shared_mesh')
    need(all(row['index']<len(target.data.vertices) for row in patch['vertices']),'qa_patch_index_range')
    need(any(list(target.data.vertices[row['index']].co)!=row['co'] for row in patch['vertices']),'qa_patch_no_change')
    expected=json.loads(encoded(before))
    target_state=next(row for row in expected['objects'] if row['name']==patch['target_name'])
    for row in patch['vertices']:
        target_state['vertices'][row['index']]=row['co']
    for row in patch['vertices']:
        target.data.vertices[row['index']].co=row['co']
    target.data.update()
    bpy.context.view_layer.update()
    after=_scene_state(bpy)
    need(after==expected,'qa_patch_readback')
    return dict(target_name=patch['target_name'],vertices_written=len(patch['vertices']),
        before_fingerprint=hashlib.sha256(encoded(before)).hexdigest(),
        after_fingerprint=hashlib.sha256(encoded(after)).hexdigest())

def _scan_pngs(workspace):
    rows={}
    # Only this owned workspace. Do not enumerate global Blender/user images.
    for path in Path(workspace).rglob('*.png'):
        need(len(rows)<256,'construction_file_budget')
        try:rows[str(path.resolve())]=png_metadata(path.read_bytes())
        except (OSError,ValueError):rows[str(path.resolve())]=dict(invalid_or_incomplete=True)
    return rows

def worker(config_path):
    import bpy
    config=load(config_path);workspace=Path(config['workspace']);deadline=config['deadline_ns']
    check(deadline);need(sha(config['asset_copy'])==config['asset_sha256'],'worker_asset_binding')
    # Both conditions load the same file bytes. Redirect only the in-memory
    # default output path so ordinary write_still never targets the source PNG.
    renders_directory=workspace/'renders';renders_directory.mkdir(exist_ok=True)
    bpy.context.scene.render.filepath=str(renders_directory/'default.png')
    initial=_scene_fingerprint(bpy);current=initial;qa_advanced=False;management_step=0
    audit=workspace/'WORKER_EVENTS.jsonl';renders=[]
    def render_event(kind):
        def handler(*_):
            event=dict(event=kind,at_ns=time.perf_counter_ns());renders.append(event);append(audit,event)
        return handler
    for name,kind in [('render_pre','render_started'),('render_post','render_completed'),('render_cancel','render_cancelled')]:
        getattr(bpy.app.handlers,name).append(render_event(kind))
    stopped=threading.Event()
    def watchdog():
        while not stopped.is_set():
            remaining=(deadline-time.perf_counter_ns())/1e9
            if remaining<=0:os._exit(124)
            for name in ('worker_stdout.txt','worker_stderr.txt'):
                path=workspace/name
                if path.exists() and path.stat().st_size>64*1024*1024:os._exit(125)
            stopped.wait(min(.05,remaining))
    watchdog_thread=threading.Thread(target=watchdog,daemon=True,name='visual004-watchdog-'+uuid.uuid4().hex)
    poisoned=False
    try:
        watchdog_thread.start()
        namespace={'__name__':'__visual004_native_consumer__','bpy':bpy}
        os.environ['VISUAL004_WORKSPACE']=str(workspace)
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as server:
            server.bind(('127.0.0.1',0));server.listen(2)
            publish_ready(workspace/'READY.json',dict(host='127.0.0.1',port=server.getsockname()[1],pid=os.getpid(),
                deadline_ns=deadline,initial_fingerprint=initial,helper_sha256=sha(Path(__file__))),deadline_ns=deadline)
            sequence=0
            while not poisoned:
                if (workspace/'POISONED.json').exists():poisoned=True;break
                check(deadline);server.settimeout(max(.001,(deadline-time.perf_counter_ns())/1e9))
                connection,_=server.accept()
                with connection:
                    start=time.perf_counter_ns();sequence+=1;execution_entered=False
                    event=dict(sequence=sequence,started_ns=start,status='unknown',render_events_before=len(renders))
                    try:
                        need(not (workspace/'POISONED.json').exists(),'session_poisoned')
                        request=_read_request(connection,deadline)
                        if request.get('type')=='close':
                            response=dict(status='closed',pid=os.getpid(),deadline_ns=deadline);connection.sendall(encoded(response));break
                        need(sequence<=config['max_calls'],'call_budget')
                        if request.get('type')=='coordinator_step':
                            event['operation']='coordinator_step'
                            binding=config.get('management_steps')
                            need(binding is not None and set(request)=={'type','params'},'management_binding')
                            step=request['params'].get('step')
                            need(type(step) is int and step==management_step+1 and 1<=step<=6,'management_step_order')
                            need(protected_files_intact(config) and _scene_fingerprint(bpy)==current,'management_before')
                            check(deadline);execution_entered=True
                            codes=load(binding['path'])
                            code=codes[str(step)]
                            exec(compile(code,binding['path']+':'+str(step),'exec'),namespace)
                            check(deadline);need(protected_files_intact(config),'management_after')
                            current=_scene_fingerprint(bpy);management_step=step
                            event.update(status='management_applied',step=step,accepted_geometry_fingerprint=current)
                            response=dict(status='success',result=dict(step=step,fingerprint=current))
                        elif request.get('type')=='qa_advance':
                            event['operation']='qa_advance'
                            need(set(request)=={'type','params'} and type(request['params']) is dict
                                and set(request['params'])=={'patch_sha256'},'qa_advance_request')
                            binding=config.get('qa_vertex_patch')
                            need(binding is not None,'qa_patch_not_enabled')
                            need(not qa_advanced,'qa_patch_already_applied')
                            need(request['params']['patch_sha256']==binding['sha256'],'qa_patch_binding')
                            need(_scene_fingerprint(bpy)==current,'scene_changed_before')
                            need(protected_files_intact(config)
                                and sha(Path(__file__))==config['helper_sha256'],'source_file_changed_before')
                            check(deadline)
                            # The public broker never exposes this coordinator
                            # operation. Any failure after entry poisons the
                            # chain, including a partial vertex setter failure.
                            execution_entered=True
                            patch,_=_load_qa_vertex_patch(binding['path'],binding['sha256'])
                            outcome=_apply_qa_vertex_patch(bpy,patch)
                            check(deadline)
                            need(protected_files_intact(config)
                                and sha(Path(__file__))==config['helper_sha256'],'source_file_changed_after')
                            check(deadline)
                            need(not (workspace/'POISONED.json').exists(),'session_poisoned')
                            current=outcome['after_fingerprint'];qa_advanced=True
                            event.update(status='qa_patch_applied',patch_sha256=binding['sha256'],
                                original_fingerprint=initial,**outcome)
                            response=dict(status='success',result=dict(stage=1,patch_sha256=binding['sha256'],
                                original_fingerprint=initial,**outcome))
                        else:
                            need(set(request)=={'type','params'} and request['type']=='execute_code' and type(request['params']) is dict
                                and set(request['params'])=={'code'},'execute_code_request')
                            code=request['params']['code'];need(type(code) is str and len(code.encode('utf8'))<=MAX_CODE,'code_bytes')
                            before=_scan_pngs(workspace);need(_scene_fingerprint(bpy)==current,'scene_changed_before')
                            need(protected_files_intact(config),'source_file_changed_before')
                            call=workspace/('call_'+str(sequence));call.mkdir();(call/'SCRIPT.py').write_text(code,encoding='utf8')
                            stdout=_LimitedText();stderr=_LimitedText();script_error=None
                            try:
                                execution_entered=True
                                with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):exec(compile(code,str(call/'SCRIPT.py'),'exec'),namespace)
                            except BaseException as exc:script_error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
                            raw_out=stdout.getvalue();raw_err=stderr.getvalue()
                            (call/'stdout.txt').write_text(raw_out,encoding='utf8');(call/'stderr.txt').write_text(raw_err,encoding='utf8')
                            check(deadline)
                            need(not (workspace/'POISONED.json').exists(),'session_poisoned')
                            after=_scan_pngs(workspace);changed=[dict(path=path,**meta) for path,meta in after.items() if before.get(path)!=meta]
                            intact=_scene_fingerprint(bpy)==current and protected_files_intact(config)
                            event.update(script_sha256=hashlib.sha256(code.encode('utf8')).hexdigest(),stdout_bytes=len(raw_out.encode('utf8')),
                                stderr_bytes=len(raw_err.encode('utf8')),script_error=script_error,changed_or_new_PNG_files=changed,
                                render_events_after=len(renders),terminal_geometry_and_file_checks_passed=intact,
                                status='completed' if intact and script_error is None else 'script_failed' if intact else 'state_changed',
                                protection_scope='terminal fingerprint/file hashes plus code audit; no claim to detect reverted transient mutation or sandbox Python')
                            if not intact:poisoned=True
                            response=(dict(status='success',result=dict(executed=True,result=raw_out)) if intact and script_error is None else
                                dict(status='error',error=script_error or dict(type='StateChanged',message='terminal geometry/file protection failed'),
                                    stdout=raw_out,stderr=raw_err,poisoned=poisoned))
                    except BaseException as exc:
                        event.update(status='transport_or_guard_error',error_type=type(exc).__name__,reason=str(exc))
                        response=dict(status='error',error=dict(type=type(exc).__name__,message=str(exc)))
                        if execution_entered or time.perf_counter_ns()>=deadline or any(reason in str(exc) for reason in ('scene_changed','source_file_changed','session_poisoned')):poisoned=True
                    finally:
                        event['elapsed_ns']=time.perf_counter_ns()-start;append(audit,event)
                    wire=encoded(response);need(len(wire)<=MAX_WIRE,'response_bytes')
                    try:connection.sendall(wire)
                    except OSError as exc:
                        append(audit,dict(event='response_send_unknown',sequence=sequence,error_type=type(exc).__name__,at_ns=time.perf_counter_ns()))
                        poisoned=True
    finally:
        original=sys.exc_info()[1];stopped.set()
        try:
            if watchdog_thread.ident is not None:watchdog_thread.join(timeout=1)
            need(not watchdog_thread.is_alive(),'watchdog_cleanup')
        except BaseException as exc:
            if original is None:raise
            original.add_note('owned watchdog cleanup failed: '+repr(exc))
    closed=dict(pid=os.getpid(),closed_ns=time.perf_counter_ns(),poisoned=poisoned,
        final_geometry_fingerprint=_scene_fingerprint(bpy),initial_geometry_fingerprint=initial,
        original_deadline_ns=deadline)
    closed.update(accepted_geometry_fingerprint=current,management_step=management_step)
    if 'qa_vertex_patch' in config:
        closed.update(accepted_geometry_fingerprint=current,qa_patch_applied=qa_advanced)
    save(workspace/'WORKER_CLOSED.json',closed)

class NativeSession:
    @classmethod
    def start(cls,*,blender,asset,workspace,deadline_ns,condition='N',expected_asset_sha256=None,max_calls=64,qa_vertex_patch=None,management_steps=None):
        started=time.perf_counter_ns();check(deadline_ns)
        need(deadline_ns-started<=600*10**9,'maximum_original_window')
        need(condition in ('N','P') and type(max_calls) is int and 1<=max_calls<=128,'session_parameters')
        startup_deadline=min(deadline_ns,started+30*10**9)
        self=cls();self.process=None;self.workspace=Path(workspace).resolve();self.workspace.mkdir(parents=True,exist_ok=False)
        try:
            asset=Path(asset).resolve();blender=Path(blender).resolve();need(asset.is_file() and blender.is_file(),'asset_or_binary')
            digest=sha(asset);need(expected_asset_sha256 is None or expected_asset_sha256==digest,'asset_binding');check(startup_deadline)
            copied=self.workspace/'input.blend';shutil.copyfile(asset,copied);need(sha(copied)==digest,'asset_copy');check(startup_deadline)
            self.config=dict(schema='visual004-native-session-v1',workspace=str(self.workspace),asset=str(asset),asset_copy=str(copied),
                asset_sha256=digest,blender=str(blender),blender_sha256=sha(blender),helper_sha256=sha(Path(__file__)),
                deadline_ns=deadline_ns,condition=condition,max_calls=max_calls,started_ns=started)
            if management_steps is not None:
                step_path=Path(management_steps).resolve()
                self.config['management_steps']=dict(path=str(step_path),sha256=sha(step_path))
            if qa_vertex_patch is not None:
                patch_path=Path(qa_vertex_patch).resolve()
                _,patch_digest=_load_qa_vertex_patch(patch_path)
                self.config['qa_vertex_patch']=dict(path=str(patch_path),sha256=patch_digest)
            public_image=asset.parent/'initial.png'
            self.config['protected_public_images']=([dict(path=str(public_image),sha256=sha(public_image))] if public_image.is_file() else [])
            save(self.workspace/'CONFIG.json',self.config);check(startup_deadline)
            command=[str(blender),'--factory-startup','--disable-autoexec','--background',str(copied),
                '--python-exit-code','1','--python',str(Path(__file__).resolve()),'--','--worker',str(self.workspace/'CONFIG.json')]
            with (self.workspace/'worker_stdout.txt').open('wb') as out,(self.workspace/'worker_stderr.txt').open('wb') as err:
                self.process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=str(self.workspace),
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
            ready=self.workspace/'READY.json';check(startup_deadline)
            while not ready.exists():
                check(startup_deadline);need(self.process.poll() is None,'worker_start_failed');time.sleep(.01)
            self.ready=load(ready);check(startup_deadline)
            need(type(self.ready) is dict and set(self.ready)=={'host','port','pid','deadline_ns','initial_fingerprint','helper_sha256'},'ready_fields')
            need(type(self.ready['host']) is str and self.ready['host']=='127.0.0.1'
                and type(self.ready['port']) is int and 1<=self.ready['port']<=65535
                and type(self.ready['pid']) is int and self.ready['pid']>0 and self.ready['pid']==self.process.pid
                and type(self.ready['deadline_ns']) is int and self.ready['deadline_ns']==deadline_ns,'ready_binding')
            for name in ('helper_sha256','initial_fingerprint'):
                need(type(self.ready[name]) is str and len(self.ready[name])==64
                    and all(c in '0123456789abcdef' for c in self.ready[name]),'ready_fields')
            need(self.ready['helper_sha256']==self.config['helper_sha256'],'ready_helper_binding')
            self._check_startup_sources();check(startup_deadline)
            need(self.process.poll() is None,'worker_start_failed')
            self.config.update(pid=self.process.pid,host=self.ready['host'],port=self.ready['port'],startup_ns=time.perf_counter_ns()-started)
            save(self.workspace/'SESSION.json',self.config);check(startup_deadline)
            self._check_startup_sources();check(startup_deadline)
            need(self.process.poll() is None,'worker_start_failed');return self
        except BaseException as exc:
            cleanup_errors=[]
            try:self._kill()
            except BaseException as cleanup:cleanup_errors.append(dict(type=type(cleanup).__name__,reason=str(cleanup)))
            try:save(self.workspace/'START_FAILURE.json',dict(type=type(exc).__name__,reason=str(exc),
                elapsed_ns=time.perf_counter_ns()-started,cleanup_errors=cleanup_errors))
            except BaseException as cleanup:cleanup_errors.append(dict(type=type(cleanup).__name__,reason=str(cleanup)))
            for cleanup in cleanup_errors:exc.add_note('startup cleanup failed: '+repr(cleanup))
            raise
    def _check_startup_sources(self):
        need(protected_files_intact(self.config) and sha(self.config['blender'])==self.config['blender_sha256']
            and sha(Path(__file__))==self.config['helper_sha256'],'ready_source_binding')
    @classmethod
    def open(cls,workspace):
        self=cls();self.workspace=Path(workspace).resolve();self.process=None
        need(not (self.workspace/'START_FAILURE.json').exists(),'session_start_failed')
        self.config=load(self.workspace/'SESSION.json')
        need(not (self.workspace/'POISONED.json').exists(),'session_poisoned')
        need(sha(Path(__file__))==self.config['helper_sha256'],'helper_changed');check(self.config['deadline_ns']);return self
    @property
    def host(self):return self.config['host']
    @property
    def port(self):return self.config['port']
    def _exchange(self,request,timeout_s):
        check(self.config['deadline_ns']);need(type(timeout_s) in (int,float) and math.isfinite(timeout_s) and timeout_s>0,'call_timeout')
        limit=min(float(timeout_s),(self.config['deadline_ns']-time.perf_counter_ns())/1e9);begun=time.perf_counter_ns()
        with socket.create_connection((self.host,self.port),timeout=limit) as conn:
            conn.settimeout(limit);conn.sendall(encoded(request));conn.shutdown(socket.SHUT_WR);raw=bytearray()
            while True:
                check(self.config['deadline_ns']);remaining=limit-(time.perf_counter_ns()-begun)/1e9
                need(remaining>0,'call_timeout');conn.settimeout(remaining)
                chunk=conn.recv(65536)
                if not chunk:break
                raw.extend(chunk);need(len(raw)<=MAX_WIRE,'response_bytes')
        check(self.config['deadline_ns']);return json.loads(raw)
    def run(self,code,*,timeout_s=30):
        need(not (self.workspace/'POISONED.json').exists(),'session_poisoned')
        need(type(code) is str and len(code.encode('utf8'))<=MAX_CODE,'code_bytes');started=time.perf_counter_ns()
        try:
            response=self._exchange(dict(type='execute_code',params=dict(code=code)),timeout_s)
            return dict(response=response,elapsed_ns=time.perf_counter_ns()-started,original_deadline_ns=self.config['deadline_ns'],
                source_file_unchanged=sha(self.config['asset'])==self.config['asset_sha256'],protected_files_unchanged=protected_files_intact(self.config))
        except (OSError,TimeoutError,ValueError) as exc:
            save(self.workspace/('CLIENT_FAILURE_'+uuid.uuid4().hex+'.json'),dict(type=type(exc).__name__,reason=str(exc),elapsed_ns=time.perf_counter_ns()-started))
            self.abort('client_transport_unknown');raise
    def advance(self,step,*,timeout_s=30):
        need(not (self.workspace/'POISONED.json').exists(),'session_poisoned')
        save(self.workspace/('STEP_'+str(step)+'_ATTEMPT.json'),dict(step=step))
        started=time.perf_counter_ns()
        try:
            response=self._exchange(dict(type='coordinator_step',params=dict(step=step)),timeout_s)
            need(response.get('status')=='success','management_failed')
            receipt=dict(response=response,elapsed_ns=time.perf_counter_ns()-started)
            save(self.workspace/('STEP_'+str(step)+'_RECEIPT.json'),receipt)
            return receipt
        except BaseException:
            self.abort('management_failed_no_replay');raise
    def qa_advance(self,*,timeout_s=30):
        """One coordinator-only attempt, outside the public broker tools.

        The persistent attempt file also blocks a reopened caller from
        retrying after an unconfirmed response. Runtime access remains
        unrestricted Python under the trial's read-only consumer protocol.
        """
        need(not (self.workspace/'POISONED.json').exists(),'session_poisoned')
        binding=self.config.get('qa_vertex_patch')
        need(binding is not None,'qa_patch_not_enabled')
        need(protected_files_intact(self.config)
            and sha(Path(__file__))==self.config['helper_sha256'],'qa_patch_source_changed')
        check(self.config['deadline_ns'])
        started=time.perf_counter_ns()
        # save uses exclusive creation, serializing separate coordinator
        # clients without extending the original deadline or RPC budget.
        save(self.workspace/'QA_ADVANCE_ATTEMPT.json',dict(started_ns=started,
            patch_sha256=binding['sha256'],original_deadline_ns=self.config['deadline_ns']))
        response=None
        try:
            response=self._exchange(dict(type='qa_advance',params=dict(patch_sha256=binding['sha256'])),timeout_s)
            need(type(response) is dict and response.get('status')=='success','qa_advance_failed')
            result=response.get('result')
            need(type(result) is dict and result.get('stage')==1
                and result.get('patch_sha256')==binding['sha256'],'qa_advance_response_binding')
            need(protected_files_intact(self.config)
                and sha(Path(__file__))==self.config['helper_sha256'],'qa_patch_source_changed')
            check(self.config['deadline_ns'])
            need(not (self.workspace/'POISONED.json').exists(),'session_poisoned')
            receipt=dict(response=response,elapsed_ns_before_receipt_publish=time.perf_counter_ns()-started,
                original_deadline_ns=self.config['deadline_ns'],protected_files_unchanged=True,
                scope='coordinator patch RPC and checks; receipt publication is outside this elapsed field')
            save(self.workspace/'QA_ADVANCE_RECEIPT.json',receipt)
            check(self.config['deadline_ns'])
            need(not (self.workspace/'POISONED.json').exists(),'session_poisoned')
            return receipt
        except (OSError,TimeoutError,ValueError) as exc:
            try:
                save(self.workspace/'QA_ADVANCE_FAILURE.json',dict(response=response,type=type(exc).__name__,
                    reason=str(exc),elapsed_ns_before_failure_publish=time.perf_counter_ns()-started,
                    original_deadline_ns=self.config['deadline_ns']))
            finally:self.abort('qa_advance_failed_or_unknown_no_replay')
            raise
    def abort(self,reason):
        path=self.workspace/'POISONED.json'
        if not path.exists():save(path,dict(reason=str(reason),at_ns=time.perf_counter_ns(),original_deadline_ns=self.config['deadline_ns']))
        self._kill()
        return dict(poisoned=True,launcher_owned_process_stopped=self.process is not None and self.process.poll() is not None,
            reopened_controller_cannot_attest_kill=self.process is None)
    def _kill(self):
        if self.process is not None and self.process.poll() is None:
            self.process.kill();self.process.wait(timeout=5)
    def close(self):
        started=time.perf_counter_ns();response=None;error=None
        try:response=self._exchange(dict(type='close'),max(.01,min(5,(self.config['deadline_ns']-time.perf_counter_ns())/1e9)))
        except BaseException as exc:error=dict(type=type(exc).__name__,reason=str(exc))
        finally:
            if self.process is not None:
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self._kill()
        result=dict(schema='visual004-native-close-v1',pid=self.config['pid'],response=response,error=error,
            original_deadline_ns=self.config['deadline_ns'],elapsed_ns=time.perf_counter_ns()-started,
            source_file_unchanged=sha(self.config['asset'])==self.config['asset_sha256'],
            protected_files_unchanged=protected_files_intact(self.config),
            exit_code=None if self.process is None else self.process.poll(),
            process_reaped=self.process is not None and self.process.poll() is not None,
            scope='only launcher-owned Popen can attest wait/reap; reopened controller only requests closure')
        save(self.workspace/('CLOSE_'+uuid.uuid4().hex+'.json'),result);return result
    def status(self):
        return dict(config=self.config,ready=load(self.workspace/'READY.json'),
            closed=load(self.workspace/'WORKER_CLOSED.json') if (self.workspace/'WORKER_CLOSED.json').exists() else None,
            source_file_unchanged=sha(self.config['asset'])==self.config['asset_sha256'],protected_files_unchanged=protected_files_intact(self.config))

def main(argv=None):
    argv=sys.argv[sys.argv.index('--')+1:] if argv is None and '--' in sys.argv else argv
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--worker',type=Path)
    parser.add_argument('--workspace',type=Path);parser.add_argument('--script',type=Path);parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--close',action='store_true');args=parser.parse_args(argv)
    if args.worker:worker(args.worker);return
    need(args.workspace is not None,'workspace');session=NativeSession.open(args.workspace)
    if args.close:result=session.close()
    else:
        need(args.script is not None,'script');path=args.script.resolve();need(path.is_relative_to(args.workspace.resolve()),'script_workspace')
        result=session.run(path.read_text(encoding='utf-8-sig'),timeout_s=args.timeout)
    sys.stdout.buffer.write(encoded(result));sys.stdout.buffer.flush()

if __name__=='__main__':main()
