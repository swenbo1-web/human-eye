"""Explicit small-source product entry, reusing owned FK transport lifetime.

The trusted fixed profile and verified worker handshake supply expectations.
No packet self-description, research status or model flag grants admission.
"""
import argparse,hashlib,queue,subprocess,threading,time
from pathlib import Path
from . import small_skin_source as core,surface_deformation
from .rig_pose_process import RigPoseProcess
from .skin_source_process import run_reader
from .surface_owned import pinned_file
from .runtime_identity import runtime_identity,check_source_drift
r=core.r


def worker_error(value):
    reason=value.get('reason','worker_error')
    if reason.startswith('small_skin_'):reason=reason[len('small_skin_'):]
    raise core.SmallSourceError(reason,'unavailable' if reason in ('original_deadline','scene_changed','runtime_changed','fixed_frame','fixed_unit') else 'unsupported')


def pin_input(path,digest,maximum,kind):
    try:return pinned_file(path,digest,maximum)
    except (ValueError,OSError) as exc:raise core.SmallSourceError(kind+'_pin','unavailable') from exc


class SmallSkinSourceProcess(RigPoseProcess):
    def __init__(self,profile_path):
        self.received_ns=time.perf_counter_ns();self.deadline_ns=self.received_ns+30_000_000_000
        self.path=Path(profile_path);core.need(self.path.is_absolute() and self.path.resolve()==self.path,'profile_path')
        with self.path.open('rb') as f:self.profile_bytes=f.read(65537)
        core.need(len(self.profile_bytes)<=65536,'profile_byte_budget');p=self.profile=r.decode(self.profile_bytes)
        core.fields(p,{'schema','blender_executable','blender_sha256','scene_file','scene_sha256','mesh_name','rig_name','expected_frame','unit_scale_m','runtime_source_sha256'},'profile_fields')
        core.need(p['schema']=='small-skin-source-operator-profile-v1' and r.text(p['mesh_name']) and r.text(p['rig_name']) and p['mesh_name']!=p['rig_name'],'profile_roles')
        core.fields(p['expected_frame'],{'number','subframe'},'profile_frame')
        core.need(type(p['expected_frame']['number']) is int and r.finite(p['expected_frame']['subframe']) and 0<=p['expected_frame']['subframe']<1,'profile_frame')
        core.need(r.finite(p['unit_scale_m']) and 0<p['unit_scale_m']<=1e6,'profile_unit')
        core.need(check_source_drift()['compatible'] and runtime_identity()['source_sha256']==p['runtime_source_sha256'],'runtime_pin','unavailable')
        pin_input(p['blender_executable'],p['blender_sha256'],128*1024*1024,'binary');pin_input(p['scene_file'],p['scene_sha256'],64*1024*1024,'scene')
        root=Path(__file__).resolve().parents[1];worker=root/'human_eye_plugin/small_skin_source_worker.py'
        self.module_sha=hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest();self.math_sha=hashlib.sha256(Path(r.__file__).read_bytes()).hexdigest()
        self.worker_sha=hashlib.sha256(worker.read_bytes()).hexdigest();self.queue=queue.Queue(maxsize=16);self.closed=False
        self.sequence=0;self.diagnostics=[];self.source=None;self._gate=threading.Lock();core.check(self.deadline_ns)
        self.process=subprocess.Popen([p['blender_executable'],'--factory-startup','--disable-autoexec','--background',p['scene_file'],'--python-exit-code','73',
            '--python',str(worker),'--','--root',str(root),'--profile',str(self.path),'--profile-sha256',hashlib.sha256(self.profile_bytes).hexdigest(),
            '--module-sha256',self.module_sha,'--math-sha256',self.math_sha,'--worker-sha256',self.worker_sha,'--deadline-ns',str(self.deadline_ns)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
        def read():
            try:
                while True:
                    blob=self.process.stdout.readline(r.MAX_BYTES+1)
                    if not blob:break
                    core.need(len(blob)<=r.MAX_BYTES,'response_byte_budget')
                    if blob.startswith(b'HUMAN_EYE_SMALL_SKIN:'):self.queue.put_nowait(r.decode(blob[len(b'HUMAN_EYE_SMALL_SKIN:'):]))
                    elif len(self.diagnostics)<16:self.diagnostics.append(blob[:512].decode('utf8','replace'))
            except Exception:pass
            finally:
                try:self.queue.put_nowait(None)
                except queue.Full:pass
        def stderr():
            while True:
                blob=self.process.stderr.readline(513)
                if not blob:break
                if len(self.diagnostics)<16:self.diagnostics.append(blob.decode('utf8','replace'))
        try:
            threading.Thread(target=read,daemon=True).start();threading.Thread(target=stderr,daemon=True).start()
            ready=self._next()
            if ready.get('kind')=='error':
                core.need(set(ready)=={'kind','id','reason','geometry_setters'} and ready['id'] is None and r.text(ready['reason'])
                    and type(ready['geometry_setters']) is int and ready['geometry_setters']==0,'startup_error_binding','unavailable')
                worker_error(ready)
            expected=dict(protocol=core.PROTOCOL,process_id=self.process.pid,scene_sha256=p['scene_sha256'],profile_sha256=hashlib.sha256(self.profile_bytes).hexdigest(),
                module_sha256=self.module_sha,math_sha256=self.math_sha,worker_sha256=self.worker_sha,binary_sha256=p['blender_sha256'],runtime_source_sha256=p['runtime_source_sha256'])
            core.need(ready.get('kind')=='ready' and all(type(ready.get(k)) is type(v) and ready[k]==v for k,v in expected.items()),'worker_binding','unavailable')
            frame=ready.get('frame')
            core.need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int and r.finite(frame['subframe'])
                and 0<=frame['subframe']<1 and r.finite(ready.get('unit_scale_m'))
                and type(ready.get('deadline_ns')) is int and ready['deadline_ns']==self.deadline_ns and frame==p['expected_frame']
                and ready['unit_scale_m']==p['unit_scale_m'],'worker_frame_unit_binding','unavailable')
            core.need(ready.get('read_only') is True and type(ready.get('geometry_setters')) is int and ready['geometry_setters']==0
                and ready.get('saves_file') is False and ready.get('sets_frame') is False and ready.get('generic_exec') is False
                and type(ready.get('max_requests')) is int and ready['max_requests']==16 and type(ready.get('byte_limit')) is int
                and ready['byte_limit']==r.MAX_BYTES,'worker_capabilities','unavailable')
            self.bindings=core.ExternalBinding(**{k:v for k,v in expected.items() if k!='protocol'},mesh_name=p['mesh_name'],rig_name=p['rig_name'],
                expected_frame=(p['expected_frame']['number'],p['expected_frame']['subframe']),unit_scale_m=p['unit_scale_m'],document_epoch=ready['document_epoch'],
                mesh_identity=dict(identity=ready['mesh_identity'],data_identity=ready['mesh_data_identity']),
                rig_identity=dict(identity=ready['rig_identity'],data_identity=ready['rig_data_identity']))
            self.capabilities=ready;core.check(self.deadline_ns)
        except BaseException:self.close();raise

    def verify_inputs(self):
        core.check(self.deadline_ns)
        with self.path.open('rb') as f:blob=f.read(65537)
        core.need(blob==self.profile_bytes and check_source_drift()['compatible'],'profile_or_runtime_changed','unavailable')
        p=self.profile
        pin_input(p['scene_file'],p['scene_sha256'],64*1024*1024,'scene');pin_input(p['blender_executable'],p['blender_sha256'],128*1024*1024,'binary');core.check(self.deadline_ns)

    def _inspect(self):
        core.need(not self.closed,'closed_transport','unavailable');self.verify_inputs()
        core.need(self.sequence<16,'request_lifetime','unavailable')
        self.sequence+=1;self.process.stdin.write(r.encoded(dict(id=self.sequence,command='inspect',deadline_ns=self.deadline_ns))+b'\n');self.process.stdin.flush()
        value=self._next()
        if value.get('kind')=='error':
            core.need(set(value)=={'kind','id','reason','geometry_setters'} and type(value['id']) is int and value['id']==self.sequence
                and r.text(value['reason']) and type(value['geometry_setters']) is int and value['geometry_setters']==0,'error_reply_binding','unavailable')
            worker_error(value)
        core.need(value.get('kind')=='snapshot' and type(value.get('id')) is int and value['id']==self.sequence and set(value)=={'kind','id','packet'},'reply_binding','unavailable')
        packet=value['packet'];core.validate(packet,deadline_ns=self.deadline_ns,expected_bindings=self.bindings,expected_source=self.source)
        if self.source is None:self.source=packet['source_sha256']
        return packet

    def analyze(self,packet,*,deadline_ns,query=None):
        core.need(deadline_ns==self.deadline_ns and not self.closed,'analysis_window','unavailable')
        core.need(self.source is not None,'observation_required','unavailable')
        self.verify_inputs()
        proof=core.validate(packet,deadline_ns=deadline_ns,expected_bindings=self.bindings,expected_source=self.source)
        proof['source']=dict(proof['source'],source_sha256=packet['source_sha256'],source_schema=core.SCHEMA,
            profile_sha256=self.bindings.profile_sha256,runtime_source_sha256=self.bindings.runtime_source_sha256,
            worker_sha256=self.bindings.worker_sha256,module_sha256=self.bindings.module_sha256,math_sha256=self.bindings.math_sha256,binary_sha256=self.bindings.binary_sha256)
        report=surface_deformation._analyze_geometry(proof,deadline_ns=deadline_ns,query=query)
        report['source_validation']=dict(schema=core.SCHEMA,method='external_binding_full_dependency_FK_and_LBS',
            max_replay_error=proof['max_replay_error'],replay_atol=core.POSITION_ATOL,animation_curves_checked=proof['animation_curves_checked'],
            not_coordinate_measurement_error=True)
        self.verify_inputs();return report

    def bind_selection(self,packet,selection,*,deadline_ns):
        core.need(deadline_ns==self.deadline_ns and not self.closed,'selection_window','unavailable')
        core.need(self.source is not None,'observation_required','unavailable')
        self.verify_inputs()
        proof=core.validate(packet,deadline_ns=deadline_ns,expected_bindings=self.bindings,expected_source=self.source)
        r.require(type(selection) is dict and set(selection)=={'schema','source_ref','triangle_indices'} and selection['schema']=='surface-deformation-selection-v1','deformation_selection_fields')
        ref=selection['source_ref'];r.require(type(ref) is dict and set(ref)=={'scene_sha256','rig_object_id','mesh_object_id','frame'},'deformation_selection_source_fields')
        frame=ref['frame'];r.require(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int and r.finite(frame['subframe']) and 0<=frame['subframe']<1,'deformation_selection_frame')
        wanted=dict(scene_sha256=proof['source']['scene_sha256'],rig_object_id=proof['source']['object_id'],
            mesh_object_id=proof['source']['mesh_identity']['object_id'],frame=proof['source']['frame'])
        r.require(ref==wanted,'deformation_selection_stale_source');ids=surface_deformation.query_indices(selection['triangle_indices'],len(proof['triangles']))
        self.verify_inputs();return dict(schema='surface-deformation-query-v1',expected_source_sha256=packet['source_sha256'],triangle_indices=ids)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Read one fixed small current-frame LBS source; no edit, frame or save commands')
    parser.add_argument('--operator-profile',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--triangle-query',type=Path)
    return run_reader(parser.parse_args(argv),SmallSkinSourceProcess,
        analyzer=lambda packet,actor,**kw:actor.analyze(packet,**kw),selection_binder=lambda packet,selection,actor,**kw:actor.bind_selection(packet,selection,**kw),close_before_publish=True)


if __name__=='__main__':raise SystemExit(main())
