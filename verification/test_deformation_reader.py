"""Authored actor exit/close checks; no Blender or source-admission claim."""
import tempfile
from pathlib import Path
import unittest

from human_eye_plugin import deformation_delivery as delivery
from human_eye_plugin import deformation_reader as reader_module
from verification.test_deformation_delivery import Clock, FakeQualifiedReader
from verification.test_deformation_task_view import task_fixture


class AuthoredProcess:
    def __init__(self, pid):
        self.pid=pid
        self.returncode=None

    def poll(self):
        return self.returncode


class AuthoredActor:
    def __init__(self, pid, deadline_ns, exit_code=0, verify_failure=False):
        self.process=AuthoredProcess(pid)
        self.deadline_ns=deadline_ns
        self.exit_code=exit_code
        self.verify_failure=verify_failure
        self.verify_calls=0
        self.sequence=2
        self.closed=False

    def verify_inputs(self):
        self.verify_calls+=1
        if self.verify_failure:
            raise OSError('authored source verification failure')

    def close(self):
        self.closed=True
        self.process.returncode=self.exit_code


def authored_reader(clock, deadline_ns, *, exit_code=0, verify_failure=False):
    """Exercise actual verify_and_close with controlled process exit facts."""
    value=reader_module.QualifiedReader.__new__(reader_module.QualifiedReader)
    value.clock_ns=clock
    value.task_deadline_ns=deadline_ns
    value.started_ns=clock()
    value.actors={
        'source_left':AuthoredActor(101,deadline_ns,exit_code,verify_failure),
        'source_right':AuthoredActor(102,deadline_ns),
    }
    value.closed=False
    value.close_receipt=None
    value.events=[]
    value.costs=dict(physical_inspect_requests=4,logical_directory_reads=2,
                    B2_rows_attempts=2,B2_rows_completed=2,worker_starts=2)
    return value


class ReaderCloseTests(unittest.TestCase):
    def test_zero_exit_is_required_for_successful_verified_close(self):
        clock=Clock();deadline=clock()+30_000_000_000
        value=authored_reader(clock,deadline)
        receipt=value.verify_and_close()
        self.assertTrue(receipt['sources_unchanged'])
        self.assertTrue(receipt['all_owned_closed'])
        self.assertTrue(receipt['original_deadline_preserved'])
        self.assertEqual(receipt['costs']['physical_inspect_requests'],4)
        self.assertEqual(receipt['costs']['B2_rows_passes'],2)
        self.assertTrue(all(actor.closed for actor in value.actors.values()))
        self.assertTrue(all(actor.process.poll()==0 for actor in value.actors.values()))

    def test_nonzero_and_forced_exit_never_produce_successful_close_receipt(self):
        for code in (73,1,-15):
            with self.subTest(code=code):
                clock=Clock();deadline=clock()+30_000_000_000
                value=authored_reader(clock,deadline,exit_code=code)
                with self.assertRaises(ValueError):
                    value.verify_and_close()
                self.assertIsNone(value.close_receipt)
                self.assertTrue(all(actor.closed for actor in value.actors.values()))
                costs=value.snapshot_costs()
                self.assertEqual(costs['worker_processes']['source_left']['exit_code'],code)
                self.assertEqual(costs['physical_inspect_requests'],4)
                self.assertEqual(costs['B2_rows_passes'],2)

    def test_source_verification_failure_still_closes_and_keeps_read_costs(self):
        clock=Clock();deadline=clock()+30_000_000_000
        value=authored_reader(clock,deadline,verify_failure=True)
        with self.assertRaises(ValueError):
            value.verify_and_close()
        self.assertIsNone(value.close_receipt)
        self.assertTrue(all(actor.closed for actor in value.actors.values()))
        costs=value.snapshot_costs()
        self.assertEqual(costs['physical_inspect_requests'],4)
        self.assertEqual(costs['B2_rows_passes'],2)

    def test_failed_process_close_blocks_publication_without_refund_or_retry(self):
        for fault in ('worker_exit','source_verification'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='human-eye-reader-close-') as folder:
                root=Path(folder).resolve()
                self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
                task,frames=task_fixture();clock=Clock();deadline=clock()+30_000_000_000
                backend=authored_reader(clock,deadline,exit_code=73 if fault=='worker_exit' else 0,
                                        verify_failure=fault=='source_verification')
                reader=FakeQualifiedReader(task['spec'],frames,task_deadline_ns=deadline)
                def verified_close():
                    reader.close_calls+=1
                    try:return backend.verify_and_close()
                    finally:
                        reader.closed=backend.closed
                        reader.snapshot_costs['owned_process_closes']=sum(a.closed for a in backend.actors.values())
                reader.verify_and_close=verified_close
                session=delivery.DeliverySession(task['spec'],run_nonce=task['run_nonce'],
                    condition_id=task['condition_id'],deadline_ns=deadline,store=root,reader=reader,
                    prior_usage=dict(directories=2,facts=0,native_supplements=0),clock_ns=clock)
                with self.assertRaises(delivery.DeliveryError):
                    session.request('read-before-close-failure')
                self.assertFalse(session.ledger['published'])
                self.assertFalse(session.ledger['delivered'])
                self.assertFalse(session.ledger['model_received'])
                self.assertEqual(session.ledger['usage']['facts'],2)
                self.assertEqual(session.ledger['usage']['physical_inspect_requests'],4)
                self.assertEqual(session.ledger['usage']['B2_rows_passes'],2)
                self.assertEqual(reader.close_calls,1)
                with self.assertRaisesRegex(delivery.DeliveryError,'terminal_no_retry'):
                    session.request('not-a-fresh-budget')
                self.assertEqual(len(reader.calls),2)


if __name__=='__main__':unittest.main()
