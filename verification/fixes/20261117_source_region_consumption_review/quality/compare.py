"""Compare the already-written independent decisions with author scores."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
NS = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_consumption_001')
BLIND_SHA = '49e04a7cf4c292c565ea35bcb49bb13b8ef5abe18058cdd0612ef9607ad400e0'


def main():
    blind_bytes = (OUT / 'BLIND_SCORES.json').read_bytes()
    assert hashlib.sha256(blind_bytes).hexdigest() == BLIND_SHA
    result = json.loads(blind_bytes)
    author_bytes = (NS / 'scoring/AUTHOR_SCORES.json').read_bytes()
    author = json.loads(author_bytes)
    independent = {c['case_id']: c for c in result['cases']}
    comparisons = []
    for case in author['cases']:
        for gate in case['gates']:
            own = independent[case['case_id']]['gates'][gate['gate_id']]
            comparisons.append(dict(case_id=case['case_id'], gate_id=gate['gate_id'],
                independent=own['verdict'], author=gate['verdict'],
                agrees=own['verdict'] == gate['verdict']))
    assert len(comparisons) == 27
    result['phase'] = 'independent_final_with_author_comparison'
    result['blind_scores_sha256_before_author_read'] = BLIND_SHA
    result['author_comparison'] = dict(
        author_scores_sha256=hashlib.sha256(author_bytes).hexdigest(),
        decisions_compared=len(comparisons),
        agrees=sum(row['agrees'] for row in comparisons),
        disagreements=[row for row in comparisons if not row['agrees']],
        verdicts_changed_after_comparison=0,
        comparisons=comparisons)
    result['author_scores_read'] = True
    result['assignment_disclosure'] = dict(
        own_context_handle='2177bc02fec34553b8a2f368baf24a95',
        current_parent_task='c3e7c21a-e71d-42ba-b5a8-02c544c24449',
        current_parent_revision=1,current_parent_write_version=749,
        continuing_child_assignment_task='d718d092-1718-414a-85bf-d636c6bc9f09',
        continuing_child_assignment_current=False,
        scope='current explicit parent delegation, public final answers and frozen source only')
    (OUT / 'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(comparisons=len(comparisons),agreement=result['author_comparison']['agrees'],
        accepted_cases=result['accepted_cases'],counts=result['counts']),ensure_ascii=False))


if __name__ == '__main__':
    main()
