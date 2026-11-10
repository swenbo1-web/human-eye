"""Documented small extension of the previously owned fixture for fixed T steps."""
from pathlib import Path
import hashlib, json
HERE=Path(__file__).resolve().parent
original=HERE.parent/'native_plugin_complex_003/reused/accepted_native.py'
raw=original.read_bytes()
text=raw.decode('utf8').replace('\r\n','\n')
def replace(old,new):
    global text
    assert text.count(old)==1,old
    text=text.replace(old,new)
replace("and ('qa_vertex_patch' not in config", "and ('management_steps' not in config or sha(config['management_steps']['path'])==config['management_steps']['sha256'])\n        and ('qa_vertex_patch' not in config")
replace('current=initial;qa_advanced=False','current=initial;qa_advanced=False;management_step=0')
replace("if request.get('type')=='qa_advance':", """if request.get('type')=='coordinator_step':
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
                        elif request.get('type')=='qa_advance':""")
replace("if 'qa_vertex_patch' in config:\n        closed.update", "closed.update(accepted_geometry_fingerprint=current,management_step=management_step)\n    if 'qa_vertex_patch' in config:\n        closed.update")
replace('max_calls=64,qa_vertex_patch=None):','max_calls=64,qa_vertex_patch=None,management_steps=None):')
replace('if qa_vertex_patch is not None:\n',"if management_steps is not None:\n                step_path=Path(management_steps).resolve()\n                self.config['management_steps']=dict(path=str(step_path),sha256=sha(step_path))\n            if qa_vertex_patch is not None:\n")
replace('    def qa_advance(self,*,timeout_s=30):', '''    def advance(self,step,*,timeout_s=30):
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
    def qa_advance(self,*,timeout_s=30):''')
(HERE/'session.py').write_text(text,encoding='utf8',newline='\n')
(HERE/'SESSION_ORIGIN.json').write_text(json.dumps({'origin':str(original),'sha256':hashlib.sha256(raw).hexdigest(),
    'new_sha256':hashlib.sha256(text.encode()).hexdigest(),'scope':'fixed coordinator-only steps, outside solver; same deadlines, readonly fingerprint and file checks retained'},indent=2)+'\n',encoding='utf8',newline='\n')
