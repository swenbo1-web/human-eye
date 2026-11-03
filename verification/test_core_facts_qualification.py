"""Short negative tests for independent qualification, without Blender."""
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from verification import run_core_facts_qualification as q
from verification import core_facts_fixtures as fixture


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.entry=self.folder/'entry.py';self.entry.write_text('# QA\n')
        self.held=ROOT/'verification/fixtures/core_facts_heldout_v1.json'
        self.legacy=ROOT/'verification/fixtures/core_facts_legacy_v1.json'
        self.registration=q.load(self.held)
    def manifest(self):
        cases=[]
        for held,records in ((False,q.load(self.legacy)['cases']),(True,self.registration['cases'])):
            for c in records:
                name=c['case' if held else 'name']
                calls=[dict(mode=mode,block=block,folder=str(self.folder/name/f'{block}_{mode}'))
                    for block in range(3) for mode in ('core','context')]
                cases.append(dict(case=name,heldout=held,catalog=str(self.folder/name/'CATALOG.json'),
                    policy=str(self.folder/name/'POLICY.json'),profile=str(self.folder/name/'PROFILE.json'),
                    selection=str(self.folder/name/'SELECTION.json'),calls=calls))
        return dict(schema='complete-core-acquisition-manifest-v1',runtime_source_sha256='a'*64,
            legacy_registration=str(self.legacy),heldout_registration=str(self.held),blocks=3,cases=cases,
            entry=str(self.entry),entry_sha256=q.sha(self.entry),python=sys.executable)
    def test_exact_complete_manifest(self):
        manifest=self.manifest();q.validate_manifest(manifest)
        self.assertEqual(sum(len(c['calls']) for c in manifest['cases']),96)
    def test_empty_extra_duplicate_or_missing_rows_fail(self):
        for mutate in (lambda m:m.update(cases=[]),lambda m:m['cases'].append(copy.deepcopy(m['cases'][0])),
                       lambda m:m['cases'][0]['calls'].pop(),
                       lambda m:m['cases'][0]['calls'].append(copy.deepcopy(m['cases'][0]['calls'][0])),
                       lambda m:m['cases'][0]['calls'][0].update(block=True),
                       lambda m:m['cases'][0].update(heldout=True),
                       lambda m:m['cases'][0]['calls'][1].update(folder=m['cases'][0]['calls'][0]['folder'])):
            manifest=self.manifest();mutate(manifest)
            with self.assertRaises(AssertionError):q.validate_manifest(manifest)
    def test_modified_registration_cannot_define_its_own_cases(self):
        path=self.folder/'registration.json';path.write_text(self.held.read_text()+' ')
        manifest=self.manifest();manifest['heldout_registration']=str(path)
        with self.assertRaises(AssertionError):q.validate_manifest(manifest)
    def test_frozen_analytic_truth_never_uses_production_fields(self):
        answers={c['case']:fixture.analytic_expectation(self.registration,c['case']) for c in self.registration['cases']}
        self.assertEqual(answers['omitted_extremum8']['facts']['core_extrema']['max_principal_stretch'],2)
        self.assertEqual(answers['outer_dominates_mixed18']['facts']['core_states'],dict(measured=14,collapsed=0,unknown=4))
        self.assertEqual(answers['empty_core']['members'],[])
        self.assertIsNone(answers['all_unknown_core3']['facts']['core_extrema']['max_area_ratio'])
        self.assertEqual(answers['closed_boundary_contacts']['members'],[0,1])
    def test_counts_booleans_and_extra_metric_cannot_pass(self):
        expected=fixture.analytic_expectation(self.registration,'mixed_analytic3')['facts']
        for mutate in (lambda f:f['core_states'].update(unknown=True),
                       lambda f:f['core_extrema'].update(extra=1),
                       lambda f:f['core_extrema'].update(max_area_ratio=float('nan'))):
            actual=copy.deepcopy(expected);mutate(actual)
            with self.assertRaises(AssertionError):q.same_facts(actual,expected)
    def test_principal_stretch_zip_truncation_closed(self):
        row=dict(triangle=0,vertices=[0,1,2],state='measured',reason=None,unweighted_vertices=[],
            reference_geometry='nonzero_area',current_geometry='nonzero_area',principal_stretches=[1.,1.],area_ratio=1.)
        q.check_row(row,row)
        for values in ([1.],[1.,1.,99.],[True,1.],[float('inf'),1.]):
            changed={**row,'principal_stretches':values}
            with self.assertRaises(AssertionError):q.check_row(changed,row)
    def test_unknown_exterior_does_not_count_as_realized(self):
        analytic=fixture.analytic_expectation(self.registration,'outer_dominates_mixed18')
        packet=dict(inputs=dict(mesh=dict(triangles=[[]]*19)))
        with patch.object(q,'all_facts',return_value={18:dict(state='unknown',reason='metric_resolution_insufficient')}):
            result=q.exterior_challenge(packet,analytic)
        self.assertEqual(result['status'],'not_realized');self.assertFalse(result['passed'])
        self.assertEqual(result['unknown_reasons'],{'18':'metric_resolution_insufficient'})
    def test_strict_json_rejects_duplicate(self):
        path=self.folder/'bad.json';path.write_text('{"case":1,"case":2}')
        with self.assertRaises(ValueError):q.load(path)
    def test_command_input_bindings_are_not_receipt_self_assertions(self):
        profile=self.folder/'profile.json';profile.write_text('{}')
        policy=self.folder/'policy.json';policy.write_text('{"policy":1}')
        selection=self.folder/'selection.json';selection.write_text('{"selection":1}')
        folder=self.folder/'call';call=dict(mode='core',folder=str(folder))
        manifest=dict(entry=str(self.entry),entry_sha256=q.sha(self.entry),python=sys.executable)
        command=[sys.executable,'-I','-B',str(self.entry),'--operator-profile',str(profile),
            '--output',str(folder/'readback'),'--core-query',str(selection),
            '--context-policy',str(policy),'--context-policy-sha256',q.sha(policy)]
        receipt=dict(command=command,operator_profile=str(profile),entry_sha256=q.sha(self.entry),
            operator_profile_sha256=q.sha(profile),context_policy_sha256=q.sha(policy),selection_sha256=q.sha(selection))
        q.validate_command(receipt,call,manifest,policy)
        for mutate in (lambda r:r['command'].append('--extra'),
                       lambda r:r['command'].__setitem__(7,str(folder/'other_output')),
                       lambda r:r['command'].__setitem__(8,'--context-query'),
                       lambda r:r.update(selection_sha256='a'*64),
                       lambda r:r.update(operator_profile_sha256='b'*64),
                       lambda r:r.update(entry_sha256='c'*64)):
            changed=copy.deepcopy(receipt);mutate(changed)
            with self.assertRaises(AssertionError):q.validate_command(changed,call,manifest,policy)


if __name__=='__main__':unittest.main()
