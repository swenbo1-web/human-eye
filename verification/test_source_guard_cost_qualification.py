"""Counterexamples for one pinned finite cost trial; no Blender is started."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from verification import run_source_guard_cost_qualification as c


def result():
    rows=[]
    for pair in range(8):
        for arm in ('old','candidate'):
            duration=10_000_000 if arm=='old' else 7_000_000
            calls=[dict(kind='cold_native',repetition=0,status='passed',complete_ns=duration)]
            calls.extend(dict(kind=k,repetition=i,status='passed',complete_ns=duration if k!='status' else 1_000_000)
                for k in ('hot_native','ordinary_gap_text','status') for i in range(3))
            rows.append(dict(lane='default_fixed_entry_external_qa_tcp',arm=arm,pair=pair,status='completed',calls=calls,
                external_blender_exit_code=0,cold_service_complete_ns=100_000_000,cold_first_native_complete_ns=200_000_000,service_complete_cycle_ns=500_000_000))
            rows.append(dict(lane='owned_fixed_file_worker',arm=arm,pair=pair,status='passed',complete_cycle_ns=100_000_000,detail=dict(process_reaped=True,setters=0)))
    source={k:{arm:{i:10_000_000 if arm=='old' else 7_000_000 for i in range(8)} for arm in ('old','candidate')} for k in ('hot_native','ordinary_gap_text')}
    return dict(rows=rows),source


class CostTrialTests(unittest.TestCase):
    def test_pinned_complete_improvement_passes(self):
        r,s=result();self.assertTrue(c.evaluate(r,s)['passed']);self.assertEqual(len(c.evaluate(r,s)['checks']),7)

    def test_missing_duplicate_refused_and_changed_geometry_outcomes_never_pass(self):
        for mutate in (lambda r:r['rows'].pop(),lambda r:r['rows'].__setitem__(1,copy.deepcopy(r['rows'][0])),
                lambda r:r['rows'][0].update(status='stopped'),lambda r:r['rows'][0]['calls'].pop(),
                lambda r:r['rows'][0]['calls'][0].update(status='unknown'),lambda r:r['rows'][1]['detail'].update(setters=1),
                lambda r:r['rows'][0].update(cold_service_complete_ns=True)):
            r,s=result();mutate(r);self.assertFalse(c.evaluate(r,s)['passed'])

    def test_primary_noise_and_only_five_winning_blocks_fail(self):
        for winning in (0,5):
            r,s=result()
            for row in r['rows']:
                if row['arm']=='candidate' and row['lane']=='default_fixed_entry_external_qa_tcp' and row['pair']>=winning:
                    for v in row['calls']:
                        if v['kind'] in ('ordinary_gap_text','hot_native'):v['complete_ns']=10_000_000
            self.assertFalse(c.evaluate(r,s)['passed'])

    def test_p95_slowdown_is_not_hidden_by_median_improvement(self):
        r,s=result()
        # Two slow values enter nearest-rank p95 among the24 actual calls.
        row=next(r for r in r['rows'] if r['arm']=='candidate' and r['lane']=='default_fixed_entry_external_qa_tcp')
        values=[v for v in row['calls'] if v['kind']=='ordinary_gap_text']
        values[0]['complete_ns']=values[1]['complete_ns']=20_000_000
        self.assertFalse(c.evaluate(r,s)['passed'])

    def test_source_check_must_improve_as_well_as_complete_request(self):
        r,s=result();s['hot_native']['candidate']={i:10_000_000 for i in range(8)}
        self.assertFalse(c.evaluate(r,s)['passed'])

    def test_non_target_status_and_startup_controls_have_tail_limits(self):
        for field in ('status','cold_service_complete_ns','cold_first_native_complete_ns','service_complete_cycle_ns','complete_cycle_ns'):
            r,s=result()
            for row in r['rows']:
                if row['arm']!='candidate':continue
                if field=='status' and row['lane']=='default_fixed_entry_external_qa_tcp':
                    for v in row['calls']:
                        if v['kind']=='status':v['complete_ns']=20_000_000
                elif field in row:row[field]*=2
            self.assertFalse(c.evaluate(r,s)['passed'],field)

    def test_child_receives_independent_argv_pin_not_only_sidecar_claim(self):
        folder=Path(tempfile.gettempdir())/'source-guard-cost-unit'
        script=folder/'wrapper.py';config=folder/'config.json';proxy=c.PinnedSubprocess(script,config,'a'*64)
        args=['python','-I','-B',str(script),'owned-child']
        self.assertEqual(proxy.command(args)[-4:],['--configuration',str(config),'--configuration-sha256','a'*64])
        self.assertEqual(proxy.command(['python','other.py']),['python','other.py'])
        with self.assertRaises(ValueError):proxy.command([*args,'--configuration','wrong'])

    def test_strict_config_data_rejects_duplicate_or_nonfinite(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            for text in ('{"schema":1,"schema":2}','{"a":NaN}'):
                path.write_text(text)
                with self.assertRaises(ValueError):c.load(path)

    def test_config_pins_fixed125_roles_dependencies_and_frozen_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();binary=root/'fake-binary';binary.write_bytes(b'unit fixture')
            gate=root/'gate.json';gate.write_text(json.dumps(dict(schema='source-guard-cost-gates-v1',pairs=8,hot_per_kind=3,
                baseline_source_sha256=c.BASELINE,baseline_source_file_count=125)))
            config=dict(schema='source-guard-cost-config-v1',workspace=str(root),
                python=dict(path=str(binary),sha256=c.sha(binary)),blender=dict(path=str(binary),sha256=c.sha(binary)),
                harness_sha256='a'*64,gate_file=str(gate),gate_sha256=c.sha(gate),arms={})
            for name,source in [('old',c.BASELINE),('candidate','b'*64)]:
                release=root/name;entry=release/'admin/target_runtime_entry.py';entry.parent.mkdir(parents=True);entry.write_text('# unit\n')
                receipt=entry.with_name('RUNTIME_BINDING.json');receipt.write_text(json.dumps(dict(kind='human_eye_fixed_target_runtime',
                    target_release=str(release),site_packages=str(release/'site-packages'),dependency_python=str(binary),launcher_sha256=c.sha(entry),
                    identity=dict(source_sha256=source),source_files=[{}]*125)))
                config['arms'][name]=dict(release=str(release),entry=str(entry),entry_sha256=c.sha(entry),binding_sha256=c.sha(receipt),source_sha256=source,source_file_count=125)
            self.assertEqual(c.validate_config(config),config)
            for mutate in (lambda v:v['arms']['old'].update(source_file_count=78),lambda v:v['arms']['old'].update(source_sha256='c'*64),
                    lambda v:v['arms']['candidate'].update(source_sha256=c.BASELINE),lambda v:v['python'].update(sha256='a'*64),
                    lambda v:v.update(gate_sha256='b'*64),lambda v:v['arms']['candidate'].update(binding_sha256='a'*64)):
                changed=copy.deepcopy(config);mutate(changed)
                with self.assertRaises(ValueError):c.validate_config(changed)

    def test_changed_config_rejects_before_any_subprocess_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json';path.write_text('{}');original=c.sha(path);path.write_text('{"changed":true}')
            with patch.object(c.subprocess,'Popen') as popen,patch.object(c.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'external_config_pin'):
                    c.main(['run','--configuration',str(path),'--configuration-sha256',original,'--output',folder])
                popen.assert_not_called();run.assert_not_called()


if __name__=='__main__':unittest.main()
