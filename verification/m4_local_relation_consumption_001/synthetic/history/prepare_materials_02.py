"""Pure preparation only: preserve old scoring semantics and packager helpers."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
ROOT=BATCH.parents[1]
OLD=ROOT/'verification/m4_observation_baseline_001'
CYCLE='M4-LOCAL-RELATION-CONSUMPTION-001'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def encoded(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')
def put(path,raw):
    assert path.resolve().is_relative_to(BATCH.resolve())
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)


def leaves(value,path='$'):
    if isinstance(value,dict):
        for key,item in value.items():yield from leaves(item,path+'/'+key.replace('~','~0').replace('/','~1'))
    elif isinstance(value,list):
        for index,item in enumerate(value):yield from leaves(item,path+'/'+str(index))
    else:yield path,value


def main():
    original=(OLD/'scoring/SCORING_CONTRACT.json').read_bytes()
    assert sha(original)=='1c4a88d7018426c1a68ae7f770acb8f1eb90faee50ee46ca616dd0ea703cdbcc'
    previous=json.loads(original)
    sequence_raw=(BATCH/'SEQUENCE.json').read_bytes()
    mapping_raw=(BATCH/'private/ANON_MAP.json').read_bytes()
    assert sha(sequence_raw)=='9ded7fc2ca8707bc2355092e6ce333f458da5d6c9ebcbc1808836b7e2a34445f'
    assert sha(mapping_raw)=='d0535e412c89339c095edcd0e82a0eb6430b3aa979be19f982fd2972ba1193d8'
    sequence=json.loads(sequence_raw)['sequence'];mapping=json.loads(mapping_raw)['rows']
    assert len(sequence)==len(mapping)==9
    assert all(all(slot[key]==row[key] for key in ('cell','round','task','group')) for slot,row in zip(sequence,mapping,strict=True))
    assert [slot['group'] for slot in sequence]==['N','P0','P1','P0','P1','N','P1','N','P0']
    current=copy.deepcopy(previous)
    current.update(cycle_id=CYCLE,
      scope='One unchanged historical scene; N/P0/P1 each three planned fresh consumers. This file is private scoring material, never consumer input.',
      fixed_sample_policy='One scene, N/P0/P1 each3, nine fixed slots, no replacement for failure/unknown/no-attempt/slow/incomplete samples. Frozen stop tails are not_run, distinct from entered failures. No extra task introduced here. The earlier six-cell baseline remains historical and is not pooled with this batch.')
    current['sample_metadata']={
      'groups':['N','P0','P1'],'per_group':3,'rounds':3,'logical_denominator':9,
      'sequence':'SEQUENCE.json','sequence_sha256':sha(sequence_raw),
      'anonymous_mapping':'private/ANON_MAP.json','anonymous_mapping_sha256':sha(mapping_raw),
      'anonymous_mapping_scope':'new pre-consumer fixed nine-row mapping; private, not a consumer input',
      'historical_baseline_pooling':'The earlier N/P six-cell batch is not pooled into this batch.'}
    allowed={'cycle_id','scope','fixed_sample_policy'}
    assert set(current)==set(previous)|{'sample_metadata'}
    semantic_fields=[key for key in previous if key not in allowed]
    comparisons=[{'pointer':'$/'+key,'equal':current[key]==previous[key],
        'original_value_sha256':sha(encoded(previous[key])),
        'new_value_sha256':sha(encoded(current[key]))} for key in semantic_fields]
    assert all(row['equal'] for row in comparisons)
    semantic_leaves=[]
    for key in semantic_fields:
        old_leaves=list(leaves(previous[key],'$/'+key));new_leaves=list(leaves(current[key],'$/'+key))
        assert old_leaves==new_leaves
        semantic_leaves.extend({'pointer':path,'equal':True,'value_sha256':sha(encoded(value))} for path,value in old_leaves)
    copies=[]
    for name in ('TRUTH.json','INPUT_BINDING.json','SOURCE_BINDING.json','REFERENCE_REPLAY.json'):
        raw=(OLD/'scoring'/name).read_bytes();put(BATCH/'scoring'/name,raw)
        copies.append({'source':str((OLD/'scoring'/name).relative_to(ROOT)).replace('\\','/'),
          'destination':'scoring/'+name,'bytes':len(raw),'sha256':sha(raw),'copied_exact_bytes':True})
    put(BATCH/'scoring/SCORING_CONTRACT_BASELINE.json',original)
    new_raw=encoded(current);put(BATCH/'scoring/SCORING_CONTRACT.json',new_raw)
    changes=[{'pointer':'$/'+key,'old':previous[key],'new':current[key]} for key in ('cycle_id','scope','fixed_sample_policy')]
    changes.append({'pointer':'$/sample_metadata','old_field_present':False,'new':current['sample_metadata']})
    binding=json.loads((OLD/'scoring/SOURCE_BINDING.json').read_bytes())
    references=[]
    for row in binding['files']:
        path=OLD/row['path'];raw=path.read_bytes()
        assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
        references.append({'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':sha(raw),'bytes':len(raw),'copied':False})
    put(BATCH/'scoring/SOURCE_REUSE.json',encoded({'copies':copies,'references_only':references,
      'legacy_relative_path_resolution_base':str(OLD.relative_to(ROOT)).replace('\\','/'),
      'legacy_record_identity_preserved':'Copied truth/binding/replay records retain their original cycle and source-relative paths. Resolve their original source paths against the historical baseline directory; no fresh replay is claimed.',
      'model_consumers':0,'product_calls':0,'Blender_sessions':0,'new_images':0,'new_assets':0}))
    put(BATCH/'scoring/SCORING_CONTRACT_EQUIVALENCE.json',encoded({
      'passed':True,'baseline_contract_sha256':sha(original),'new_contract_sha256':sha(new_raw),
      'allowed_changed_existing_fields':['$/cycle_id','$/scope','$/fixed_sample_policy'],
      'new_metadata_field':'$/sample_metadata','exact_structural_diff':changes,
      'unchanged_top_level_fields':comparisons,'unchanged_semantic_leaves':semantic_leaves,
      'scoring_semantics_changed':False,'copied_references_recomputed':False,
      'model_consumers':0,'product_calls':0,'Blender_sessions':0}))
    put(BATCH/'scoring/SCORING_CONTRACT_EXACT.diff',''.join(difflib.unified_diff(
      original.decode().splitlines(True),new_raw.decode().splitlines(True),
      fromfile='historical_SCORING_CONTRACT.json',tofile='new_SCORING_CONTRACT.json')).encode('utf8'))

    old_pack=(OLD/'quality_handoff/pack_quality.py').read_bytes()
    assert sha(old_pack)=='afa802bdb085ad9e174f04c4ba91ff05bdacdbc7b0bb892162a7b7e14d580cbc'
    text=old_pack.decode('utf8')
    replacements=[
      ("CYCLE = 'M4-OBSERVATION-BASELINE-001'","CYCLE = '"+CYCLE+"'"),
      ('assert len(sequence)==len(rows)==6 and','assert len(sequence)==len(rows)==9 and'),
      ('assert len(records)<=6 and','assert len(records)<=9 and'),
      ('assert len(records)==6 or','assert len(records)==9 or'),
      ("'fixed_slots':6","'fixed_slots':9"),("'packaged_slots':6","'packaged_slots':9")]
    for before,after in replacements:
        assert text.count(before)==1,(before,text.count(before))
        text=text.replace(before,after)
    old_binding="        assert all(consumer.get(key)==slot[key] for key in KEYS), 'consumer slot binding mismatch'"
    new_binding=("        assert all(consumer.get(key)==slot[key] for key in ('cell','task','round')), 'consumer slot binding mismatch'\n"
      "        expected_group={'N':'N','P0':'P','P1':'P'}[slot['group']]\n"
      "        assert consumer.get('group')==expected_group and consumer.get('external_group')==slot['group'], 'consumer external/internal group binding mismatch'")
    assert text.count(old_binding)==1
    text=text.replace(old_binding,new_binding)
    anchor="    assert plan['cycle_id']==CYCLE and plan['batch']==CYCLE, 'wrong observation cycle'\n"
    assert text.count(anchor)==1
    metadata_check=("    assert plan['logical_denominator']==9 and plan['per_arm']==3 and set(plan['arms'])=={'N','P0','P1'}, 'wrong fixed nine-slot sample metadata'\n")
    text=text.replace(anchor,anchor+metadata_check)
    new_pack=text.encode('utf8')
    old_functions={node.name:ast.dump(node,include_attributes=False) for node in ast.parse(old_pack).body if isinstance(node,ast.FunctionDef)}
    new_functions={node.name:ast.dump(node,include_attributes=False) for node in ast.parse(new_pack).body if isinstance(node,ast.FunctionDef)}
    assert set(old_functions)==set(new_functions)
    unchanged={name:old_functions[name]==new_functions[name] for name in old_functions if name not in ('main','handoff_one')}
    assert all(unchanged.values())
    put(BATCH/'quality_handoff/pack_quality.py',new_pack)
    put(BATCH/'quality_handoff/SOURCE_REUSE.json',encoded({
      'source_path':str((OLD/'quality_handoff/pack_quality.py').relative_to(ROOT)).replace('\\','/'),
      'source_sha256':sha(old_pack),'new_sha256':sha(new_pack),
      'exact_text_replacements':[{'before':a,'after':b} for a,b in replacements],
      'consumer_group_binding_delta':{'before':old_binding,'after':new_binding,
          'reason':'Original transport remains N/P internally; new driver records external_group=N/P0/P1. Both identities must match the frozen external slot.'},
      'new_main_metadata_assertion':metadata_check.strip(),
      'all_payload_and_assembly_helpers_AST_unchanged':unchanged,
      'changed_functions':['main','handoff_one'],'changed_constant':'CYCLE','semantic_projection_unchanged':True,
      'model_consumers':0,'product_calls':0,'Blender_sessions':0}))
    put(BATCH/'quality_handoff/SOURCE.diff',''.join(difflib.unified_diff(
      old_pack.decode().splitlines(True),text.splitlines(True),
      fromfile='historical_pack_quality.py',tofile='new_pack_quality.py')).encode('utf8'))
    print(json.dumps({'prepared':True,'semantic_fields_unchanged':len(comparisons),
      'semantic_leaves_unchanged':len(semantic_leaves),'new_scoring_sha256':sha(new_raw),
      'new_packager_sha256':sha(new_pack),'model_consumers':0,'product_calls':0,'Blender_sessions':0}))


if __name__=='__main__':main()
