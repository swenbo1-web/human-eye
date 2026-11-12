"""Saved-only exact world-rank and 4 mm checks over the frozen G508 calls."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def world_squared(key):
    numerator,denominator,exponent = key
    scale = F(1<<exponent) if exponent>=0 else F(1,1<<-exponent)
    return F(numerator,denominator)*scale


def main():
    data = json.loads((HERE/'sixty_01/RESULTS.json').read_bytes())
    designed = json.loads((HERE/'DESIGNED_CASES.json').read_bytes())
    proofs = []
    threshold = F(designed['g508']['minimum_gap_m'])**2
    expected = {'Peer_000':False,'Competing_001':True,'Near_003':True}
    for arm in ('reference','candidate'):
        for iteration in range(1,6):
            selected = [row for row in data['samples'] if row['arm']==arm and row['iteration']==iteration and row['case'].startswith('G508/')]
            ranks = {row['case'].split('/')[1]:world_squared(row['result']['surface']['_exact_distance_sq']) for row in selected}
            minimum = min(ranks.values())
            nearest = sorted(name for name,value in ranks.items() if value==minimum)
            gaps = {name:value>=threshold for name,value in ranks.items()}
            proofs.append({'arm':arm,'iteration':iteration,'passed':len(ranks)==3 and nearest==['Peer_000'] and gaps==expected,
                'nearest':nearest,'minimum_4mm':gaps,
                'exact_squared_distances':{name:[value.numerator,value.denominator] for name,value in ranks.items()}})
    result = {'passed':len(proofs)==10 and all(row['passed'] for row in proofs),'proofs':proofs,
        'scope':'exact rank of only the three fixed G508 candidates; repeated groups are not new tasks',
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_results_sha256':hashlib.sha256((HERE/'sixty_01/RESULTS.json').read_bytes()).hexdigest(),
        'product_calls':0,'performance_calls':0,'model_consumers':0}
    with (HERE/'saved_verification_01/RANKING_AND_4MM.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
