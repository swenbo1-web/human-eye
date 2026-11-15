import hashlib,json,re,time,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;P=HERE/'snapshot/verification/m6_perception_data_001'
n=0
def j(name):return json.loads((P/name).read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def check(v,why):
 global n
 n+=1;assert v,why
def natural(name):return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)',name)]
def main():
 start=time.perf_counter();cpu=time.process_time();freeze=j('PLAN_FREEZE.json')
 for r in freeze['files']+freeze['actual_source_inputs']:
  b=(P/r['path']).read_bytes();check(sha(b)==r['sha256'] and len(b)==r['bytes'],'freeze '+r['path'])
 sources=j('SOURCE_INDEX.json');byasset={}
 for source in sources['meshes']:byasset.setdefault(source['asset'],[]).append(source)
 for archive in sources['archives']:
  asset=Path(archive['path']).name.split('-poses')[0]
  with zipfile.ZipFile(P/archive['path']) as z:
   members={x.filename:x for x in z.infolist()}
   for info in archive['members']:
    actual=members[info['name']];check(actual.file_size==info['bytes'] and actual.CRC==info['crc32'],'archive member')
   geometry=[x for x in members if Path(x).suffix.lower() in ('.obj','.pose')]
   references=[x for x in geometry if 'reference' in Path(x).stem.lower()];check(len(references)==1,'single reference')
   other=sorted([x for x in geometry if x not in references],key=natural)
   chosen={x['posture']:x['member'] for x in byasset[asset]}
   check(chosen=={'reference':references[0],'pose1':other[0]},'fixed natural first selection')
   for doc in sources['documents']:
    if doc['asset']==asset:check(z.read(doc['member'])==(P/doc['path']).read_bytes(),'archive README bytes')
 scripts=list(P.glob('*.py'))+list((P/'private/recovery').glob('*.py'))
 hashes={sha(p.read_bytes()):str(p.relative_to(P)) for p in scripts}
 costs=j('COSTS.json');phases=costs['phases']
 for label,row in phases.items():
  check(j('private/processes/'+label+'.controller.json')==row['controller'],'raw controller')
  check(j('private/processes/'+label+'.json')==row['worker'],'raw worker')
  check(row['controller']['worker_source_sha256'] in hashes,'executed source retained')
  check(row['controller']['returncode']==row['worker']['returncode'],'phase return status')
 failed={name for name,r in phases.items() if r['controller']['returncode']!=0}
 check(failed=={'acquire','acquire_extension_recovery'},'two acquisition errors retained')
 total=sum(r['controller']['wall_s'] for r in phases.values());numeric=sum(r['controller']['wall_s'] for r in phases.values() if r['controller']['compute_budget_counted'])
 check(abs(total-costs['all_monitored_phase_wall_s'])<1e-9,'total wall')
 check(abs(numeric-costs['numerical_monitored_wall_s'])<1e-9,'numeric wall')
 check(abs(numeric+costs['ad_hoc_readonly_shell_envelope_upper_sum_s']-costs['numerical_budget_accounting_upper_s'])<1e-9,'numeric upper accounting')
 check(sum(r['worker']['tree_cpu_s'] for r in phases.values())==costs['monitored_tree_CPU_s'],'CPU sum')
 check(max(r['worker']['tree_sampled_peak_working_set_bytes'] for r in phases.values())==costs['max_sampled_simultaneous_tree_RSS_bytes'],'peak RSS')
 check(sum(r['bytes'] for r in sources['archives'])==costs['archive_HTTP_body_bytes'],'archive transfer bytes')
 check(sources['primary_page']['bytes']==costs['source_page_HTTP_body_bytes'],'page bytes')
 check(abs(costs['elapsed_task_wall_s']-total-costs['authoring_reading_inspection_and_tool_wait_residual_wall_s'])<1e-9,'elapsed remainder')
 source_views=['horse_reference','horse_pose1','camel_reference','camel_pose1','face_reference','face_pose1','head_reference','head_pose1']
 pair_views=['horse_reference','face_reference','cat_pose1']
 viewed=[{'path':'private/views/source/'+s+'.png','sha256':sha((P/'private/views/source'/ (s+'.png')).read_bytes()),'observation':'Displayed all three source axes; positive winding arrow leaves visible muzzle/hoof/nose exterior. Open-surface direction is visual interpretation, not a closed-volume proof.'} for s in source_views]
 viewed +=[{'path':'private/views/pairs/'+s+'.png','sha256':sha((P/'private/views/pairs'/(s+'.png')).read_bytes()),'observation':'Displayed matched current geometry; preserved cat_pose1 failure. Numeric formula/labels verified separately.'} for s in pair_views]
 out={'status':'passed','assertions':n,'frozen_public_records':len(freeze['files']),'frozen_source_arrays':len(freeze['actual_source_inputs']),'source_archives':len(sources['archives']),
      'author_monitored_phases':len(phases),'author_failed_phases':sorted(failed),'author_numeric_wall_s':numeric,'author_numeric_upper_s':costs['numerical_budget_accounting_upper_s'],
      'author_all_monitored_wall_s':total,'author_elapsed_to_cost_snapshot_s':costs['elapsed_task_wall_s'],'author_elapsed_remainder_s':costs['authoring_reading_inspection_and_tool_wait_residual_wall_s'],
      'author_worker_CPU_s':costs['monitored_tree_CPU_s'],'author_peak_RSS_bytes':costs['max_sampled_simultaneous_tree_RSS_bytes'],'archive_HTTP_bytes':costs['archive_HTTP_body_bytes'],
      'view_inspection':viewed,'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu,
      'limits':['Author elapsed remainder is not independently attributed to code authoring, model latency, visual inspection, or waiting; cost snapshot precedes final completion.',
                'No external acquisition replay; copied archive identity and embedded raw data/readme relationships verified. Research provenance is not commercial redistribution authorization.',
                'Root viewed8 open source figures and3 fixed pair figures; closed directions checked numerically. Does not claim all24 author views independently inspected.']}
 (HERE/'EVIDENCE_RESULTS.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in out.items() if k not in ('view_inspection','limits')}))
if __name__=='__main__':main()
