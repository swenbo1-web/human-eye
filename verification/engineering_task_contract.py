"""Common public-task ROI policy and pinned experimental bootstrap."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def choose_region(regions, anchor, *, total, omitted=0, complete=True):
    if complete is not True:return dict(status='unknown',reason='scan_incomplete')
    if type(total) is not int or total<0 or type(omitted) is not int or omitted<0:raise ValueError('region_counts')
    if omitted or len(regions)!=total:return dict(status='unknown',reason='omitted_regions_have_no_bounds')
    if type(anchor) is not list or len(anchor)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in anchor):
        raise ValueError('anchor')
    if not regions:return dict(status='empty',reason='no_boundary')
    if len({r['ref'] for r in regions})!=len(regions):raise ValueError('duplicate_region_ref')
    ranked=[]
    for region in regions:
        bounds=region.get('bounds')
        if bounds is None:return dict(status='unknown',reason='region_position_unknown')
        if (type(bounds) is not list or len(bounds)!=2 or any(type(row) is not list or len(row)!=3 for row in bounds)
            or any(type(v) not in (int,float) or not math.isfinite(v) for row in bounds for v in row)
            or any(bounds[0][k]>bounds[1][k] for k in range(3))):raise ValueError('bounds')
        center=[bounds[0][k]/2+bounds[1][k]/2 for k in range(3)]
        try:key=(sum((center[k]-anchor[k])**2 for k in range(3)),sum(((bounds[1][k]-bounds[0][k])/2)**2 for k in range(3)))
        except OverflowError:return dict(status='unknown',reason='region_score_nonfinite')
        if not all(math.isfinite(v) for v in key):return dict(status='unknown',reason='region_score_nonfinite')
        ranked.append((key,region))
    ranked.sort(key=lambda item:item[0])
    if len(ranked)>1 and ranked[0][0]==ranked[1][0]:return dict(status='unknown',reason='ambiguous_nearest_boundary')
    return dict(status='selected',region=ranked[0][1],policy='world_aabb_anchor_distance_then_half_diagonal')


def he_regions(value):
    """Use public diagnostic positions and refs, never scene-oracle indices."""
    diagnostic=value['diagnostic'];check=diagnostic['report']['checks']['boundary_edges']
    refs={r['cluster_ordinal']:r['patch_ref'] for r in value['patch_refs'] if r['category']=='boundary_edges'}
    regions=[]
    for patch in diagnostic['patches']:
        if patch['category']!='boundary_edges' or patch['cluster_ordinal'] not in refs:continue
        position=patch['position']
        regions.append(dict(ref=refs[patch['cluster_ordinal']],bounds=position.get('world_bounds_m')
            if position.get('status')=='known' and position.get('length_unit')=='m' else None))
    return regions,dict(total=check['total'],omitted=check['omitted'],complete=check['state']=='complete')


def bootstrap(entry):
    """Use the existing fixed installation recognizer, not a source checkout."""
    entry=Path(entry).resolve();spec=importlib.util.spec_from_file_location('_engineering_fixed_entry',entry)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root'])
    identity,origins=module.verify_imported_runtime(proof)
    if identity['source_sha256']!='8bcdc431240711482c24915af327b2227a9f4c76b0b437b389339f281451350d':
        raise ValueError('frozen_engine_required')
    return identity,origins
