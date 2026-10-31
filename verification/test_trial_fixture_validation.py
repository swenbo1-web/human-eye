"""Independent raw-fixture and supplied-PNG adversarial checks, no Blender."""
from copy import deepcopy
import hashlib,math,struct,unittest,zlib

from verification.model_trial import fixture_validation as validator
from verification.model_trial.test_oracle import scene,box,refresh


def base_scene(angle=0,gap=.004):
    native=scene(angle,gap=gap)
    native['objects'].pop('Distractor')
    native.update(readonly=False,allow_apply=True)
    return native


def add_occluder(native):
    focal=native['objects']['BluePart']
    center=[sum(v[k] for v in focal['world_vertices'])/8 for k in range(3)]
    direction=validator._unit((1,-1,.75))
    native['objects']['Occluder']=box([.13,.13,.13],[center[k]+direction[k]*.30 for k in range(3)])


def camera(native,view):
    direction=validator._unit(validator.VIEWS[view])
    up=[0,0,1]
    if abs(validator._dot(up,direction))>.999:up=[0,1,0]
    right=validator._unit(validator._cross(up,direction));up=validator._cross(direction,right)
    vertices=[v for obj in native['objects'].values() for v in obj['world_vertices']]
    center=[(min(v[k] for v in vertices)+max(v[k] for v in vertices))/2 for k in range(3)]
    projected=[[validator._dot(validator._sub(v,center),a) for a in (right,up)] for v in vertices]
    span=max(max(v[k] for v in projected)-min(v[k] for v in projected) for k in (0,1))*1.25+.04
    return {'eye_direction':direction,'center':center,'camera_right':right,'camera_up':up,
            'width':40,'height':40,'ortho_scale':span}


def mask_png(red=True,filter_kind=0,alpha=255):
    width=height=40;channels=4
    rows=[];prior=bytearray(width*channels)
    for y in range(height):
        row=bytearray()
        for x in range(width):
            row.extend((255 if red and 10<=x<30 and 10<=y<30 else 0,0,0,alpha))
        filtered=bytearray(row)
        for i in range(len(row)):
            a=row[i-channels] if i>=channels else 0;b=prior[i];c=prior[i-channels] if i>=channels else 0
            predict=(0,a,b,(a+b)//2,validator._paeth(a,b,c))[filter_kind]
            filtered[i]=(row[i]-predict)&255
        rows.append(bytes((filter_kind,))+filtered);prior=row
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))


def reports(native,scene_visible=False):
    result={}
    for view in ('SCENE','XY','XZ'):
        visible=mask_png(red=scene_visible or view!='SCENE');isolated=mask_png()
        import base64
        result[view]={'camera':camera(native,view),
            'full_scene_png_base64':base64.b64encode(visible).decode(),
            'focal_only_png_base64':base64.b64encode(isolated).decode(),
            'visible_mask_png_sha256':hashlib.sha256(visible).hexdigest(),
            'isolated_mask_png_sha256':hashlib.sha256(isolated).hexdigest(),
            'source':'synthetic masks test decoding only; not real renderer evidence'}
    return result


class FixtureValidationTests(unittest.TestCase):
    def test_actual_raw_geometry_goal_at_translated_tilted_support(self):
        native=base_scene(math.radians(14),.005)
        for obj in native['objects'].values():
            obj['matrix'][0][3]+=.071;obj['matrix'][1][3]-=.043;obj['matrix'][2][3]+=.02
            refresh(obj)
        result=validator.validate_fixture(native,{'kind':'goal','initial_gap_m':.005})
        self.assertTrue(result['passed'],result)
        self.assertFalse(result['engine_support_assessed'])
        self.assertLess(abs(result['predicted_world_z_translation_m']),.008)
        self.assertTrue(result['mathematical_sweep']['passed'])

    def test_gap_mismatch_and_bad_range_fail_without_seed_replacement(self):
        native=base_scene()
        result=validator.validate_fixture(native,{'kind':'goal','initial_gap_m':.003})
        self.assertFalse(result['passed']);self.assertFalse(result['checks']['manifest_gap_matches_native_projection'])
        native=base_scene(gap=.006)
        self.assertFalse(validator.validate_fixture(native,{'kind':'goal'})['passed'])

    def test_dense_count_and_collision_independently_checked(self):
        native=base_scene()
        for i in range(24):native['objects']['D'+str(i)]=box([.01,.01,.01],[.3+.025*(i%6),-.05+.025*(i//6),.03])
        self.assertTrue(validator.validate_fixture(native,{'kind':'goal','dense':True})['passed'])
        native['objects'].pop('D23')
        self.assertFalse(validator.validate_fixture(native,{'kind':'goal','dense':True})['passed'])
        native['objects']['D0']=deepcopy(native['objects']['BluePart'])
        self.assertFalse(validator.validate_fixture(native,{'kind':'goal'})['passed'])

    def test_open_expected_object_must_actually_be_open(self):
        native=base_scene();native['objects']['BluePart']['faces'].pop()
        passed=validator.validate_fixture(native,{'kind':'unsupported','open_object':'BluePart'})
        self.assertTrue(passed['passed'],passed)
        wrong=validator.validate_fixture(native,{'kind':'unsupported','open_object':'GreyBase'})
        self.assertFalse(wrong['passed'])
        closed=validator.validate_fixture(base_scene(),{'kind':'unsupported','open_object':'BluePart'})
        self.assertFalse(closed['passed'])

    def test_readonly_flag_is_separate_from_geometry(self):
        native=base_scene()
        self.assertFalse(validator.validate_fixture(native,{'kind':'readonly'})['passed'])
        native.update(readonly=True,allow_apply=False)
        self.assertTrue(validator.validate_fixture(native,{'kind':'readonly'})['passed'])

    def test_raw_ray_occlusion_and_alternate_recovery(self):
        native=base_scene();add_occluder(native)
        evidence=reports(native)
        result=validator.validate_fixture(native,{'kind':'goal','occluded':True},evidence)
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['visibility']['SCENE']['geometry']['external_blockers'],['Occluder'])
        self.assertEqual(result['visibility']['SCENE']['native_masks']['visible_pixels'],0)
        self.assertEqual(result['visibility']['XY']['geometry']['visible_fraction'],1.)

    def test_case_name_or_masks_alone_cannot_prove_occlusion(self):
        native=base_scene();native['case']='occluded'
        result=validator.validate_fixture(native,{'kind':'goal','occluded':True},reports(native))
        self.assertFalse(result['passed'])
        native=base_scene();add_occluder(native)
        result=validator.validate_fixture(native,{'kind':'goal','occluded':True},reports(native,scene_visible=True))
        self.assertFalse(result['passed'])
        self.assertFalse(validator.validate_fixture(native,{'kind':'goal','occluded':True})['passed'])

    def test_camera_and_mask_binding_fail_closed(self):
        native=base_scene();add_occluder(native)
        for mutation in ('basis','direction','hash','dimensions'):
            evidence=reports(native)
            if mutation=='basis':evidence['SCENE']['camera']['camera_up']=[1,0,0]
            elif mutation=='direction':evidence['SCENE']['camera']['eye_direction']=[0,0,1]
            elif mutation=='hash':evidence['SCENE']['visible_mask_png_sha256']='0'*64
            else:evidence['SCENE']['camera']['width']=100
            with self.subTest(mutation=mutation):
                self.assertFalse(validator.validate_fixture(native,{'kind':'goal','occluded':True},evidence)['passed'])

    def test_real_blender_float32_camera_readback_agrees_with_common_view(self):
        # Exact camera values observed in real P05 preflight. No seed/answer is
        # needed to reproduce binary32 Euler/matrix direction agreement.
        actual={
            'SCENE':([.6246951222419739,-.6246950030326843,.46852120757102966],
                     [.7071067094802856,.70710688829422,6.57667413861418e-08],
                     [-.33129459619522095,.3312944173812866,.8834522366523743]),
            'XY':([0.,0.,1.],[-1.,-1.5099580252808664e-07,0.],[1.5099580252808664e-07,-1.,0.]),
            'XZ':([0.,-1.,-1.6292068494294654e-07],[1.,0.,0.],[0.,-1.6292068494294654e-07,1.])}
        for view,(direction,right,up) in actual.items():
            c=camera(base_scene(),view)
            c.update(eye_direction=direction,camera_right=right,camera_up=up)
            with self.subTest(view=view):self.assertTrue(validator._camera(c,view))
        c=camera(base_scene(),'XZ');c['eye_direction']=[0.,-1.,1e-4]
        with self.assertRaises(ValueError):validator._camera(c,'XZ')

    def test_all_png_filters_and_alpha_classification(self):
        for kind in range(5):
            with self.subTest(filter=kind):self.assertEqual(validator.decode_red_mask(mask_png(filter_kind=kind))['red_pixels'],400)
        self.assertEqual(validator.decode_red_mask(mask_png(alpha=0))['red_pixels'],0)

    def test_png_corruption_truncation_and_bomb_fail(self):
        good=mask_png()
        for bad in (good[:-1],good+b'x',good[:32]+b'x'+good[33:],b'notpng'):
            with self.assertRaises(ValueError):validator.decode_red_mask(bad)

    def test_ray_boundary_and_behind_eye(self):
        tri=([0,0,1],[1,0,1],[0,1,1])
        self.assertEqual(validator.ray_triangle_distance([.2,.2,0],[0,0,1],*tri),1.)
        self.assertIsNone(validator.ray_triangle_distance([.2,.2,2],[0,0,1],*tri))
        self.assertIsNone(validator.ray_triangle_distance([2,2,0],[0,0,1],*tri))
        self.assertIsNone(validator.ray_triangle_distance([.2,.2,0],[1,0,0],*tri))

    def test_bad_native_json_fails_closed(self):
        for native in (None,{}, {'objects':{}}, {'normal':[float('nan'),0,1],'objects':{}}):
            self.assertFalse(validator.validate_fixture(native,{'kind':'goal'})['passed'])


if __name__=='__main__':unittest.main()
