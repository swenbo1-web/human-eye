"""New fixture recipes, private diagnostic boundary and readonly enforcement."""
from pathlib import Path
from types import SimpleNamespace as NS
import base64,copy,json,math,tempfile,time,unittest
from unittest.mock import patch

from verification.model_trial.native_client import OwnedFixture,CASES as CLIENT_CASES,PUBLIC_COMMANDS
from verification.model_trial.native_fixture import OwnedGateway,CASES,Refusal


def recipe(case,angle=10,gap=.004,origin=None):
    origin=origin or [0.,0.,0.]
    scene=NS(name='',unit_settings=NS(system='',scale_length=0),objects=[])
    layer=NS(objects=NS(active=None),update=lambda:None)
    bpy=NS(app=NS(version=(5,2,1)),context=NS(scene=scene,view_layer=layer),
           ops=NS(wm=NS(read_factory_settings=lambda **kw:None)))
    g=object.__new__(OwnedGateway);g.bpy=bpy
    g.config={'case':case,'angle_deg':angle,'gap_m':gap,'origin':origin}
    g.module=NS(BlenderSceneHost=NS(object_id=lambda obj:'obj:'+obj.name))
    g.boxes=[]
    def box(name,size,center,color,rotation,opened=False):
        obj=NS(name=name,select_set=lambda selected:None)
        scene.objects.append(obj)
        g.boxes.append({'name':name,'size':size,'center':center,'color':color,
                       'rotation':rotation,'opened':opened})
        return obj
    g._box=box;g._create_scene();return g


class FixtureVariantsTests(unittest.TestCase):
    def test_case_sets_match_and_public_tools_unchanged(self):
        self.assertEqual(CLIENT_CASES,frozenset(CASES))
        self.assertEqual(PUBLIC_COMMANDS,frozenset({'native_scene_query','native_transform','native_look'}))

    def test_new_cases_validate_and_readonly_constructor_sets_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            for case in ('occluded','readonly_occluded'):
                f=OwnedFixture(Path(temp)/case,case=case)
                self.assertEqual(f.readonly,case=='readonly_occluded')
                self.assertFalse(f._started)

    def test_old_recipe_counts_and_geometry_remain(self):
        for case in ('floor','tilted','dense','readonly','open_focal','open_reference'):
            with self.subTest(case=case):
                g=recipe(case,angle=14,gap=.003,origin=[.031,-.042,.05])
                self.assertEqual(len(g.boxes),26 if case=='dense' else 2)
                base,part=g.boxes[:2]
                self.assertEqual(base['size'],[.2,.2,.2])
                self.assertEqual(part['size'],[.06,.06,.1])
                self.assertEqual(base['opened'],case=='open_reference')
                self.assertEqual(part['opened'],case=='open_focal')
                self.assertEqual(base['center'],[.031,-.042,.05])
                angle=0 if case=='floor' else math.radians(14)
                expected=[.031+math.sin(angle)*.153,-.042,.05+math.cos(angle)*.153]
                self.assertEqual(part['center'],expected)

    def test_blocker_ray_alignment_and_full_z_corridor_separation(self):
        d=[v/math.sqrt(2+.75*.75) for v in (1,-1,.75)]
        for angle in (-30,-14,-10,-6,0,6,10,14,30):
            for gap in (.003,.004,.005):
                with self.subTest(angle=angle,gap=gap):
                    g=recipe('occluded',angle=angle,gap=gap,origin=[.09,-.08,.04])
                    base,part,block=g.boxes
                    self.assertEqual(block['name'],'FixedOccluder')
                    self.assertEqual(block['size'],[.14]*3)
                    self.assertFalse(block['opened'])
                    delta=[block['center'][k]-part['center'][k] for k in range(3)]
                    for k in range(3):self.assertAlmostEqual(delta[k],.3*d[k],places=14)
                    # Both the base and focal keep this Y interval over every
                    # allowed Z-only path, independent of angle and origin.
                    occluder_high_y=block['center'][1]+.07
                    self.assertLess(occluder_high_y,base['center'][1]-.1-.017)
                    self.assertLess(occluder_high_y,part['center'][1]-.03)
                    # A .07m ball lies in the blocker, while all focal points
                    # lie in its .0656m circumsphere, giving conservative full
                    # projected silhouette coverage from the aligned SCENE ray.
                    self.assertLess(math.sqrt(.03**2+.03**2+.05**2),.07)

    def test_readonly_occluded_same_geometry_as_occluded(self):
        self.assertEqual(recipe('occluded').boxes,recipe('readonly_occluded').boxes)

    def test_readonly_occluded_write_gate_even_if_flag_false(self):
        g=object.__new__(OwnedGateway);g.quarantined=False;g.episode_started=time.monotonic()
        g.episode_deadline=g.episode_started+10;g.started=g.episode_started
        g.config={'lifetime_s':360,'readonly':False,'case':'readonly_occluded'}
        with self.assertRaises(Refusal) as caught:g._write_permission()
        self.assertEqual(caught.exception.code,'read_only')

    def test_owner_visibility_not_available_as_public_tool(self):
        with tempfile.TemporaryDirectory() as temp:
            f=OwnedFixture(Path(temp)/'private')
            with patch.object(f,'_exchange') as exchange:
                with self.assertRaises(ValueError):f.call('owner_visibility',{'view':'SCENE'})
                exchange.assert_not_called()
                f.owner_visibility('SCENE')
                exchange.assert_called_once_with('owner_visibility',{'view':'SCENE'})
                with self.assertRaises(ValueError):f.owner_visibility('ANSWER')

    def test_public_query_stays_exactly_common_fields(self):
        g=object.__new__(OwnedGateway)
        g._objects=lambda:{'BluePart':{'object_id':'id','name':'BluePart','local_vertices':[],
            'world_vertices':[],'faces':[],'matrix':[],'color':[0,0,1,1],
            'case':'occluded','normal':[0,0,1],'seed':123,'mask':'private'}}
        value=g.query()
        self.assertEqual(set(value),{'unit','coordinate_frame','revision','objects'})
        self.assertEqual(set(value['objects'][0]),{'object_id','name','local_vertices',
            'world_vertices','faces','matrix','color'})

    def test_owner_diagnostic_wrapper_preserves_fields_and_validates_masks(self):
        g=object.__new__(OwnedGateway)
        state={'unit':'m','objects':[]};g.query=lambda:copy.deepcopy(state)
        def look(params,**kw):
            n=10 if kw.get('_isolated') else 2
            return {'red_pixels_linear':n,'image_base64':base64.b64encode(b'png').decode(),
                    'png_sha256':'same','camera':{'width':384,'height':384}}
        g.look=look
        report=g.visibility({'view':'SCENE'})
        self.assertEqual(report['mask']['visible_fraction'],.2)
        self.assertTrue(report['scene_unchanged'])
        self.assertIn('full_scene_png_base64',report)
        with self.assertRaises(Refusal):g.visibility({'view':'SCENE','seed':123})


if __name__=='__main__':unittest.main()
