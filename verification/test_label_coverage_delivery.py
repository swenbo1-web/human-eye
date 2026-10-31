"""Visual focus reaches actual images/briefs without changing geometric facts."""
import copy
import json
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest

from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.task_brief import project_task_brief
from verification.test_auto_router import box


NEIGHBORS = ['east', 'north', 'south', 'west']
def raw_scene():
    rows = [box('base', [0,0,-.02], [.14,.12,.04]),
            box('part', [0,0,.024], [.08,.06,.04], True)]
    rows += [box(identity, center, [.024,.024,.024]) for identity,center in [
        ('east',[.045,0,.02]), ('north',[0,.035,.02]),
        ('south',[0,-.035,.02]), ('west',[-.045,0,.02])]]
    return {'revision':'label-delivery-r1','unit':'m','coordinate_frame':'world',
            'source':'local_contract_fixture','meshes':rows}

def query(focus=None):
    result={'mode':'exact_pairs','object_ids':list(NEIGHBORS),'max_exact_pairs':5}
    if focus is not None:result['label_object_ids']=list(focus)
    return result

def observe(router, request):
    return router.handle_event({'event':'before_model','session_id':'labels','scene':raw_scene(),
        'task_kind':'spatial_3d','focal_id':'part','reference_id':'base','query':request})

class ReadOnlyHost:
    is_alive=True
    def __init__(self):self.raw=raw_scene();self.applies=0;self.captures=0
    @contextmanager
    def transaction(self):yield
    def capture_scene(self):self.captures+=1;return copy.deepcopy(self.raw)
    def apply_transform(self,*args,**kwargs):self.applies+=1;raise AssertionError('Read-only test')


class LabelCoverageDeliveryTests(unittest.TestCase):
    def test_measurement_request_keeps_small_default_and_reports_two_unselected_risks(self):
        value=observe(HumanEyeAutoRouter(quad_size=256),query())
        facts=json.loads(value['context_text'])
        report=facts['label_presentation']
        self.assertEqual(report['selection_mode'],'pair_context')
        self.assertEqual(report['related_candidate_count'],4)
        self.assertEqual(report['selected_related_count'],2)
        self.assertEqual(report['unselected_known_penetration_count'],2)
        self.assertFalse(report['execution_authority'])
        self.assertEqual(sum(c['is_penetrating'] is True for c in facts['scene_contacts']),4)

    def test_four_visual_targets_are_depth_bound_and_core_aliases_survive(self):
        value=observe(HumanEyeAutoRouter(quad_size=256),query(NEIGHBORS))
        facts=json.loads(value['context_text']);canvas=facts['canvas']
        report=facts['label_presentation']
        self.assertEqual(report['visual_focus_count'],4)
        self.assertEqual(report['visual_focus_drawn_count'],4)
        self.assertEqual(report['visual_focus_not_drawn_ids'],[])
        self.assertEqual(report['unselected_related_count'],0)
        q1=canvas['views'][0];labels={r['object_id']:r for r in q1['projected_labels']}
        self.assertTrue(set(NEIGHBORS).issubset(labels))
        self.assertEqual(labels['part']['display_label'],'A')
        self.assertEqual(labels['base']['display_label'],'B')
        for identity in NEIGHBORS:
            self.assertEqual(labels[identity]['anchor_source'],'current_full_scene_depth_winner')
        self.assertEqual(q1['label_layout']['visual_focus_coverage']['undrawn_objects'],[])

    def test_late_visual_targets_take_selection_priority_without_reclassifying_contacts(self):
        focused=observe(HumanEyeAutoRouter(quad_size=256),query(['south','west']))
        facts=json.loads(focused['context_text']);plan=facts['canvas']['task_labels']
        self.assertEqual(set(plan['related_object_ids']),{'south','west'})
        self.assertEqual(set(plan['related_reasons'].values()),{'known_penetration'})
        self.assertEqual(facts['label_presentation']['unselected_known_penetration_count'],2)
        self.assertEqual(sum(c['is_penetrating'] is True for c in facts['scene_contacts']),4)

    def test_tiny_view_keeps_explicit_undrawn_reasons_and_no_fake_surface_labels(self):
        value=observe(HumanEyeAutoRouter(quad_size=64),query(NEIGHBORS))
        facts=json.loads(value['context_text'])
        self.assertEqual(facts['label_presentation']['visual_focus_drawn_count'],0)
        self.assertEqual(facts['label_presentation']['visual_focus_not_drawn_ids'],NEIGHBORS)
        for view in facts['canvas']['views']:
            report=view['label_layout']['visual_focus_coverage']
            self.assertEqual(report['drawn_object_ids'],[])
            self.assertEqual({r['object_id'] for r in report['undrawn_objects']},set(NEIGHBORS))
            self.assertTrue(all(r['reason'] in {'view_too_small','not_surface_visible',
                'insufficient_surface_pixels'} for r in report['undrawn_objects']))

    def test_focus_has_no_effect_on_measured_contacts_or_action_gate(self):
        a=json.loads(observe(HumanEyeAutoRouter(quad_size=256),query())['context_text'])
        b=json.loads(observe(HumanEyeAutoRouter(quad_size=256),query(NEIGHBORS))['context_text'])
        for field in ['measurement','scene_contacts','query_result','scene_assessment','scene_capabilities']:
            self.assertEqual(a[field],b[field],field)

    def test_service_cache_separates_focus_and_brief_retains_binding_and_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            path.write_text(json.dumps({'schema_version':'1.0','project_root':str(Path(__file__).resolve().parents[1]),
                'state_file':'state.json','audit_file':'audit.jsonl','quad_size':256,'max_sessions':2}),encoding='utf-8')
            host=ReadOnlyHost();service=LiveSpatialService(path,host=host)
            a=service.observe('labels',focal_id='part',reference_id='base',query=query())
            b=service.observe('labels',focal_id='part',reference_id='base',query=query(NEIGHBORS))
            c=service.observe('labels',focal_id='part',reference_id='base',query=query(NEIGHBORS[::-1]))
            self.assertFalse(a['routing']['cache_hit']);self.assertFalse(b['routing']['cache_hit'])
            self.assertTrue(c['routing']['cache_hit'])
            full=json.loads(b['routing']['context_text']);brief=project_task_brief(b)
            self.assertIsNotNone(brief)
            self.assertEqual(brief['observation']['label_presentation'],full['label_presentation'])
            self.assertEqual(brief['observation']['canvas']['object_labels'],full['canvas']['object_labels'])
            for av,bv in zip(full['canvas']['views'],brief['observation']['canvas']['views']):
                self.assertEqual(av['label_layout'],bv['label_layout'])
            self.assertEqual(b['routing']['image'],brief['routing']['image'])
            self.assertEqual(host.applies,0)

if __name__=='__main__':unittest.main()
