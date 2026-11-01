"""Native observer under the same installed trace, source and task lifecycle.

Benchmark adapter only. It does not claim the HE geometry certificate tier.
"""
import base64,copy,hashlib,json,socket,time,uuid
from pathlib import Path
from human_eye_plugin.live_service import LiveSpatialService,_request
from human_eye_plugin.structure_task import query,digest,require,TEXT_RESERVATION
from human_eye_plugin.structure_task_control import consumption
from human_eye_plugin.structure_task_service import _base
from human_eye_plugin.forward_deadline import counter_descriptor
from verification.run_native_engineering_preflight import actual_camera


def verify_helpers(spec):
    for name,expected in spec['helpers'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:raise ValueError('benchmark_helper_changed')


class NativeService(LiveSpatialService):
    def __init__(self,config_path,spec):
        super().__init__(config_path,production_mode=True)
        self.benchmark=spec

    def probe(self,operation,object_id,deadline,*,include_images=False,region=None):
        key=uuid.uuid4().hex;spec=self.benchmark
        request=dict(type='native_benchmark',params=dict(request_id=key,operation=operation,object_id=object_id,
            deadline_ns=deadline,include_images=include_images,region=region,peer_nonce=spec['peer_nonce']))
        timeout=min(30.,max(.001,(deadline-time.perf_counter_ns())/1e9));raw=b''
        with socket.create_connection((spec['host'],spec['port']),timeout=timeout) as connection:
            connection.settimeout(timeout);connection.sendall(json.dumps(request).encode())
            while True:
                part=connection.recv(65536)
                if not part:break
                raw+=part
                require(len(raw)<=16*1024*1024,'native_wire_budget')
        value=json.loads(raw)
        require(value.get('request_id')==key and value.get('peer_nonce')==spec['peer_nonce'],'native_reply_binding')
        require(value.get('deadline_ns')==deadline and value.get('clock')==counter_descriptor(),'native_clock_binding')
        require(value.get('source_before')==value.get('source_after')==spec['source_sha256'],'native_source_changed')
        require(time.perf_counter_ns()<deadline,'native_deadline')
        require(value.get('error') is None,'native_host_error:'+str(value.get('error')))
        native=value['native'];images=[];metadata=[]
        require(native.get('status')=='observed' and native.get('damage')=='not_inferred','native_facts_unavailable')
        for image in native.pop('images'):
            picture=base64.b64decode(image.pop('data'),validate=True);frame=image
            require(hashlib.sha256(picture).hexdigest()==frame['sha256'],'native_png_hash')
            require(picture[16:24]==b'\0\0\1\x80\0\0\1\x80','native_png_dimensions')
            actual_camera(frame)
            metadata.append(frame);images.append(dict(type='image',mimeType='image/png',data=base64.b64encode(picture).decode()))
        require(len(images)<=2,'native_image_budget')
        native['image_metadata']=metadata;native['capture_request_id']=key
        return native,images

    @_request('observe')
    def observe(self,session_id,*,query=None,include_image=True,focal_id=None,**kwargs):
        normalized=globals()['query'](query)
        require(not (normalized['operation']=='diagnose' and include_image),'diagnose_requires_include_image_false')
        require(not any(kwargs.get(k) is not None for k in ('goal','reference_id','scene_delta')),'native_pair_or_delta_unsupported')
        verify_helpers(self.benchmark)
        rejected=self._identity_rejection()
        if rejected is not None:return rejected
        with self._locked() as (legacy,runtime),self._observation_scope():
            require(not legacy.get('inflight') and not runtime.status['quarantined'],'host_quarantined')
            with consumption(self,normalized,20.) as store,store.locked() as state:
                require(focal_id in (None,state['object_id']),'bound_object_cannot_change')
                fingerprint=digest(dict(query=normalized,object_id=state['object_id'],include_image=include_image))
                receipt=store.reserve(state,normalized['request_id'],fingerprint,want_images=include_image)
                if receipt is not None:
                    value=_base('receipt',session_id);value.update(receipt);value['task_budget']=store.summary(state);return value
                record=state['requests'][normalized['request_id']];images=[];called=False
                value=_base('unavailable',session_id)
                deadline=min(state['deadline_ns'],time.perf_counter_ns()+30_000_000_000)
                try:
                    remaining=self._check_request_budget('before_native_host')
                    if remaining is not None:deadline=min(deadline,time.perf_counter_ns()+int(remaining*1e9))
                    selected=state['refs'].get(normalized.get('patch_ref'))
                    if normalized['operation']=='patch':require(selected is not None,'patch_ref_not_current')
                    want=normalized['operation']=='patch' and include_image and record['reserved']['images']>0
                    called=want
                    native,images=self.probe('patch' if want else 'diagnose',state['object_id'],deadline,
                        include_images=want,region=selected if want else None)
                    old={digest(v):k for k,v in state['refs'].items()};references={};regions=[]
                    for region in native.pop('regions'):
                        key=old.get(digest(region),uuid.uuid4().hex);references[key]=region
                        regions.append(dict(ref=key,bounds=region['bounds']))
                    state['refs']=references
                    value=_base('observed' if not called or images else 'partial',session_id)
                    value.update(native=native,regions=regions,region_coverage=dict(total=len(regions),omitted=0,complete=True),
                        assurance='native_shared_not_HE_independent_geometry_certificate',
                        image_status=('observed' if images else 'unavailable') if called else
                            'budget_exhausted' if include_image else 'not_requested')
                except Exception as exc:
                    images=[];value=_base('unavailable',session_id);value['reason']=str(exc)[:500]
                png_bytes=sum(len(base64.b64decode(image['data'])) for image in images)
                text_bytes=len(json.dumps(value,allow_nan=False).encode())+4096
                require(text_bytes<=TEXT_RESERVATION,'native_public_text_budget')
                store.finish(state,normalized['request_id'],text_bytes=text_bytes,images=len(images),png_bytes=png_bytes,
                    outcome=value['status'],image_outcome_known=not called or bool(images),failed=value['status']=='unavailable')
                require(time.perf_counter_ns()<deadline and time.time_ns()<state['deadline_wall_ns'],'native_delivery_deadline')
                value['task_budget']=store.summary(state);value['accounted_public_text_bytes']=text_bytes
                if images:value['routing']['images']=images
                return value


class ReadOnly:
    def __init__(self,service,spec):self.service=service;self.spec=spec
    def request_trace(self,*args,**kwargs):return self.service.request_trace(*args,**kwargs)
    def describe_runtime(self):
        value=self.service.describe_runtime();value['benchmark_arm']=self.spec['arm'];value['benchmark_read_only']=True;return value
    def observe(self,*args,**kwargs):verify_helpers(self.spec);return self.service.observe(*args,**kwargs)
    def status(self):return dict(status='ready',host_connection='not_checked',execution_authority=False,scope='owned_benchmark_only')
    def transform(self,*args,**kwargs):return dict(status='refused',executed=False,execution_authority=False,reason='benchmark_read_only')
    def run_clearance_segment(self,*args,**kwargs):return self.transform()
