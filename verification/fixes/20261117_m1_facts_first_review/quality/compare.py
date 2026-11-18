"""Compare the sealed independent original-gate decisions with both reviewers."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
NS = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m1_source_region_facts_first_001')
BLIND_SHA = 'b28a92be1d9e5ab036794ba1d80a7d8e6e3af5f9748d9945cd3a7e865077510f'


def main():
    source_bytes = (OUT/'BLIND_SCORES.json').read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == BLIND_SHA
    result = json.loads(source_bytes)
    own = {case['case_id']:case for case in result['cases']}
    comparisons = []
    for filename in ('AUTHOR_SCORES.json','INDEPENDENT_SCORES.json'):
        path = NS/'scoring'/filename
        content = path.read_bytes()
        scores = json.loads(content)
        rows = []
        for case in scores['cases']:
            for gate in case['gates']:
                gid = gate['gate_id']
                ours = own[case['case_id']]['strict_gates'][gid]['verdict']
                rows.append(dict(case_id=case['case_id'],gate_id=gid,
                    own=ours,other=gate['verdict'],agrees=ours==gate['verdict']))
        assert len(rows) == 27
        comparisons.append(dict(path=str(path),sha256=hashlib.sha256(content).hexdigest(),
            gates_compared=27,gates_agree=sum(row['agrees'] for row in rows),
            disagreements=[row for row in rows if not row['agrees']],rows=rows))
    pngs = []
    for case in ('S1','S2','S3'):
        current = NS/'inputs'/case/'ORIGINAL_IMAGE.png'
        historical = NS/'historical'/case/'ORIGINAL_IMAGE.png'
        current_bytes = current.read_bytes()
        assert current_bytes == historical.read_bytes()
        pngs.append(dict(case_id=case,path=str(current),bytes=len(current_bytes),
            sha256=hashlib.sha256(current_bytes).hexdigest(),same_historical_bytes=True,
            existing_file_visually_viewed=True))
    result.update(phase='independent_final_after_comparison',author_scores_read=True,
        blind_result_sha256=BLIND_SHA,score_comparisons=comparisons,
        verdicts_changed_after_comparison=0,existing_original_png_checks=pngs,
        image_qualitative_claims='Existing original PNGs confirm grey triangulated torso/arm in S1, uniform grey S2 and dark S3; no colour selection overlay or nearest-point overlay is visible.',
        assignment_disclosure=dict(own_context_verified=True,
            current_parent='985fb28e-857e-4221-9af6-ae5645c1d873',parent_revision=1,parent_write_version=751,
            historical_child_assignment='d718d092-1718-414a-85bf-d636c6bc9f09',historical_child_current=False))
    path = OUT/'RESULT.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(comparisons=[dict(gates=c['gates_compared'],agree=c['gates_agree']) for c in comparisons],
        strict_accepted=result['strict_preregistered_result']['accepted'],
        actual_prompt_satisfied=result['actual_prompt_alignment']['satisfied'],
        cm_error_m=result['cases'][0]['cm_rounding_absolute_error_m']),ensure_ascii=False))


if __name__ == '__main__':
    main()
