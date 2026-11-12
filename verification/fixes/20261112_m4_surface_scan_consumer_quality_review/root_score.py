"""Root offline scoring of the six public answers, before private unblinding.

The parser covers these observed table forms only. Prose/extra claims receive
separate manual review; no author scoring implementation is imported/executed.
"""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext
import hashlib
import itertools
import json
import re
import subprocess

ROOT = Path('D:/hefe')
PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_consumption_001/runtime/handoff_01/public')
OUT = Path(__file__).resolve().parent
checks = []
sources = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    data = path.read_bytes()
    sources[str(path)] = {'sha256': sha(data), 'bytes': len(data)}
    return data


def ck(name, result):
    checks.append({'name': name, 'passed': bool(result)})
    if not result:
        (OUT/'ROOT_FAILED.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
        raise AssertionError(name)


def frac(value):
    return F(int(value['numerator']), int(value['denominator']))


def fits(q_mm, exact_m2):
    tolerance = F('0.000500001')
    low = max(F(0), q_mm-tolerance)/1000
    high = (q_mm+tolerance)/1000
    return q_mm >= 0 and low*low <= exact_m2 <= high*high


def parse_table(answer):
    records = []
    for lineno, line in enumerate(answer.splitlines(), 1):
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if not cells or not re.fullmatch(r'Obj_\d{3}', cells[0]):
            continue
        if len(cells) == 3 and re.fullmatch(r'Obj_\d{3}', cells[1]):
            records.append((tuple(sorted(cells[:2])), cells[2], lineno, 'numeric_row'))
        elif len(cells) == 2:
            # Both observed two-column tables explicitly say each entry is 0 mm.
            for target in re.findall(r'Obj_\d{3}', cells[1]):
                records.append((tuple(sorted((cells[0], target))), '0', lineno, 'explicit_zero_group'))
        else:
            raise ValueError((lineno, cells))
    return records


def main():
    raw_truth = read(PUBLIC/'scoring/TRUTH.json')
    raw_snapshot = read(PUBLIC/'scoring/ACTUAL_SNAPSHOT.json')
    ck('fixed_truth_sha', sha(raw_truth)=='a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7')
    ck('fixed_snapshot_sha', sha(raw_snapshot)=='f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b')
    truth = json.loads(raw_truth)
    snapshot = json.loads(raw_snapshot)
    ck('truth_snapshot_binding', truth['snapshot_sha256']==sha(raw_snapshot))
    old = ROOT/'verification/fixes/20261112_m4_surface_scan_initial_review/quality'
    for name in ('ORACLE_RECOMPUTE.json', 'check_saved.py', 'RESULTS.json', 'INPUTS.json'):
        path = old/name
        data = read(path)
        ck('sealed_prior_'+name, data==subprocess.check_output(['git','show','dd11f1aa97ad0bf8bb314a86cd91b32ff0123874:'+path.relative_to(ROOT).as_posix()], cwd=ROOT))
    independent = json.loads((old/'ORACLE_RECOMPUTE.json').read_bytes())['base']['pairs']
    exact = {(p['object_a'],p['object_b']):frac(p['exact_squared_distance_m2']) for p in truth['pairs']}
    expected_all = set(itertools.combinations(sorted(o['name'] for o in snapshot['objects']),2))
    ck('all_276_unique', len(exact)==276 and set(exact)==expected_all)
    for p in independent:
        ck('reuse_independent_exact_'+'_'.join(p['pair']), exact[tuple(p['pair'])]==frac(p['exact_squared']))
    threshold2 = F(0.002)**2
    match = {pair for pair,d2 in exact.items() if d2<=threshold2}
    ck('exact_71_matches', len(match)==71)
    ck('zero_43', sum(exact[p]==0 for p in match)==43)
    for row in truth['pairs']:
        pair = (row['object_a'],row['object_b'])
        ck('exact_class_'+str(pair), row['matches_threshold']==(pair in match))
    objs = snapshot['objects']
    tri_counts = [len(o['triangles']) for o in objs]
    ck('24_978', len(objs)==24 and sum(tri_counts)==978)
    ck('cross_triangle_total_436640', sum(a*b for a,b in itertools.combinations(tri_counts,2))==436640)
    nearest = min((d2,p) for p,d2 in exact.items() if p not in match)
    ck('nearest_negative_extra_claim', nearest[1]==('Obj_002','Obj_008') and fits(F('2.249999'),nearest[0]))
    ck('units', snapshot['unit_system']=='METRIC' and snapshot['scale_length']==1.0)
    for obj in objs:
        ck('no_empty_'+obj['name'],len(obj['triangles'])>0)
        verts = [[F(c) for c in p] for p in obj['vertices_world']]
        for i, tri in enumerate(obj['triangles']):
            a,b,c = [verts[j] for j in tri]
            u=[b[j]-a[j] for j in range(3)]
            v=[c[j]-a[j] for j in range(3)]
            cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
            ck('nondegenerate_'+obj['name']+'_'+str(i),any(cross))
    index=json.loads(read(PUBLIC/'INDEX.json'))
    ck('six_answers',len(index['answers'])==6 and len({a['anonymous_id'] for a in index['answers']})==6)
    scores=[]
    pair_results=[]
    for entry in index['answers']:
        aid=entry['anonymous_id']
        raw=read(PUBLIC/aid/'answer.txt')
        ck(aid+'_final_sha',sha(raw)==entry['answer_original_sha256'])
        ck(aid+'_execution',entry['answer_state']=='present' and entry['cell_execution_state']=='completed' and entry['consumer_valid_completion'] is True)
        text=raw.decode('utf-8-sig')
        rows=parse_table(text)
        pairs=[row[0] for row in rows]
        ck(aid+'_no_duplicates',len(pairs)==len(set(pairs)))
        ck(aid+'_complete_set',set(pairs)==match)
        ck(aid+'_unit', '毫米' in text and 'mm' in text)
        ck(aid+'_complete_statement','检查完整' in text or '检查完整覆盖' in text)
        max_err=Decimal(0)
        for pair,token,line,kind in rows:
            q=F(token);d2=exact[pair]
            okay=fits(q,d2)
            ck(aid+'_distance_'+str(pair),okay)
            ck(aid+'_display_'+str(pair), (q==0 and d2==0) or Decimal(token).as_tuple().exponent<=-3)
            with localcontext() as ctx:
                ctx.prec=80
                exact_mm=(Decimal(d2.numerator)/Decimal(d2.denominator)).sqrt()*1000
                err=abs(Decimal(token)-exact_mm)
            max_err=max(max_err,err)
            pair_results.append({'anonymous_id':aid,'pair':pair,'mm':token,'line':line,'form':kind,'numeric_pass':okay,'absolute_error_mm_decimal_for_display':str(err)})
        scores.append({'anonymous_id':aid,'status':'complete_correct','pairs_present':len(rows),'pairs_required':71,'numeric_correct':len(rows),'FP':0,'FN':0,'duplicates':0,'presentation_incomplete':False,'complete_statement':True,'manual_extra_claim_review':'see ROOT_MANUAL_REVIEW.md','max_absolute_error_mm':str(max_err),'answer_sha256':sha(raw)})
    result={'stage':'root_quality_before_private_unblinding','scores':scores,'totals':{'complete_correct':6,'incorrect':0,'incomplete':0,'execution_failed':0,'not_run':0,'pair_distance_facts_correct':426,'pair_distance_facts_required':426},'checks_passed':len(checks),'oracle_reuse':'dd11f1aa independent exact BASE results; no new geometry oracle rerun','new_Blender_consumers_API':0,'private_cost_mapping_read':False,'manual_review_required_and_completed_separately':True}
    for name, value in [('ROOT_RESULTS.json',result),('ROOT_PAIR_CHECKS.json',pair_results),('ROOT_CHECKS.json',checks),('ROOT_INPUTS.json',sources)]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
