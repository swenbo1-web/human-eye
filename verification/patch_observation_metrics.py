"""Independent fixed-fixture pixel checks, not production visibility logic."""
import io,math
from PIL import Image
from verification.patch_observation_fixtures import edge_samples,analytically_visible


def evaluate(case,proof,png):
    image=Image.open(io.BytesIO(png)).convert('RGBA')
    if image.size!=(384,384) or proof['resolution_px']!=[384,384] or proof['view']!='XY':
        raise ValueError('fixed_XY_384_reference_required')
    matrix=proof['camera_matrix_host_units'];scale=proof['unit_scale_m'];span=proof['ortho_scale_bu']*scale
    axes=[[matrix[k][i] for k in range(3)] for i in (0,1)]
    location=[matrix[k][3] for k in range(3)]
    def project(point):
        local=[point[k]/scale-location[k] for k in range(3)]
        x,y=[math.fsum(a*b for a,b in zip(local,axis))/proof['ortho_scale_bu'] for axis in axes]
        return [(x+.5)*384-.5,(.5-y)*384-.5]
    def pixel(point):
        x,y=map(round,project(point))
        return list(image.getpixel((x,y))) if 0<=x<384 and 0<=y<384 else None
    def blue(rgba):
        return rgba is not None and rgba[3]>128 and rgba[2]>rgba[0]+40 and rgba[2]>rgba[1]+20
    distance=3*span/384;pairs=[]
    for sample in edge_samples(case):
        p=sample['point'];direction=sample['outside']
        outside=pixel([p[k]+distance*direction[k] for k in range(3)])
        inside=pixel([p[k]-distance*direction[k] for k in range(3)])
        contrast=None if outside is None or inside is None else sum(abs(outside[k]-inside[k]) for k in range(3))
        readable=contrast is not None and blue(outside) and not blue(inside) and contrast>=80
        pairs.append(dict(point=p,analytic_visible=analytically_visible(case,p),outside_rgba=outside,
                          inside_rgba=inside,contrast=contrast,readable=readable))
    width=384*min(2*x for x in case['half'])/span
    count=sum(x['readable'] for x in pairs)
    return dict(scope='controlled_opaque_blue_aperture_not_general_segmentation',
                aperture_min_width_px=width,readable_edge_pairs=count,edge_pairs=pairs,
                useful_feature_evidence=width>=16 and count>=8)
