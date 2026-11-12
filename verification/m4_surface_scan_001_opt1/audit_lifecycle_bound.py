"""Bound the full median including final result writing from serial raw intervals."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUN = HERE/'engineering/run_01'


def main():
    binding = json.loads((RUN/'INPUT_BINDINGS.json').read_bytes())
    records = []
    inputs = {}
    for index,order in enumerate(binding['pair_orders'],1):
        for version in order:
            path = RUN/('pair_'+str(index).zfill(2))/version/'RESULTS.json'
            raw = path.read_bytes()
            row = json.loads(raw)
            assert row['passed']
            records.append((index,version,row))
            inputs[str(path.relative_to(HERE))] = hashlib.sha256(raw).hexdigest()
    # The hash-bound controller waits synchronously for run_sequence(), whose
    # final save closes RESULTS before returning. The next sequence starts later.
    ends = {}
    for current,following in zip(records,records[1:]):
        index,version,row = current
        next_started = following[2]['started_ns']
        assert next_started >= row['ended_ns']
        ends[index,version] = next_started
    by_pair = {(index,version):row for index,version,row in records}
    upper_bounds = []
    for index in range(1,6):
        before = by_pair[index,'A']['session_wall_ns']
        assert before > 0
        if (index,'B') not in ends:
            continue
        after = by_pair[index,'B']
        upper = ends[index,'B']-after['started_ns']
        upper_bounds.append(dict(pair=index,old_lower_ns=before,new_upper_ns=upper,
            trailing_gap_upper_ns=ends[index,'B']-after['ended_ns'],
            ratio=Fraction(upper,before)))
    assert len(upper_bounds) == 4
    # The fifth ratio has an unbounded upper endpoint. The third smallest of
    # these four finite endpoints still bounds the median of all five ratios.
    median_upper = sorted(row['ratio'] for row in upper_bounds)[2]
    assert median_upper <= Fraction(105,100)
    result = dict(passed=True,planned_pairs=5,finite_upper_bounds=4,
        final_pair_upper_bound='unbounded; retained in the five-ratio median proof',
        median_ratio_upper_bound=dict(numerator=median_upper.numerator,
            denominator=median_upper.denominator,value=float(median_upper)),
        full_median_gate_proven=True,full_median_net_improvement_proven=median_upper < 1,
        exact_full_median_measured=False,input_results=inputs,rows=[])
    for row in upper_bounds:
        ratio = row.pop('ratio')
        result['rows'].append(dict(row,ratio_upper_bound=dict(numerator=ratio.numerator,
            denominator=ratio.denominator,value=float(ratio))))
    for name in ('sequence.py','run_pairs.py'):
        path = HERE/'engineering'/name
        expected = binding['files'][str(path.resolve())]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    with (HERE/'ROOT_LIFECYCLE_BOUND.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('input_results','rows')}))


if __name__ == '__main__':
    main()
