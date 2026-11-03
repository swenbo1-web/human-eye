"""Pinned current-125 adapter over the existing complete deployment harness.

All actual request, PNG, worker, persistence and cleanup code is reused. The
CONFIG digest is an explicit parent CLI pin and is forwarded on every child
argv; a mutable sidecar never supplies its own trust anchor. No profiler runs.
"""
from __future__ import annotations
import argparse,hashlib,json,math,statistics,subprocess,sys,types
from pathlib import Path

BASELINE='dbeb471f3120bdb133b1ca1669dbbbd525e4679a9ec1949bc67fdba171182c47'
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_HARNESS=Path(__file__).with_name('run_deployment_cost_qualification.py')
CONFIG_NAME='SOURCE_GUARD_COST_CONFIG.json'
PIN_NAME='SOURCE_GUARD_COST_ADAPTER_PIN.json'


def need(value,reason):
    if not value:raise ValueError('source_guard_cost_'+reason)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def hex64(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def load(path):
    def pairs(items):
        v={}
        for key,child in items:
            need(key not in v,'duplicate_JSON');v[key]=child
        return v
    return json.loads(Path(path).read_bytes(),object_pairs_hook=pairs,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def save(path,value):
    with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=True,indent=2,allow_nan=False)
def absolute(value):
    need(type(value) is str,'path_type');p=Path(value)
    need(p.is_absolute() and p.resolve()==p,'canonical_path');return p


def validate_config(config):
    need(type(config) is dict and set(config)=={'schema','workspace','python','blender','harness_sha256','gate_file','gate_sha256','arms'},'config_fields')
    need(config['schema']=='source-guard-cost-config-v1' and hex64(config['harness_sha256']) and hex64(config['gate_sha256']),'config_schema')
    absolute(config['workspace'])
    for key in ('python','blender'):
        pin=config[key];need(type(pin) is dict and set(pin)=={'path','sha256'} and hex64(pin['sha256']),'dependency_pin')
        need(sha(absolute(pin['path']))==pin['sha256'],'dependency_changed')
    need(sha(absolute(config['gate_file']))==config['gate_sha256'],'gate_changed')
    gate=load(config['gate_file']);need(gate['schema']=='source-guard-cost-gates-v1' and gate['pairs']==8 and gate['hot_per_kind']==3
        and gate['baseline_source_sha256']==BASELINE and gate['baseline_source_file_count']==125,'gate_scope')
    arms=config['arms'];need(type(arms) is dict and set(arms)=={'old','candidate'},'arms')
    for name,pin in arms.items():
        need(type(pin) is dict and set(pin)=={'release','entry','entry_sha256','binding_sha256','source_sha256','source_file_count'},'arm_fields')
        need(pin['source_file_count']==125 and type(pin['source_file_count']) is int,'source_count')
        need(all(hex64(pin[k]) for k in ('entry_sha256','binding_sha256','source_sha256')),'arm_pin')
        if name=='old':need(pin['source_sha256']==BASELINE,'baseline')
        release=absolute(pin['release']);entry=absolute(pin['entry'])
        need(entry==release/'admin/target_runtime_entry.py','entry_role')
        need(sha(entry)==pin['entry_sha256'] and sha(entry.with_name('RUNTIME_BINDING.json'))==pin['binding_sha256'],'entry_binding_changed')
        binding=load(entry.with_name('RUNTIME_BINDING.json'))
        need(binding['identity']['source_sha256']==pin['source_sha256'] and len(binding['source_files'])==125,'binding_identity')
        need(binding['kind']=='human_eye_fixed_target_runtime' and Path(binding['target_release'])==release
            and Path(binding['site_packages'])==release/'site-packages'
            and Path(binding['dependency_python'])==Path(config['python']['path'])
            and binding['launcher_sha256']==pin['entry_sha256'],'binding_role')
    need(arms['candidate']['source_sha256']!=BASELINE and arms['candidate']['entry']!=arms['old']['entry'],'distinct_candidate')
    return config


class PinnedSubprocess:
    """Delegate original subprocess calls, appending independent child pins."""
    def __init__(self,script,config_path,config_sha256):self.script=str(script);self.path=str(config_path);self.digest=config_sha256
    def __getattr__(self,name):return getattr(subprocess,name)
    def command(self,args):
        if type(args) is list and self.script in args:
            need('--configuration' not in args and '--configuration-sha256' not in args,'duplicate_child_pin')
            return [*args,'--configuration',self.path,'--configuration-sha256',self.digest]
        return args
    def Popen(self,args,*a,**kw):return subprocess.Popen(self.command(args),*a,**kw)
    def run(self,args,*a,**kw):return subprocess.run(self.command(args),*a,**kw)


def harness(config,config_path,config_sha256):
    raw=DEFAULT_HARNESS.read_bytes();need(hashlib.sha256(raw).hexdigest()==config['harness_sha256'],'harness_changed')
    module=types.ModuleType('_source_guard_reused_cost');module.__file__=str(DEFAULT_HARNESS)
    exec(compile(raw,str(DEFAULT_HARNESS),'exec',dont_inherit=True),module.__dict__)
    module.__file__=str(Path(__file__).resolve());module.ROOT=Path(config['workspace']);module.EVIDENCE=Path(config_path).parent
    module.PYTHON=Path(config['python']['path']);module.BLENDER=Path(config['blender']['path'])
    module.ARMS={name:dict(release=Path(pin['release']).name,count=125,sha=pin['source_sha256']) for name,pin in config['arms'].items()}
    module.arm_paths=lambda name:(Path(config['arms'][name]['release']),Path(config['arms'][name]['release'])/'site-packages',Path(config['arms'][name]['entry']))
    module.subprocess=PinnedSubprocess(Path(__file__).resolve(),config_path,config_sha256)
    return module


def _series(rows,kind):
    groups={arm:{} for arm in ('old','candidate')};raw={arm:[] for arm in groups}
    for row in rows:
        if row.get('lane')!='default_fixed_entry_external_qa_tcp':continue
        values=[c['complete_ns'] for c in row['calls'] if c['kind']==kind]
        groups[row['arm']][row['pair']]=statistics.median(values);raw[row['arm']].extend(values)
    return groups,raw
def _summary(values):return dict(median_ns=statistics.median(values),p95_ns=sorted(values)[math.ceil(.95*len(values))-1],n=len(values))
def _bounded(old,new,absolute_ns,relative):return new<=old+max(absolute_ns,relative*old)


def source_spans(output):
    values={kind:{arm:{} for arm in ('old','candidate')} for kind in ('ordinary_gap_text','hot_native')}
    for pair in range(8):
        for arm in ('old','candidate'):
            folder=output/f'DEPLOYMENT_COST_{pair:02d}_{arm}_tcp';events=[load_line(v) for v in (folder/'events.jsonl').read_text('utf8').splitlines()]
            traces={e['trace']['trace_id']:e['trace'] for e in events if e.get('event')=='request_trace'}
            for kind in values:
                measured=[]
                for p in folder.glob('*_'+kind+'.json'):
                    response=load(p);texts=[v['text'] for v in response['result']['content'] if v['type']=='text'];need(len(texts)==1,'trace_metadata')
                    metadata=json.loads(texts[0]);trace_id=metadata['request_trace']['trace_id'];trace=traces[trace_id]
                    spans=[s['duration_ns'] for s in trace['spans'] if s['name']=='runtime.source_check'];need(len(spans)==1,'source_span_count')
                    need(type(spans[0]) is int and spans[0]>=0,'source_span_duration');measured.append(spans[0])
                need(len(measured)==3,'source_samples');values[kind][arm][pair]=statistics.median(measured)
    return values
def load_line(raw):return json.loads(raw)


def validate_rows(rows):
    need(type(rows) is list and len(rows)==32,'registered_lane_count');seen=set()
    for row in rows:
        lane=row['lane'];need(lane in ('default_fixed_entry_external_qa_tcp','owned_fixed_file_worker'),'lane')
        arm=row['arm'];pair=row['pair'];need(arm in ('old','candidate') and type(pair) is int and 0<=pair<8,'slot')
        slot=(lane,arm,pair);need(slot not in seen,'duplicate_slot');seen.add(slot)
        need(row['status']==('completed' if lane=='default_fixed_entry_external_qa_tcp' else 'passed'),'outcome')
        timers=('cold_service_complete_ns','cold_first_native_complete_ns','service_complete_cycle_ns') if lane=='default_fixed_entry_external_qa_tcp' else ('complete_cycle_ns',)
        need(all(type(row[k]) is int and row[k]>0 for k in timers),'timer')
        if lane=='default_fixed_entry_external_qa_tcp':
            expected={('cold_native',0),*((kind,i) for kind in ('hot_native','ordinary_gap_text','status') for i in range(3))}
            calls=row['calls'];need(len(calls)==10 and {(c['kind'],c['repetition']) for c in calls}==expected,'call_count_or_slot')
            need(all(c['status']=='passed' and type(c['complete_ns']) is int and c['complete_ns']>0 and type(c['repetition']) is int for c in calls),'call_outcome')
            need(row['external_blender_exit_code']==0,'server_exit')
        else:need(row['detail']['process_reaped'] is True and type(row['detail']['setters']) is int and row['detail']['setters']==0,'owned_cleanup')
    return True


def evaluate(result,source_checks):
    checks=[]
    try:validate_rows(result['rows'])
    except (KeyError,ValueError,TypeError) as exc:return dict(passed=False,checks=[],reason=str(exc),all_attempts_retained=True)
    rows=result['rows']
    for kind in ('ordinary_gap_text','hot_native'):
        groups,raw=_series(rows,kind);old=[groups['old'][i] for i in range(8)];new=[groups['candidate'][i] for i in range(8)];improvement=[a-b for a,b in zip(old,new)]
        o,n=_summary(raw['old']),_summary(raw['candidate']);s=source_checks[kind];source_old=[s['old'][i] for i in range(8)];source_new=[s['candidate'][i] for i in range(8)]
        entry=dict(metric=kind,block_median_improvement_ns=statistics.median(improvement),improved_blocks=sum(v>0 for v in improvement),baseline=o,candidate=n,
            source_block_median_improvement_ns=statistics.median(a-b for a,b in zip(source_old,source_new)),source_required_improvement_ns=max(1e6,.05*statistics.median(source_old)))
        entry['passed']=entry['block_median_improvement_ns']>=1e6 and entry['improved_blocks']>=6 and entry['source_block_median_improvement_ns']>=entry['source_required_improvement_ns'] and _bounded(o['p95_ns'],n['p95_ns'],1e6,.02)
        checks.append(entry)
    for kind in ('status',):
        _,raw=_series(rows,kind);o,n=_summary(raw['old']),_summary(raw['candidate']);checks.append(dict(metric=kind,baseline=o,candidate=n,passed=all(_bounded(o[k],n[k],.5e6,.05) for k in ('median_ns','p95_ns'))))
    for field,lane in [('cold_service_complete_ns','default_fixed_entry_external_qa_tcp'),('cold_first_native_complete_ns','default_fixed_entry_external_qa_tcp'),('service_complete_cycle_ns','default_fixed_entry_external_qa_tcp'),('complete_cycle_ns','owned_fixed_file_worker')]:
        o,n=(_summary([r[field] for r in rows if r['lane']==lane and r['arm']==arm]) for arm in ('old','candidate'))
        checks.append(dict(metric=field,baseline=o,candidate=n,passed=all(_bounded(o[k],n[k],20e6,.05) for k in ('median_ns','p95_ns'))))
    return dict(passed=all(v['passed'] for v in checks),checks=checks,all_attempts_retained=True,old_M1_M2_failures_unchanged=True,scope='One preregistered current125 derivative; no release/global model-speed claim')


def main(argv=None):
    argv=sys.argv[sys.argv.index('--')+1:] if argv is None and '--' in sys.argv else argv
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['preregister','run','qa-server','owned-child','create-fixture']);p.add_argument('--output',type=Path);p.add_argument('--arm',choices=['old','candidate']);p.add_argument('--fixture',type=Path)
    p.add_argument('--configuration',type=Path,required=True);p.add_argument('--configuration-sha256',required=True);args=p.parse_args(argv)
    config_path=args.configuration.resolve();need(hex64(args.configuration_sha256) and sha(config_path)==args.configuration_sha256,'external_config_pin');config=validate_config(load(config_path))
    output=args.output.resolve() if args.output is not None else args.fixture.resolve().parent;artifact_root=output if args.mode in ('preregister','run') else config_path.parent
    if args.mode=='preregister':
        output.mkdir(parents=True,exist_ok=False);copy=output/CONFIG_NAME;copy.write_bytes(config_path.read_bytes());config_path=copy
        save(output/PIN_NAME,dict(schema='source-guard-cost-adapter-pin-v1',configuration_sha256=args.configuration_sha256,gate_sha256=config['gate_sha256'],wrapper_sha256=sha(Path(__file__)),harness_sha256=config['harness_sha256']))
        (output/Path(__file__).name).write_bytes(Path(__file__).read_bytes());(output/DEFAULT_HARNESS.name).write_bytes(DEFAULT_HARNESS.read_bytes())
    else:
        need(config_path==artifact_root/CONFIG_NAME,'registered_config_path');pin=load(artifact_root/PIN_NAME)
        need(pin==dict(schema='source-guard-cost-adapter-pin-v1',configuration_sha256=args.configuration_sha256,gate_sha256=config['gate_sha256'],wrapper_sha256=sha(Path(__file__)),harness_sha256=config['harness_sha256']),'registered_artifact_changed')
    h=harness(config,config_path,args.configuration_sha256)
    if args.mode=='preregister':h.preregister(output,'both')
    elif args.mode=='run':
        h.run(output);result=load(output/'DEPLOYMENT_COST_RESULT.json')
        try:validate_rows(result['rows']);summary=evaluate(result,source_spans(output))
        except (OSError,KeyError,ValueError,TypeError) as exc:summary=dict(passed=False,checks=[],reason=str(exc),all_attempts_retained=True)
        save(output/'SOURCE_GUARD_COST_GATE_RESULT.json',summary);print(json.dumps(dict(performance_gate_passed=summary['passed'])))
    elif args.mode=='qa-server':need(output.is_relative_to(artifact_root),'output_scope');h.qa_server(args.arm,output)
    elif args.mode=='owned-child':need(output.is_relative_to(artifact_root),'output_scope');h.owned_child(args.arm,args.fixture,output)
    else:need(args.fixture.resolve().is_relative_to(artifact_root),'fixture_scope');h.create_fixture(args.fixture)
    return 0


if __name__=='__main__':raise SystemExit(main())
