"""Compatibility for a zero-count original snapshot omitting its optional pixel anchor."""
import argparse
import importlib.util
import json
from pathlib import Path

BASE_SHA = 'e511e03f9dc784e438a1acab2bda4cf1385f9b57208ee4f68ebeef19444339ea'
BASE = Path(__file__).with_name('grade.py')
spec = importlib.util.spec_from_file_location('frozen_occlusion_grade',BASE)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
baseline.require(baseline.pin(BASE)['sha256']==BASE_SHA,'original_frozen_grader_changed')
original_public = baseline.public_payload


class ZeroPixelSample(dict):
    def __missing__(self,key):
        if key=='sampled_pixel' and self.get('selected_surface_pixels')==0 and self.get('primary_surface_pixels')==0:
            return None
        raise KeyError(key)


def missing_anchor_compat(reply):
    body,images = original_public(reply)
    focus = body['facts']['focus']
    sample = focus['sample']
    if isinstance(sample,dict) and 'sampled_pixel' not in sample:
        focus['sample']=ZeroPixelSample(sample)
    # No field is added and dict equality against the original producer is retained.
    return body,images


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda p:Path(p).resolve(strict=True))
    cli.add_argument('phase',choices=('A','AB'))
    cli.add_argument('output',type=Path)
    args = cli.parse_args()
    original_failed = args.root/'preflight/A_BASELINE_AUDIT.json'
    baseline.require(baseline.read(original_failed)=={
        'passed':False,'phase':'A','error':"KeyError: 'sampled_pixel'"},
        'initial_frozen_audit_failure_changed')
    baseline.public_payload=missing_anchor_compat
    try:
        result=baseline.run(args.root,args.phase)
    except (KeyError,IndexError,TypeError,ValueError,OSError,StopIteration) as error:
        result={'passed':False,'phase':args.phase,'error':f'{type(error).__name__}: {error}'}
    result.update(audit_compatibility='zero-count absent optional anchor evaluates to null',
                  original_failed=baseline.pin(original_failed),compat_script=baseline.pin(__file__))
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print(json.dumps(baseline.pin(args.output)))
    if not result['passed']:
        print(result['error'])
        raise SystemExit(1)


if __name__=='__main__':
    main()
