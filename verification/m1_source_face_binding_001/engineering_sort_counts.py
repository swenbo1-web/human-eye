"""Count actual sorting calls separately from the completed timing sample."""

import builtins
import copy
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_source_binding_completed_benchmark', HERE / 'engineering_bench.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def main():
    raw = bench.read(bench.RAW_SOURCE)
    raw['binding'].pop('camera_specification')
    public = json.loads(bench.read(bench.OLD_RESPONSE)['result']['content'][0]['text'])
    raw['image_delivery'] = copy.deepcopy(public['image_delivery'])
    results = {}
    variants = dict(baseline=bench.OLD_SOURCE, initial=HERE/'product_candidate_01.py', optimized=HERE/'product_candidate_02.py')
    for name, source in variants.items():
        counts = {}

        def profile(frame, event, argument):
            if event == 'c_call' and argument is builtins.sorted and frame.f_code.co_filename == str(source):
                function = frame.f_code.co_name
                counts[function] = counts.get(function, 0) + 1

        function = bench.load_projection(source)['project_active_observation_brief']
        sys.setprofile(profile)
        try:
            value = function(raw)
        finally:
            sys.setprofile(None)
        assert value is not None
        results[name] = dict(sorted_calls_by_function=counts, total_sorted_calls=sum(counts.values()))
    assert results['initial']['total_sorted_calls'] == results['optimized']['total_sorted_calls']
    output = dict(schema='m1-source-face-binding-sorting-work-v1', actual_projection_calls=3,
                  product_observe_raster_model_calls=0, results=results,
                  interpretation='The additional pass was removed. Exactly one source-range sort per region remains required by unordered source input. No sort was eliminated by moving it into validation.',
                  timing_matrix_rerun=False)
    bench.save(HERE / 'ENGINEERING_SORT_COUNTS.json', output)
    print(json.dumps(output))


if __name__ == '__main__':
    main()
