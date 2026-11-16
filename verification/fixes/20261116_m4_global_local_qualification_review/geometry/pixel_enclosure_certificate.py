"""Outward binary64 interval exclusion beyond the integer pixel bounds.

This checks candidate sample arithmetic only and constructs no image.
"""
from fractions import Fraction as F
import importlib.util
import json
import math
from pathlib import Path
import traceback

OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('independent_geometry',OUT/'independent_geometry.py')
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

class I:
    def __init__(self,lo,hi=None):
        self.lo,self.hi=F(lo),F(lo if hi is None else hi)

    @staticmethod
    def rounded(lo,hi):
        lower,upper=float(lo),float(hi)
        if F(lower)>lo:
            lower=math.nextafter(lower,-math.inf)
        if F(upper)<hi:
            upper=math.nextafter(upper,math.inf)
        return I(F(lower),F(upper))

    def __add__(self,other):
        other=other if isinstance(other,I) else I(other)
        return I.rounded(self.lo+other.lo,self.hi+other.hi)

    __radd__=__add__

    def __neg__(self):
        return I(-self.hi,-self.lo)

    def __sub__(self,other):
        return self+-other if isinstance(other,I) else self+I(-other)

    def __rsub__(self,other):
        return I(other)+-self

    def __mul__(self,other):
        other=other if isinstance(other,I) else I(other)
        products=[a*b for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return I.rounded(min(products),max(products))

    __rmul__=__mul__

    def __truediv__(self,other):
        other=other if isinstance(other,I) else I(other)
        if other.lo<=0<=other.hi:
            raise ValueError('division interval contains zero')
        quotients=[a/b for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return I.rounded(min(quotients),max(quotients))

def projected_interval(pose,point):
    gamma=F(16,2**53-16)
    tiny=F(16,2**1074)
    homogeneous=tuple(point)+(F(1),)
    camera=[g.dot(g.vec(row),homogeneous) for row in pose['view_matrix']]
    camera_error=[gamma*sum(abs(a*b) for a,b in zip(g.vec(row),homogeneous))+tiny for row in pose['view_matrix']]
    ndc=[]
    for row in pose['projection_matrix']:
        coefficients=g.vec(row)
        exact=g.dot(coefficients,camera)
        propagated=sum(abs(a)*b for a,b in zip(coefficients,camera_error))
        error=propagated+gamma*sum(abs(a)*(abs(b)+c) for a,b,c in zip(coefficients,camera,camera_error))+tiny
        ndc.append(I(exact-error,exact+error))
    return ((ndc[0]+1)*511/2,(1-ndc[1])*511/2)

def main():
    geometry=g.read(g.AUTHOR/'fixture/GEOMETRY.json')
    by_name={o['name']:dict(name=o['name'],vertices=list(map(g.vec,o['vertices_world_m'])),triangles=o['triangles']) for o in geometry['objects']}
    result=g.read(OUT/'RESULT.json')
    small={r['object']:r for r in result['components'] if r['eligible']}
    full=g.read(g.RUN/'sessions/global/product_full/call_001/SERVICE_RESULT.json')
    bounds={(r['view'],r['object']):r for r in result['actual_pixel_bounds']}
    samples=0
    largest_error=F(0)
    for pose in full['binding']['camera_specification']['views']:
        for name,component in small.items():
            obj=by_name[name]
            intervals=[projected_interval(pose,p) for p in obj['vertices']]
            for p,interval in zip(obj['vertices'],intervals):
                exact=g.exact_pixel(pose,p)
                largest_error=max(largest_error,*(max(abs(axis.lo-value),abs(axis.hi-value)) for axis,value in zip(interval,exact)))
            bound=bounds[(pose['name'],name)]
            axes=[[F(value) for value in pair] for pair in bound['axis_intervals']]
            for face in component['faces']:
                a,b,c=[intervals[i] for i in obj['triangles'][face]]
                area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                g.check(area.lo>F(1,2) or area.hi<-F(1,2),'interval triangle nondegeneracy')
                lower=[max(0,math.floor(min(p[k].lo for p in (a,b,c)))) for k in (0,1)]
                upper=[min(511,math.ceil(max(p[k].hi for p in (a,b,c)))) for k in (0,1)]
                for iy in range(lower[1],upper[1]+1):
                    for ix in range(lower[0],upper[0]+1):
                        x,y=F(2*ix+1,2),F(2*iy+1,2)
                        if axes[0][0]<=x<=axes[0][1] and axes[1][0]<=y<=axes[1][1]:
                            continue
                        w0=((b[0]-x)*(c[1]-y)-(b[1]-y)*(c[0]-x))/area
                        w1=((c[0]-x)*(a[1]-y)-(c[1]-y)*(a[0]-x))/area
                        w2=1-w0-w1
                        g.check(any(w.hi<F(-1e-10) for w in (w0,w1,w2)),'outside enclosed axis bounds cannot pass barycentric test')
                        samples+=1
    g.check(largest_error<F(1,65536),'actual coordinate roundoff inside independent enclosure')
    out=dict(status='passed',outside_triangle_sample_exclusions=samples,actual_matrix_projection_maximum_coordinate_error_px=str(largest_error),maximum_coordinate_error_px_float=float(largest_error),axis_enclosure_px='1/65536',method='gamma16 affine-dot error propagation plus outward binary64 intervals for screen coordinates and exact raster barycentric operation graph',new_rasters=0,new_live_calls=0)
    (OUT/'PIXEL_CERTIFICATE.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
    print(json.dumps(out))

if __name__=='__main__':
    try:
        main()
    except BaseException:
        (OUT/'PIXEL_CERTIFICATE_FAILURE.json').write_text(traceback.format_exc(),encoding='utf8')
        raise
