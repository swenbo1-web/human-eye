"""Real read-only refusal/lifetime tests and outside-RNA observation."""
import argparse,copy,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.dont_write_bytecode=True


def main(args):
    sys.path.insert(0,str(args.core_root))
    from human_eye_plugin.rig_constraint_process import RigConstraintProcess
    from human_eye_plugin import rig_constraint as c
    from human_eye_plugin.runtime_identity import runtime_identity
    r=c.r;args.output.mkdir(exist_ok=False);rows=[];profiles=args.profiles
    def load(name):return r.decode((profiles/name/'PROFILE.json').read_bytes())
    def save(path,value):
        with path.open('xb') as f:f.write(r.encoded(value))
    def actor(name,p):
        folder=args.output/name;folder.mkdir();save(folder/'PROFILE.json',p);return RigConstraintProcess(folder/'PROFILE.json'),folder
    base=load('target_y')
    for name,change in (('wrong_frame',dict(expected_frame=dict(number=2,subframe=0.))),
        ('wrong_target',dict(target_name='Missing')),('wrong_owner',dict(constraint_bone='bone_000'))):
        a,folder=actor(name,dict(base,**change))
        try:
            try:a.inspect()
            except ValueError as exc:save(folder/'RESULT.json',dict(refused=True,reason=str(exc)));rows.append(dict(test=name,refused=True))
            else:raise AssertionError(name)
        finally:a.close()
    a,folder=actor('worker_refusals',base)
    try:
        errors=[]
        for index,command,deadline in ((91,'inspect',a.deadline_ns+1),(92,'move',a.deadline_ns)):
            a.process.stdin.write(r.encoded(dict(id=index,command=command,deadline_ns=deadline))+b'\n');a.process.stdin.flush();reply=a._next()
            assert reply['kind']=='error' and reply['id']==index and reply['geometry_setters']==0;errors.append(reply)
        first=a.inspect();save(folder/'RESULT.json',dict(errors=errors,subsequent_valid_read=True,source_sha256=first['source_sha256']))
        assert 'original_window' in errors[0]['reason'] and 'readonly_command' in errors[1]['reason'];rows.append(dict(test='worker_refusals',refused=2))
    finally:a.close()
    a,folder=actor('lifetime16',base)
    try:
        packets=[a.inspect() for _ in range(16)];assert len({p['source_sha256'] for p in packets})==1
        try:a.inspect()
        except ValueError as exc:assert 'lifetime' in str(exc);reason=str(exc)
        else:raise AssertionError('seventeenth read allowed')
        save(folder/'RESULT.json',dict(reads=16,seventeenth_refused=True,reason=reason,original_deadline_ns=a.deadline_ns))
        rows.append(dict(test='lifetime16',read=16,refused=1))
    finally:a.close()
    original=subprocess.Popen;wrapper=ROOT/'verification/fixtures/rig_constraint_rna_audit.py';audits=[]
    for name in ('target_y','world_parent_combo','rolled_rest','root_constraint','limit64','singular_swing'):
        folder=args.output/('audit_'+name);folder.mkdir();save(folder/'PROFILE.json',load(name))
        def spawn(command,**kwargs):
            cmd=list(command);index=cmd.index('--python')+1;cmd[index]=str(wrapper)
            kwargs['env']=dict(os.environ,HUMAN_EYE_CONSTRAINT_AUDIT_OUTPUT=str(folder));return original(cmd,**kwargs)
        a=None
        try:
            with patch('human_eye_plugin.rig_constraint_process.subprocess.Popen',side_effect=spawn):a=RigConstraintProcess(folder/'PROFILE.json')
            first=a.inspect();second=a.inspect();assert first['source_sha256']==second['source_sha256'];report=c.analyze(second,deadline_ns=a.deadline_ns)
            save(folder/'SNAPSHOTS.json',dict(first=first,second=second));save(folder/'REPORT.json',report)
        finally:
            if a is not None:a.close()
        result=r.decode((folder/'INDEPENDENT_RESULT.json').read_bytes());assert result['identical']
        assert (folder/'INDEPENDENT_BEFORE.json').read_bytes()==(folder/'INDEPENDENT_AFTER.json').read_bytes()
        audits.append(dict(case=name,**result))
    for p in profiles.glob('*/PROFILE.json'):
        value=r.decode(p.read_bytes());assert hashlib.sha256(Path(value['scene_file']).read_bytes()).hexdigest()==value['scene_sha256']
    save(args.output/'RESULT.json',dict(fault_groups=rows,outside_audits=audits,runtime_source_sha256=runtime_identity()['source_sha256'],
        geometry_setters=0,original_file_saved=False,shared_GUI=False));print(json.dumps(dict(groups=len(rows),outside_audits=len(audits),passed=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--core-root',type=Path,default=ROOT);p.add_argument('--profiles',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
