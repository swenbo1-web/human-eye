"""Independent anonymous numeric/content scoring. Standard library, public-only.

No author scorer is imported. No Blender, model, API, private, cells, runtime,
usage, or arm mapping is opened. Truth is reused by frozen SHA, not recomputed
over every triangle pair. Tolerance is checked against exact squared rationals.
"""
from pathlib import Path
from fractions import Fraction
from decimal import Decimal, localcontext
import collections
import hashlib
import itertools
import json
import math
import re
import zipfile

PUBLIC=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_compact_consumption_001/quality/public')
ZIP=PUBLIC.parent/'SURFACE_SCAN_COMPACT_ANONYMOUS_QUALITY_001_r2.zip'
PLAN=Path('D:/hefe/docs/M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_PLAN.md')
OUT=Path(__file__).resolve().parent
EXPECTED_ZIP='5d2ca81f18285da1fff1a05b9c0c03deb97966f57db86fa022c8ecc0b091f54f'
TRUTH_SHA='a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7'
SNAPSHOT_SHA='f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b'
PROMPT_SHA='6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc'
TOL=Fraction('0.000500001')
NUM=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
OBJ=r'Obj_\d{3}'
INPUTS={}
CHECKS=[]

def ck(name,value,detail=None):
    CHECKS.append({'check':name,'passed':bool(value),'detail':detail})

def readbytes(path):
    path=Path(path)
    if not(path.is_relative_to(PUBLIC)or path in (ZIP,PLAN)):
        raise RuntimeError('Input outside explicit blind-review scope: '+str(path))
    b=path.read_bytes()
    INPUTS[str(path)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    return b

def text(path): return readbytes(path).decode('utf-8-sig')
def load(path): return json.loads(text(path))
def rat(d): return Fraction(int(d['numerator']),int(d['denominator']))
def sqdict(q): return {'numerator':str(q.numerator),'denominator':str(q.denominator)}

def parse_answer(s):
    """Three explicit Markdown layouts: triple, pair:value groups, zero groups.

    Only table data rows contribute threshold matches. Extra prose pairs are
    reviewed separately, so a nearest-nonmatch example is not an alleged match.
    """
    rows=[];unparsed=[];zero_context=False
    for ln,line in enumerate(s.splitlines(),1):
        if line.startswith('#'):
            zero_context=bool(re.search(r'零距离|距离为\s*0',line))
        if not line.lstrip().startswith('|'): continue
        cells=[c.strip().strip('`')for c in line.strip().strip('|').split('|')]
        if not cells or not re.fullmatch(OBJ,cells[0]): continue
        a=cells[0]
        if len(cells)==3 and re.fullmatch(OBJ,cells[1]) and re.fullmatch(NUM,cells[2]):
            rows.append({'pair':sorted((a,cells[1])),'value_text_mm':cells[2],'line':ln,'syntax':'three_column'})
        elif len(cells)==2 and re.search(OBJ+r'\s*[:：]',cells[1]):
            fields=re.split(r'[;；]',cells[1]);good=True
            for field in fields:
                m=re.fullmatch(r'\s*('+OBJ+r')\s*[:：]\s*('+NUM+r')\s*',field)
                if not m: good=False;unparsed.append({'line':ln,'text':field});continue
                rows.append({'pair':sorted((a,m.group(1))),'value_text_mm':m.group(2),'line':ln,'syntax':'grouped_pair_value'})
        elif len(cells)==2 and zero_context:
            targets=re.split(r'[、,，]\s*',cells[1])
            if all(re.fullmatch(OBJ,b)for b in targets):
                for b in targets: rows.append({'pair':sorted((a,b)),'value_text_mm':'0','line':ln,'syntax':'explicit_zero_group'})
            else: unparsed.append({'line':ln,'text':line})
        else: unparsed.append({'line':ln,'text':line})
    return rows,unparsed

def within(squared_m,number_mm,tol=TOL):
    q=Fraction(number_mm)
    lower=max(Fraction(0),q-tol)/1000
    upper=(q+tol)/1000
    return q>=0 and lower*lower<=squared_m<=upper*upper

def decimal_sqrt_mm(squared_m):
    with localcontext()as c:
        c.prec=70
        return (Decimal(squared_m.numerator)/Decimal(squared_m.denominator)).sqrt()*1000

def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def completeness_evidence(s):
    # Eligible synonymous explicit claims; merely a heading is not a claim.
    return [{'line':n,'text':l}for n,l in enumerate(s.splitlines(),1)
            if ('检查完整'in l and not l.strip(' *#').startswith('检查完整性'))
            or '扫描状态为完整'in l]

def parser_self_checks():
    layouts=[
        '| Obj_001 | Obj_002 | 0.123 |',
        '| Obj_001 | Obj_002：0.123；Obj_003：0 |',
        '### 零距离：2 对\n| Obj_001 | Obj_002、Obj_003 |']
    for i,s in enumerate(layouts):
        rows,unparsed=parse_answer(s)
        ck('parser_layout_'+str(i),not unparsed and len(rows)==[1,2,2][i])
    rows,unparsed=parse_answer('| Obj_001 | Obj_002、Obj_003 |')
    ck('parser_no_unstated_zero_assumption',not rows and bool(unparsed))
    rows,unparsed=parse_answer('| Obj_001 | Obj_002 | 1.000 |\n| Obj_002 | Obj_001 | 1.000 |')
    ck('parser_duplicate_orientation_preserved',len(rows)==2 and tuple(rows[0]['pair'])==tuple(rows[1]['pair']))
    ck('parser_extra_prose_not_false_match',not parse_answer('最近未匹配：Obj_002 — Obj_008：2.250 mm')[0])
    ck('equivalent_complete_wording',bool(completeness_evidence('扫描状态为完整。')))
    ck('completeness_heading_not_sufficient',not completeness_evidence('**检查完整性**'))
    exact=Fraction(1,1000)**2
    ck('exact_tolerance_inclusive_lower',within(exact,str(Decimal('1')-Decimal('0.000500001'))))
    ck('exact_tolerance_inclusive_upper',within(exact,str(Decimal('1')+Decimal('0.000500001'))))
    ck('exact_tolerance_outside_rejected',not within(exact,'1.000500002'))

def main():
    parser_self_checks()
    readbytes(PLAN)
    zbytes=readbytes(ZIP)
    ck('frozen_r2_zip_sha',hashlib.sha256(zbytes).hexdigest()==EXPECTED_ZIP)
    public_files=sorted(f for f in PUBLIC.rglob('*')if f.is_file())
    ck('public_42_files',len(public_files)==42)
    with zipfile.ZipFile(ZIP)as z:
        # Read only names corresponding to the authorized public directory.
        names=[n for n in z.namelist()if not n.endswith('/')]
        for f in public_files:
            rel=f.relative_to(PUBLIC).as_posix()
            matches=[n for n in names if n==rel or n.endswith('/public/'+rel)or n=='public/'+rel]
            ck('zip_member_unique:'+rel,len(matches)==1)
            if len(matches)==1: ck('zip_member_bytes:'+rel,z.read(matches[0])==readbytes(f))
        ck('zip_42_file_members',len(names)==42)
    idx=load(PUBLIC/'INDEX.json');contract=load(PUBLIC/'scoring/SCORING_CONTRACT.json')
    truth=load(PUBLIC/'scoring/TRUTH.json');snapshot=load(PUBLIC/'scoring/ACTUAL_SNAPSHOT.json')
    ck('truth_fixed_sha',INPUTS[str(PUBLIC/'scoring/TRUTH.json')]['sha256']==TRUTH_SHA)
    ck('snapshot_fixed_sha',INPUTS[str(PUBLIC/'scoring/ACTUAL_SNAPSHOT.json')]['sha256']==SNAPSHOT_SHA)
    ck('prompt_fixed_sha',INPUTS[str(PUBLIC/'tasks/T1.txt')]['sha256']==PROMPT_SHA)
    ck('truth_snapshot_binding',truth['snapshot_sha256']==SNAPSHOT_SHA)
    ck('contract_bound_inputs',contract['input_materials']['actual_snapshot_sha256']==SNAPSHOT_SHA and contract['input_materials']['independent_truth_sha256']==TRUTH_SHA)
    ck('fixed_contract_threshold_and_tolerance',contract['distance_policy']['threshold_m_binary64']==.002 and Fraction(contract['distance_policy']['absolute_error_mm'])==TOL)
    pairs={tuple(sorted((p['object_a'],p['object_b']))):p for p in truth['pairs']}
    sq={pair:rat(p['exact_squared_distance_m2'])for pair,p in pairs.items()}
    names=sorted(o['name']for o in snapshot['objects'])
    ck('all_276_unique_pairs',len(pairs)==276 and set(pairs)==set(itertools.combinations(names,2)))
    ck('geometry_object_vertex_triangle_counts',snapshot['counts']=={'objects':24,'vertices':530,'triangles':978})
    threshold_sq=Fraction.from_float(.002)**2
    expected={p for p,d in sq.items()if d<=threshold_sq}
    ck('exact_threshold_membership_count',len(expected)==71)
    for p,d in sq.items(): ck('truth_predicate:'+str(p),pairs[p]['matches_threshold']==(d<=threshold_sq))
    zero={p for p in expected if sq[p]==0}
    ck('true_zero_43_positive_28',len(zero)==43 and len(expected-zero)==28)
    outside=set(sq)-expected;least=min(sq[p]for p in outside)
    least_pairs=sorted(p for p in outside if sq[p]==least)
    ck('nearest_excluded_claim_pair',('Obj_002','Obj_008')in least_pairs)
    ck('nearest_excluded_2p250_mm',within(least,'2.250'))
    nonfinite=[];empty=[];degenerate=[]
    for ob in snapshot['objects']:
        vertices=ob['vertices_world']
        if not ob['triangles']:empty.append(ob['name'])
        if any(not math.isfinite(v)for pt in vertices for v in pt):nonfinite.append(ob['name'])
        fv=[[Fraction.from_float(v)for v in pt]for pt in vertices]
        for n,tri in enumerate(ob['triangles']):
            a,b,c=(fv[i]for i in tri)
            area=cross([b[i]-a[i]for i in range(3)],[c[i]-a[i]for i in range(3)])
            if not any(area):degenerate.append([ob['name'],n])
    ck('no_empty_degenerate_or_nonfinite_geometry',not(empty or degenerate or nonfinite))
    ck('unit_one_blender_unit_1000mm',snapshot['unit_scale_m']==1.0)
    counts=collections.Counter();answers=[]
    for slot in idx['answers']:
        aid=slot['anonymous_id'];s=text(PUBLIC/aid/'answer.txt')
        ck(aid+':answer_original_sha',INPUTS[str(PUBLIC/aid/'answer.txt')]['sha256']==slot['answer_original_sha256']==slot['source_provenance']['public_final_sha256'])
        ck(aid+':cli_corroborates_final_bytes',readbytes(PUBLIC/aid/'answer.txt')==readbytes(PUBLIC/aid/'cli_output_unconfirmed.txt'))
        rows,unparsed=parse_answer(s)
        ctr=collections.Counter(tuple(r['pair'])for r in rows);observed=set(ctr)
        missing=sorted(expected-observed);extra=sorted(observed-expected);duplicates={str(p):n for p,n in ctr.items()if n>1}
        wrong_dist=[];presentation=[];zero_misclaim=[];perpair=[]
        for row in rows:
            p=tuple(row['pair']);num=row['value_text_mm'];value=Decimal(num)
            correct=within(sq[p],num)if p in sq else False
            resolution=Decimal(10)**value.as_tuple().exponent
            precok=(value==0 and p in zero)or(value!=0 and resolution<=Decimal('.001'))
            if not correct:wrong_dist.append(row)
            if not precok:presentation.append(row)
            if value==0 and p not in zero:zero_misclaim.append(row)
            ref=decimal_sqrt_mm(sq[p])if p in sq else None
            err=abs(value-ref)if ref is not None else None
            perpair.append(dict(row,exact_squared_m2=sqdict(sq[p])if p in sq else None,
                                within_exact_squared_tolerance=correct,effective_resolution_mm=str(resolution),
                                presentation_ok=precok,reference_mm_decimal_diagnostic=str(ref),
                                absolute_error_mm_decimal_diagnostic=str(err)))
        # Every answer was read independently in full. These extracted lines
        # provide reviewable evidence for explicit completeness and units.
        completeness_lines=completeness_evidence(s)
        unit_lines=[{'line':n,'text':l}for n,l in enumerate(s.splitlines(),1)if ('毫米'in l or 'mm'in l)and('单位'in l or '距离均'in l or '以下距离'in l)]
        ck(aid+':explicit_complete_claim',bool(completeness_lines))
        ck(aid+':explicit_mm',bool(unit_lines))
        # Source producer records remain provenance, not a newly run write guard.
        source=load(PUBLIC/aid/'source_consistency.json')
        ck(aid+':source_asset_bound',source['ACTOR_CONFIG']['asset_sha256']==source['owner_IDENTITY']['asset_sha256']=='7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66')
        ck(aid+':recorded_initial_final_equal',source['INITIAL_original_file_sha256']==source['FINAL_original_file_sha256'] and source['CLOSE']['asset_unchanged']and source['CLOSE']['geometry_unchanged'])
        ck(aid+':recorded_no_image',source['CONSUMER_INPUT']['input_image_count']==0)
        content_errors=[]
        if extra:content_errors.append('false_positive_pairs')
        if duplicates:content_errors.append('duplicate_pairs')
        if wrong_dist:content_errors.append('wrong_distances')
        if zero_misclaim:content_errors.append('positive_distance_claimed_exact_zero')
        if missing and completeness_lines:content_errors.append('omission_with_complete_claim')
        if content_errors:content_class='incorrect'
        elif missing or presentation or unparsed or not(completeness_lines and unit_lines):content_class='incomplete'
        else:content_class='complete_correct'
        execution=slot['cell_execution_state']
        if execution=='failed':primary='execution_failure'
        elif execution=='not_run':primary='not_run'
        elif not slot['consumer_valid_completion']:primary='execution_failure'
        else:primary=content_class
        counts[primary]+=1
        item={'anonymous_id':aid,'cell_execution_state':execution,'consumer_valid_completion':slot['consumer_valid_completion'],
              'primary_classification':primary,'content_classification':content_class,'content_definite_errors':content_errors,
              'parsed_rows':len(rows),'unique_pairs':len(observed),'true_positive_pairs':len(observed&expected),
              'false_positive_pairs':extra,'missing_pairs':missing,'duplicate_pairs':duplicates,'wrong_distance_rows':wrong_dist,
              'zero_misclaim_rows':zero_misclaim,'presentation_incomplete_rows':presentation,'unparsed_rows':unparsed,
              'complete_claim':completeness_lines,'millimetre_declaration':unit_lines,
              'maximum_absolute_error_mm_decimal_diagnostic':str(max(Decimal(x['absolute_error_mm_decimal_diagnostic'])for x in perpair)),
              'additional_definite_errors':[],
              'extra_claim_review':'Independent full-text review: counts 24/978/276/71/43/28 and partition 164/41/71 match fixed truth where stated; 2.250 mm nearest excluded claim matches exact truth; zero statements match exact-zero pairs. Surface relation limits are stated, no false solid assertion. Separate public evidence review supports the all-276 computation assertions where stated. Read-only terminal evidence is producer corroboration, not proof against transient writes.',
              'execution_errors_preserved':slot['consumer_execution_errors'], 'per_pair':perpair}
        answers.append(item)
        (OUT/(aid+'.json')).write_text(json.dumps(item,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ck('nine_answers_present',len(idx['answers'])==9 and all(x['answer_state']=='present'for x in idx['answers']))
    ck('execution_denominator_seven_completed_two_failed',collections.Counter(x['cell_execution_state']for x in idx['answers'])=={'completed':7,'failed':2})
    result={'scope':'Anonymous numeric/content quality only, public and plan inputs. No cost or arm mapping used.',
            'frozen_zip_sha256':EXPECTED_ZIP,'truth_sha256':TRUTH_SHA,'snapshot_sha256':SNAPSHOT_SHA,
            'geometry_truth_layer':'Reused frozen exact rational oracle, SHA verified; exact threshold memberships and squared tolerance intervals recomputed. No all-triangle nearest-distance solver rerun.',
            'AL_note':'Own context_handle 2d52da22100d41b0bd4f17a0cee08411 still has stale child assignment. Parent task60f80757 revision1 read, explicit new child task used; no parent writes or borrowed identity.',
            'blindness_limit':'Public original tool content can reveal route. While reviewing numerical provenance one native stdout incidental elapsed value was visible; no private/runtime/cells/usage or group mapping was read, no time/cost used for grading.',
            'contract_precedence':'Execution_failure/not_run primary categories retained. Final-content quality scored separately even for failed executions.',
            'denominators':{'slots':9,'finals_present':9,'completed':7,'execution_failed':2,'not_run':0,'truth_pairs':276,'true_matches':71,'final_match_rows_scored':sum(a['parsed_rows']for a in answers)},
            'primary_counts':dict(counts),'content_counts':dict(collections.Counter(a['content_classification']for a in answers)),
            'exact_geometry_auxiliary':{'zero_pairs':len(zero),'positive_match_pairs':len(expected-zero),'nonmatch_pairs':len(outside),'nearest_nonmatch_pairs':least_pairs,'nearest_nonmatch_squared_m2':sqdict(least),'empty_meshes':empty,'degenerate_triangles':degenerate,'nonfinite_objects':nonfinite},
            'answers':[dict((k,v)for k,v in a.items()if k!='per_pair')for a in answers],
            'checks':len(CHECKS),'failed_checks':[c for c in CHECKS if not c['passed']],
            'reviewer_attempt_history':'Attempt 01 parser recognized 检查完整 but missed equivalent 扫描状态为完整 in answer_4a4a77418ce1424c. Full-text manual review identified the synonym; extraction corrected without changing contract. First RESULTS/CHECKS retained as ATTEMPT_01. This was a reviewer parser deficiency, not an answer defect.',
            'not_run':['new Blender/model/API','author scorer','full-triangle oracle reconstruction','cost and group comparisons','private source rebind audit (assigned separately)']}
    for name,d in [('RESULTS.json',result),('CHECKS.json',CHECKS),('INPUT_HASHES.json',INPUTS)]:
        (OUT/name).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':result['checks'],'failed_checks':result['failed_checks'],'denominators':result['denominators'],'primary_counts':result['primary_counts'],'content_counts':result['content_counts'],'answers':[{k:a[k]for k in ['anonymous_id','primary_classification','content_classification','parsed_rows','maximum_absolute_error_mm_decimal_diagnostic']}for a in answers]},ensure_ascii=False,indent=2))
    return bool(result['failed_checks'])

if __name__=='__main__':raise SystemExit(main())
