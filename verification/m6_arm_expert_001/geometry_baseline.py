"""Independent ordered-section shrink baseline for arm-twist-patch-v1.

This consumes the same rest/current vertices and section indices as the model.
It does not use a generated reference, construction label, bone angle or product
feature extractor. A polygon's area-vector magnitude is rotation invariant and
equals its area for an ordered, simple planar section. For other section kinds
it is only a vector-area proxy, not a volume or anatomical damage diagnosis.

Malformed patches raise ValueError. A numerically unresolved rest section is
represented by NaN at that section; a collapsed current section scores 1.
"""
import math

import numpy as np


def _area(points):
    # Center before crossing so an otherwise irrelevant common translation
    # does not create large cancelling cross products. Scalar fsum is kept
    # independent from the product's NumPy feature implementation.
    count = len(points)
    center = [math.fsum(float(p[k]) for p in points)/count for k in range(3)]
    rows = [[float(p[k])-center[k] for k in range(3)] for p in points]
    components = []
    for first, second in ((1,2), (2,0), (0,1)):
        components.append(0.5*math.fsum(rows[i][first]*rows[(i+1)%count][second]
                                      -rows[i][second]*rows[(i+1)%count][first]
                                      for i in range(count)))
    area = math.hypot(*components)
    radius_squared = max(math.fsum(x*x for x in p) for p in rows)
    uncertainty = 64*math.ulp(1.0)*count*radius_squared
    return area, uncertainty


def predict(patch):
    """Return section shrink severities, max(0, 1-current_area/rest_area)."""
    if not isinstance(patch, dict) or patch.get('schema') != 'arm-twist-patch-v1':
        raise ValueError('geometry_baseline_patch_schema')
    try:
        rest = np.asarray(patch['rest_vertices'], dtype=np.float64)
        current = np.asarray(patch['current_vertices'], dtype=np.float64)
        sections = patch['sections']
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('geometry_baseline_patch_fields') from exc
    if (rest.ndim != 2 or rest.shape[1:] != (3,) or len(rest) < 3
            or current.shape != rest.shape or not np.isfinite(rest).all()
            or not np.isfinite(current).all()):
        raise ValueError('geometry_baseline_vertex_correspondence')
    if not isinstance(sections, (list,tuple)) or not sections:
        raise ValueError('geometry_baseline_sections')
    results = []
    for section in sections:
        if (not isinstance(section, (list,tuple,np.ndarray)) or len(section) < 3
                or any(isinstance(index, (bool,np.bool_)) or not isinstance(index, (int,np.integer))
                       or not 0 <= index < len(rest) for index in section)
                or len(set(section)) != len(section)):
            raise ValueError('geometry_baseline_section_indices')
        try:
            rest_area, uncertainty = _area(rest[list(section)])
            current_area, _ = _area(current[list(section)])
            if not math.isfinite(rest_area) or not math.isfinite(current_area) or rest_area <= uncertainty:
                results.append(float('nan'))
            else:
                results.append(max(0.0, 1.0-current_area/rest_area))
        except (OverflowError, ValueError):
            results.append(float('nan'))
    return np.asarray(results, dtype=np.float64)
