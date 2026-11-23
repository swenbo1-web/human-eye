"""Build one isolated visual-wire candidate from the fixed Git parent."""
import json
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m4_source_region_selective_visual_capture_001'
ROOT = Path('D:/he_m4_source_region_visual_wire_reuse_001').resolve()
PRODUCT_PARENT = '85a5501ba8e03d29340ef9a94e38ae1a2849330f'
BUILD_VERSION = '9.7.2+m4.source.region.visual.wire.reuse.001'
PARENT_BINDING = Path('D:/he_m4_source_region_selective_visual_capture_001/candidate_install/PRODUCT_RUN_BINDING.json')
PARENT_BINDING_SHA256 = '8b6df2f13abe3eb0e36e40ca0783d81d2773e87e0ffb5e263c1fb9bb78259f64'
PRODUCT_FILES = {'blender_host.py', 'blender_mcp_host.py', 'live_service.py'}


def main():
    old = run_path(str(PRIOR/'build.py'))
    builder = old['build']
    old = builder.__globals__
    demand, digest, git = old['demand'], old['digest'], old['git']
    demand(sys.flags.isolated and sys.dont_write_bytecode and len(sys.argv)==2,
           'fixed_build_interpreter')
    candidate = sys.argv[1]
    demand(len(candidate)==40 and all(c in '0123456789abcdef' for c in candidate),
           'expected_exact_candidate_commit')
    prior_builder = '72eb34df7d662a3081febf02bf58f39e736cd49a:verification/' + PRIOR.name + '/build.py'
    demand((PRIOR/'build.py').read_bytes()==git('show',prior_builder),'historical_builder_changed')
    demand(digest(PARENT_BINDING.read_bytes())==PARENT_BINDING_SHA256,'historical_parent_binding_changed')
    demand(json.loads(PARENT_BINDING.read_bytes())['preparation_git']==PRODUCT_PARENT,'wrong_parent_binding')
    old.update(ROOT=ROOT, BASE=PRODUCT_PARENT, BASE_BINDING=PARENT_BINDING,
               VERSION=BUILD_VERSION, ALLOWED=PRODUCT_FILES)
    builder(candidate)


if __name__=='__main__':
    main()
