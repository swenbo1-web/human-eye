"""Cross-check independently produced cost, mechanism and source reviews."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import statistics

BASE=Path(__file__).resolve().parent


def main():
    a=json.loads((BASE/'accounting/RESULTS.json').read_bytes())
    m=json.loads((BASE/'mechanism/RESULTS.json').read_bytes())
    b=json.loads((BASE/'binding/RESULTS.json').read_bytes())
    seal_path=Path('D:/hefe/verification/fixes/20261112_m4_surface_scan_consumer_quality_review/QUALITY_SEAL.json')
    seal=json.loads(seal_path.read_bytes())
    assert hashlib.sha256(seal_path.read_bytes()).hexdigest()=='1a205c053d7bfff76e427f83a73749bbb2a04d4ca040b92396254dd12b82942f'
    am={x['cell']:x for x in a['raw_cells']}
    mm={x['cell']:x for x in m['cells']}
    bm={x['cell']:x for x in b['cells']}
    sm={x['anonymous_id']:x for x in seal['answers']}
    assert set(am)==set(mm)==set(bm)=={'N1','N2','N3','P1','P2','P3'}
    for cell,x in am.items():
        y=mm[cell]; z=bm[cell]
        assert sm[z['anonymous_id']]['answer_sha256']==z['final_sha256']
        assert sm[z['anonymous_id']]['status']=='complete_correct'
        assert x['tool_attempts']==len(y['attempts'])==z['attempts']
        assert x['cli_tools_ns']==sum(t['tool_ns'] for t in y['attempts'])
        assert x['tool_text_utf8_bytes']==sum(t['text_bytes'] for t in y['attempts'])
        assert x['prompt_to_final_ns']==y['prompt_to_first_ns']+y['first_to_final_ns']
        assert y['first_to_final_ns']==y['later_tool_ns']+y['non_tool_tail_ns']
        assert x['usage']['cached_input_tokens']==z['provider_cached_input']
        assert z['thin_EXIT']=='unknown'
        assert x['tokens']==x['usage']['input_tokens']+x['usage']['output_tokens']
    ratios=[Fraction(am['P'+str(i)]['full_cell_wall_ns'],am['N'+str(i)]['full_cell_wall_ns']) for i in (1,2,3)]
    median=statistics.median(ratios)
    groups={g:{'tokens':sum(am[g+str(i)]['tokens'] for i in (1,2,3)),
               'full_ns':sum(am[g+str(i)]['full_cell_wall_ns'] for i in (1,2,3))} for g in ('N','P')}
    assert median==Fraction(610768379,595480694)
    assert groups['N']['tokens']==124779 and groups['P']['tokens']==257272
    value={'status':'passed','scope':'agreement of independently reconstructed raw-record analyses; not new trial samples',
           'quality':'six complete_correct upheld after private binding',
           'median_pair_ratio_exact':str(median),'median_pair_ratio':float(median),
           'groups':groups,'time_gate':median<=Fraction(7,10),
           'token_gate':groups['P']['tokens']<=groups['N']['tokens'],
           'total_time_ratio':groups['P']['full_ns']/groups['N']['full_ns'],
           'token_ratio':groups['P']['tokens']/groups['N']['tokens'],
           'inputs':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     (BASE/'accounting/RESULTS.json',BASE/'mechanism/RESULTS.json',BASE/'binding/RESULTS.json')},
           'new_Blender_consumer_API_runs':0}
    (BASE/'ROOT_CROSSCHECK.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':
    main()
