"""Archive/restart contract fixtures; no human approval or physical proof."""
import copy,json,os,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from human_eye_plugin.task_episode_archive import EpisodeArchive,_digest,_sealed,NAMES
from human_eye_plugin.task_episode import TaskEpisode
from verification import test_task_episode as episode_fixtures


class EpisodeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.archive=EpisodeArchive(self.root)

    def fixture(self,request_id=7):
        helper=episode_fixtures.TaskEpisodeTests();seed=helper.seed
        def seeded(*args,**kwargs):
            e=seed(*args,**kwargs)
            helper.packet=dict(capture=dict(host_identity=copy.deepcopy(helper.scope['host_identity']),
                                           fixture='contract_not_native_proof'),
                               native_scene=dict(fixture='contract_not_native_proof',vertices=[]))
            helper.packet['capture_confirmation']=copy.deepcopy(helper.packet['capture'])
            helper.scope.update(initial_capture_sha256=_digest(helper.packet['capture']),
                                initial_native_sha256=_digest(helper.packet['native_scene']))
            return e
        helper.seed=seeded;e=helper.accepted()
        if request_id!=7:
            # Different transport events preserve the same explicit fixture.
            e=TaskEpisode('connection-fixture',request_id,helper.arguments,100.)
            e.proposed(helper.task);e.bind(helper.resolved,helper.scope,'form-1');e.response(helper.response,'accept_true')
            helper.admission['event_id']=e.intake()['event_id'];e.admitted(helper.admission);e.execution_started()
        return helper,e

    def complete(self,request_id=7,archive=None):
        archive=archive or self.archive;f,e=self.fixture(request_id)
        slot=archive.begin(e.intake());archive.bind_source(slot,f.resolved,f.scope,f.packet)
        episode=e.finish(f.result,101.);receipt=archive.finish(slot,episode)
        return slot,episode,receipt

    def test_restart_reads_terminal_and_source_but_cannot_restore_writer(self):
        slot,episode,_=self.complete();fresh=EpisodeArchive(self.root);state=fresh.recover()
        self.assertEqual(state['terminal_records'],1);self.assertEqual(state['unknown_records'],0)
        self.assertEqual(state['rows'][0]['recorded_new_setter_count'],4)
        self.assertTrue(state['rows'][0]['source_verified']);self.assertFalse(state['execution_authority'])
        with self.assertRaisesRegex(ValueError,'original_live_writer'):fresh.finish(slot,episode)
        with self.assertRaises(ValueError):fresh.finish({'index':0},episode)
        self.assertFalse(state['retry_authorized']);self.assertIsNone(state['independent_support_count'])

    def test_intake_only_crash_stays_unknown_instead_of_zero(self):
        _,e=self.fixture();self.archive.begin(e.intake());state=EpisodeArchive(self.root).recover()
        self.assertEqual(state['unknown_records'],1)
        self.assertIsNone(state['rows'][0]['recorded_new_setter_count'])
        self.assertEqual(state['terminal_records'],0);self.assertEqual(state['training_positives'],0)

    def test_source_only_crash_retains_source_without_claiming_execution_result(self):
        f,e=self.fixture();slot=self.archive.begin(e.intake());self.archive.bind_source(slot,f.resolved,f.scope,f.packet)
        state=EpisodeArchive(self.root).recover();row=state['rows'][0]
        self.assertTrue(row['source_verified']);self.assertEqual(row['status'],'unknown')
        self.assertIsNone(row['recorded_new_setter_count']);self.assertEqual(state['uncertain_task_records'],1)

    def test_completed_unknown_receipt_is_not_removed_from_uncertainty_denominator(self):
        f,e=self.fixture();slot=self.archive.begin(e.intake());self.archive.bind_source(slot,f.resolved,f.scope,f.packet)
        f.result.update(status='review_required',task_succeeded=False,physical_task_succeeded=None,new_setter_count=None)
        episode=e.finish(f.result,101.);self.archive.finish(slot,episode);state=self.archive.recover()
        self.assertEqual(state['terminal_records'],1);self.assertEqual(state['uncertain_task_records'],1)
        self.assertEqual(state['recorded_outcomes'],{'unknown':1})
        self.assertIsNone(state['rows'][0]['recorded_new_setter_count'])

    def test_missing_source_disqualifies_even_a_saved_success(self):
        self.complete();(self.root/'slot-00/source.json').unlink();state=self.archive.recover()
        self.assertEqual(state['unknown_records'],1);self.assertEqual(state['terminal_records'],0)
        self.assertIsNone(state['rows'][0]['recorded_new_setter_count'])

    def test_modified_source_with_rehashed_envelope_still_fails_original_snapshot_binding(self):
        self.complete();path=self.root/'slot-00/source.json';doc=json.loads(path.read_bytes())
        doc['packet']['native_scene']['vertices']=[[1,2,3]];doc.pop('sha256')
        doc['sha256']=_digest(doc);path.write_text(json.dumps(doc),encoding='utf8')
        state=self.archive.recover();self.assertEqual(state['unknown_records'],1)
        self.assertEqual(state['rows'][0]['reason'],'archive_source_snapshot_mismatch')

    def test_corrupt_or_oversized_terminal_never_becomes_success(self):
        for raw in (b'{broken',b'x'*(1024*1024+16385)):
            with self.subTest(bytes=len(raw)):
                if not (self.root/'slot-00').exists():self.complete()
                (self.root/'slot-00/final.json').write_bytes(raw)
                self.assertEqual(self.archive.recover()['unknown_records'],1)

    def test_two_copies_of_one_event_are_conflicting_not_independent_records(self):
        self.complete();copydir=self.root/'slot-01';copydir.mkdir()
        for name in NAMES:(copydir/name).write_bytes((self.root/'slot-00'/name).read_bytes())
        state=self.archive.recover();self.assertEqual(state['slots_observed'],2)
        self.assertEqual(state['distinct_recorded_events'],1);self.assertEqual(state['unknown_records'],2)
        self.assertTrue(all(row['reason']=='archive_duplicate_event_conflict' for row in state['rows']))

    def test_lifetime_capacity_does_not_reset_on_restart(self):
        archive=EpisodeArchive(self.root,max_slots=2);self.complete(7,archive);self.complete(8,archive)
        fresh=EpisodeArchive(self.root,max_slots=2);_,e=self.fixture(9)
        with self.assertRaisesRegex(ValueError,'capacity'):fresh.begin(e.intake())
        self.assertEqual(fresh.recover()['slots_observed'],2)

    def test_duplicate_event_cannot_allocate_a_new_slot(self):
        self.complete();_,e=self.fixture()
        with self.assertRaisesRegex(ValueError,'already_present'):self.archive.begin(e.intake())
        self.assertEqual(self.archive.recover()['slots_observed'],1)

    def test_concurrent_distinct_events_get_distinct_slots(self):
        intakes=[self.fixture(i)[1].intake() for i in (7,8)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(lambda value:EpisodeArchive(self.root).begin(value),intakes))
        self.assertEqual(len({r.index for r in result}),2)
        self.assertEqual(self.archive.recover()['unknown_records'],2)

    def test_link_publication_then_lost_ack_does_not_allow_writable_recovery(self):
        _,e=self.fixture();link=os.link
        def lost(*args):link(*args);raise OSError('after-publish ACK lost')
        with patch('human_eye_plugin.task_episode_archive.os.link',side_effect=lost):
            with self.assertRaises(OSError):self.archive.begin(e.intake())
        state=EpisodeArchive(self.root).recover();self.assertEqual(state['slots_observed'],1)
        self.assertEqual(state['unknown_records'],1)
        with self.assertRaises(ValueError):EpisodeArchive(self.root).begin(e.intake())

    def test_final_published_then_lost_ack_keeps_historical_receipt(self):
        f,e=self.fixture();slot=self.archive.begin(e.intake());self.archive.bind_source(slot,f.resolved,f.scope,f.packet)
        episode=e.finish(f.result,101.);link=os.link
        def lost(*args):link(*args);raise OSError('after-final ACK lost')
        with patch('human_eye_plugin.task_episode_archive.os.link',side_effect=lost):
            with self.assertRaises(OSError):self.archive.finish(slot,episode)
        state=EpisodeArchive(self.root).recover()
        self.assertEqual(state['terminal_records'],1);self.assertEqual(state['rows'][0]['recorded_new_setter_count'],4)
        self.assertFalse(state['retry_authorized']);self.assertEqual(state['training_positives'],0)

    def test_foreign_root_entries_and_foreign_slot_files_are_not_ignored(self):
        (self.root/'foreign').write_text('unrelated',encoding='utf8')
        with self.assertRaises(ValueError):self.archive.recover()
        (self.root/'foreign').unlink();self.complete();(self.root/'slot-00/unrelated').write_text('x',encoding='utf8')
        self.assertEqual(self.archive.recover()['unknown_records'],1)

    def test_collection_bounds_refuse_excess_directories_without_unbounded_scan(self):
        with patch.object(Path,'iterdir',return_value=iter([self.root/str(i) for i in range(1000)])) as scan:
            with self.assertRaisesRegex(ValueError,'capacity'):EpisodeArchive(self.root,max_slots=2)
        scan.assert_called_once()

    def test_source_and_final_cannot_be_rebound(self):
        slot,episode,_=self.complete();f,_=self.fixture();before=(self.root/'slot-00/source.json').read_bytes()
        f.packet['native_scene']['vertices']=[[0,0,1]];f.scope['initial_native_sha256']=_digest(f.packet['native_scene'])
        with self.assertRaisesRegex(ValueError,'conflict'):self.archive.bind_source(slot,f.resolved,f.scope,f.packet)
        self.assertEqual((self.root/'slot-00/source.json').read_bytes(),before)
        altered=copy.deepcopy(episode);altered['raw_evidence']['received_monotonic']=1.
        with self.assertRaises(ValueError):self.archive.finish(slot,altered)

    def test_confirmation_is_checked_then_deduplicated_without_losing_its_digest(self):
        self.complete();doc=json.loads((self.root/'slot-00/source.json').read_bytes())
        self.assertNotIn('capture_confirmation',doc['packet'])
        self.assertEqual(doc['packet']['capture_confirmation_sha256'],_digest(doc['packet']['capture']))
        f,e=self.fixture(8);slot=self.archive.begin(e.intake());f.packet['capture_confirmation']['fixture']='changed'
        with self.assertRaisesRegex(ValueError,'confirmation_changed'):
            self.archive.bind_source(slot,f.resolved,f.scope,f.packet)


if __name__=='__main__':unittest.main()
