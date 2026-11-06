"""Neutral transport/image-budget tests; no actual Blender or task solver."""
import contextlib,hashlib,io,json,socket,struct,sys,tempfile,threading,time,types,unittest,zlib
from pathlib import Path
from unittest.mock import patch
from verification import visual004_native as n

def png(width=8,height=8,*,bad_data=False):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b'not zlib' if bad_data else zlib.compress((b'\x00'+b'\x20\x40\x80'*width)*height)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',raw)+chunk(b'IEND',b'')

class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.ledger=n.ImageLedger(self.root)
    def test_real_png_is_decoded_and_retained_without_claiming_delivery(self):
        raw=png();row=self.ledger.register_external_image(raw,origin='authored unit fixture')
        self.assertTrue(row['pixels_fully_decoded']);self.assertEqual(Path(row['path']).read_bytes(),raw)
        state=self.ledger.status();self.assertEqual(state['reserved_images'],0);self.assertEqual(row['delivery_state'],'not_delivered')
    def test_crc_and_signature_and_incomplete_png_are_rejected(self):
        raw=png()
        for value in (b'fake',raw[:-1],raw[:42]+b'X'+raw[43:]):
            with self.subTest(value=len(value)),self.assertRaises(ValueError):self.ledger.register_external_image(value)
        self.assertEqual(self.ledger.status()['constructions'],[])
    def test_valid_header_crc_with_invalid_compressed_pixels_is_not_accepted(self):
        raw=png(bad_data=True);self.assertEqual(n.png_metadata(raw)['pixels'],64)
        with self.assertRaises((OSError,ValueError)):self.ledger.register_external_image(raw)
        self.assertEqual(self.ledger.status()['constructions'],[])
    def test_duplicate_bytes_are_distinct_constructions(self):
        one=self.ledger.register_external_image(png());two=self.ledger.register_external_image(png())
        self.assertNotEqual(one['image_id'],two['image_id']);self.assertTrue(two['same_bytes_previously_registered'])
        self.assertEqual(len(self.ledger.status()['constructions']),2)
    def test_repeat_display_costs_count_and_pixels_each_time(self):
        image=self.ledger.register_external_image(png(768,768))
        first=self.ledger.reserve_delivery([image['image_id']]*2)
        self.assertEqual(first['pixels'],2*768**2)
        self.ledger.reserve_delivery([image['image_id']]*2)
        with self.assertRaisesRegex(ValueError,'total_pixel_budget'):self.ledger.reserve_delivery([image['image_id']])
        state=self.ledger.status();self.assertEqual(state['reserved_images'],4);self.assertEqual(state['reserved_pixels'],4*768**2)
    def test_small_images_hit_count_budget_independent_of_pixels(self):
        image=self.ledger.register_external_image(png())
        self.ledger.reserve_delivery([image['image_id']]*8)
        with self.assertRaisesRegex(ValueError,'image_count_budget'):self.ledger.reserve_delivery([image['image_id']])
    def test_large_or_skinny_image_is_constructed_but_cannot_be_delivered(self):
        for size in ((1025,32),(64,2048)):
            with self.subTest(size=size):
                image=self.ledger.register_external_image(png(*size))
                with self.assertRaisesRegex(ValueError,'single_image_pixel_budget'):self.ledger.reserve_delivery([image['image_id']])
        self.assertEqual(len(self.ledger.status()['constructions']),2);self.assertEqual(self.ledger.status()['reserved_images'],0)
    def test_tampered_png_cannot_be_reserved(self):
        image=self.ledger.register_external_image(png());Path(image['path']).write_bytes(png(9,9))
        with self.assertRaisesRegex(ValueError,'image_changed'):self.ledger.reserve_delivery([image['image_id']])
        self.assertEqual(self.ledger.status()['reserved_images'],0)
    def test_unknown_delivery_keeps_spent_reservation_and_never_attests_consumption(self):
        image=self.ledger.register_external_image(png());reservation=self.ledger.reserve_delivery([image['image_id']])
        completed=self.ledger.complete_delivery(reservation['reservation_id'],outcome='unknown',host_event_id='authored-transport-failure')
        self.assertIsNone(completed['model_received']);self.assertEqual(self.ledger.status()['reserved_images'],1)
        with self.assertRaisesRegex(ValueError,'duplicate_completion'):
            self.ledger.complete_delivery(reservation['reservation_id'],outcome='shown',host_event_id='same')
    def test_existing_nonwaiting_lock_does_not_change_budget(self):
        image=self.ledger.register_external_image(png());(self.root/'images/ACTIVE').mkdir()
        with self.assertRaises(FileExistsError):self.ledger.reserve_delivery([image['image_id']])
        self.assertEqual(self.ledger.status()['reserved_images'],0)
    def test_limits_cannot_be_reset_on_reopen(self):
        with self.assertRaisesRegex(ValueError,'image_limits_changed'):
            n.ImageLedger(self.root,limits=dict(n.IMAGE_LIMITS,max_images=4))

class NeutralTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_unicode_text_budget_counts_actual_encoded_bytes(self):
        target=n._LimitedText()
        with patch.object(n,'MAX_OUTPUT',5):
            target.write('中')
            with self.assertRaisesRegex(ValueError,'stdout_byte_budget'):target.write('文')
        self.assertEqual(target.getvalue(),'中')
    def test_fragmented_socket_request_is_one_exact_code_request(self):
        a,b=socket.socketpair();self.addCleanup(a.close);self.addCleanup(b.close)
        raw=n.encoded(dict(type='execute_code',params=dict(code="print('neutral')")))
        def sender():
            for piece in (raw[:5],raw[5:17],raw[17:]):b.sendall(piece)
        thread=threading.Thread(target=sender);thread.start()
        result=n._read_request(a,time.perf_counter_ns()+10**9);thread.join()
        self.assertEqual(result,dict(type='execute_code',params=dict(code="print('neutral')")))
    def test_original_deadline_check_rejects_without_launch(self):
        with self.assertRaisesRegex(ValueError,'original_deadline'):
            n.NativeSession.start(blender='missing',asset='missing',workspace=self.root/'future',deadline_ns=time.perf_counter_ns()-1)
        self.assertFalse((self.root/'future').exists())
    def test_new_session_cannot_extend_task_beyond600_seconds(self):
        with self.assertRaisesRegex(ValueError,'maximum_original_window'):
            n.NativeSession.start(blender='missing',asset='missing',workspace=self.root/'future',deadline_ns=time.perf_counter_ns()+601*10**9)
        self.assertFalse((self.root/'future').exists())
    def test_reopen_refuses_expired_or_poisoned_session(self):
        config=dict(deadline_ns=time.perf_counter_ns()-1,helper_sha256=n.sha(n.__file__))
        n.save(self.root/'SESSION.json',config)
        with self.assertRaisesRegex(ValueError,'original_deadline'):n.NativeSession.open(self.root)
        n.save(self.root/'POISONED.json',dict(reason='authored previous transport failure'))
        with self.assertRaisesRegex(ValueError,'session_poisoned'):n.NativeSession.open(self.root)
    def test_reopen_refuses_session_left_by_failed_start(self):
        n.save(self.root/'SESSION.json',dict(deadline_ns=time.perf_counter_ns()+10**9,helper_sha256=n.sha(n.__file__)))
        n.save(self.root/'START_FAILURE.json',dict(reason='authored post-session startup failure'))
        with self.assertRaisesRegex(ValueError,'session_start_failed'):n.NativeSession.open(self.root)
    def test_open_controller_transport_failure_poisons_without_false_reap(self):
        session=n.NativeSession();session.workspace=self.root;session.process=None
        session.config=dict(deadline_ns=time.perf_counter_ns()+10**9)
        with patch.object(session,'_exchange',side_effect=TimeoutError('authored ambiguous transport')):
            with self.assertRaises(TimeoutError):session.run('print(1)')
        self.assertTrue((self.root/'POISONED.json').exists())
        with self.assertRaisesRegex(ValueError,'session_poisoned'):session.run('print(2)')
    def test_native_scanner_includes_pngs_in_images_directory(self):
        folder=self.root/'images';folder.mkdir();(folder/'consumer.png').write_bytes(png())
        rows=n._scan_pngs(self.root);self.assertEqual(len(rows),1)
        self.assertEqual(next(iter(rows.values()))['pixels'],64)
    def test_qa_client_rejects_success_response_after_concurrent_abort(self):
        session=n.NativeSession();session.workspace=self.root;session.process=None
        asset=self.root/'asset.blend';asset.write_bytes(b'authored transport fixture')
        patch_path=self.root/'qa_patch.json';n.save(patch_path,dict(target_name='Object_01',vertices=[dict(index=0,co=[1.,0.,0.])]))
        binding=dict(path=str(patch_path),sha256=n.sha(patch_path))
        session.config=dict(asset=str(asset),asset_copy=str(asset),asset_sha256=n.sha(asset),
            helper_sha256=n.sha(n.__file__),qa_vertex_patch=binding,deadline_ns=time.perf_counter_ns()+10**9)
        def reply_after_abort(*args):
            n.save(self.root/'POISONED.json',dict(reason='authored concurrent coordinator abort'))
            return dict(status='success',result=dict(stage=1,patch_sha256=binding['sha256']))
        with patch.object(session,'_exchange',side_effect=reply_after_abort):
            with self.assertRaisesRegex(ValueError,'session_poisoned'):
                session.qa_advance()
        self.assertTrue((self.root/'QA_ADVANCE_FAILURE.json').exists())
        self.assertFalse((self.root/'QA_ADVANCE_RECEIPT.json').exists())

class AuthoredWorkerTests(unittest.TestCase):
    """Actual RPC/exec loop, fake empty bpy, never an actual Blender process."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.session=None;self.thread=None;self.control_address=None;self.setup_completed=False
        asset=self.root/'input.blend';asset.write_bytes(b'not a Blender asset; transport fixture only')
        self.deadline=time.perf_counter_ns()+20*10**9
        self.config=dict(workspace=str(self.root),asset=str(asset),asset_copy=str(asset),asset_sha256=n.sha(asset),
            deadline_ns=self.deadline,max_calls=4,helper_sha256=n.sha(n.__file__))
        public_image=self.root/'initial.png';public_image.write_bytes(png())
        self.config['protected_public_images']=[dict(path=str(public_image),sha256=n.sha(public_image))]
        n.save(self.root/'CONFIG.json',self.config)
        fake=types.ModuleType('bpy');fake.data=types.SimpleNamespace(objects=[])
        fake.context=types.SimpleNamespace(scene=types.SimpleNamespace(unit_settings=types.SimpleNamespace(scale_length=1),render=types.SimpleNamespace(filepath='source/initial.png')))
        fake.app=types.SimpleNamespace(handlers=types.SimpleNamespace(render_pre=[],render_post=[],render_cancel=[]))
        self.fake=fake
        self.configure_fake(fake)
        self.patch=patch.dict(sys.modules,bpy=fake);self.patch.start();self.addCleanup(self.patch.stop)
        # Own the listening address before publication, parsing, or session
        # construction can fail. Cleanup must not depend on successful setup.
        publisher=n.publish_ready
        def remember_address(path,value,**kwargs):
            if Path(path).name=='READY.json':self.control_address=(value['host'],value['port'])
            return publisher(path,value,**kwargs)
        self.publisher_patch=patch.object(n,'publish_ready',side_effect=remember_address)
        self.publisher_patch.start();self.addCleanup(self.publisher_patch.stop)
        self.errors=[]
        self.worker_finished=threading.Event()
        def run_worker():
            try:n.worker(self.root/'CONFIG.json')
            except BaseException as exc:self.errors.append(exc)
            finally:self.worker_finished.set()
        self.thread=threading.Thread(target=run_worker);self.addCleanup(self.cleanup_worker);self.thread.start()
        ready=self.root/'READY.json'
        while not ready.exists():
            if self.errors:raise self.errors[0]
            n.check(self.deadline);self.worker_finished.wait(.001)
        value=n.load(ready);self.config.update(host=value['host'],port=value['port'],pid=value['pid'])
        n.save(self.root/'SESSION.json',self.config);self.session=n.NativeSession.open(self.root);self.setup_completed=True
    def configure_fake(self,fake):
        pass
    def cleanup_worker(self):
        if self.thread is not None and self.thread.is_alive():
            try:
                if self.session is not None:self.session.close()
                elif self.control_address is not None:
                    with socket.create_connection(self.control_address,timeout=1) as connection:
                        connection.settimeout(1);connection.sendall(n.encoded(dict(type='close')))
                        connection.shutdown(socket.SHUT_WR);connection.recv(4096)
            except (OSError,ValueError):pass
            self.thread.join(timeout=2)
        self.assertTrue(self.thread is None or not self.thread.is_alive())
        if self.setup_completed:self.assertEqual(self.errors,[])
    def test_persistent_plain_bpy_exec_and_exact_BlenderMCP_success_envelope(self):
        one=self.session.run("value=17; print('first')")
        two=self.session.run("print(value + 1)")
        self.assertEqual(one['response'],dict(status='success',result=dict(executed=True,result='first\n')))
        self.assertEqual(two['response'],dict(status='success',result=dict(executed=True,result='18\n')))
        self.assertEqual(two['original_deadline_ns'],self.deadline)
    def test_loaded_default_render_output_is_redirected_to_owned_workspace(self):
        result=self.session.run('print(bpy.context.scene.render.filepath)')
        self.assertEqual(result['response']['result']['result'].strip(),str(self.root/'renders/default.png'))
    def test_public_initial_image_change_is_detected_before_execution(self):
        image=self.root/'initial.png';image.write_bytes(png(9,9))
        result=self.session.run("print('must not execute')")
        self.assertEqual(result['response']['status'],'error')
        self.assertFalse(result['protected_files_unchanged'])
        self.assertFalse((self.root/'call_1/SCRIPT.py').exists())
    def test_script_error_retains_trace_and_can_be_fixed_in_original_window(self):
        failed=self.session.run("print('before'); raise ValueError('authored script failure')")
        self.assertEqual(failed['response']['status'],'error');self.assertIn('authored script failure',failed['response']['error']['traceback'])
        success=self.session.run("print('fixed by new user script')")
        self.assertEqual(success['response']['status'],'success');self.assertEqual(success['original_deadline_ns'],self.deadline)
    def test_terminal_unit_mutation_is_not_reported_as_success(self):
        result=self.session.run('bpy.context.scene.unit_settings.scale_length=2')
        self.assertEqual(result['response']['status'],'error');self.assertTrue(result['response']['poisoned'])
        self.thread.join(timeout=2);self.assertFalse(self.thread.is_alive())
        self.assertTrue(n.load(self.root/'WORKER_CLOSED.json')['poisoned'])
    def test_poison_marker_blocks_direct_RPC_before_script_exec(self):
        n.save(self.root/'POISONED.json',dict(reason='authored timeout at another client'))
        try:result=self.session._exchange(dict(type='execute_code',params=dict(code="print('must not run')")),1)
        except (ConnectionAbortedError,ConnectionResetError,ConnectionRefusedError):pass
        else:
            self.assertEqual(result['status'],'error');self.assertIn('session_poisoned',result['error']['message'])
        self.thread.join(timeout=2);self.assertFalse(self.thread.is_alive())
        self.assertFalse((self.root/'call_1/SCRIPT.py').exists())
    def test_qa_advance_requires_explicit_session_opt_in(self):
        result=self.session._exchange(dict(type='qa_advance',params=dict(patch_sha256='0'*64)),1)
        self.assertEqual(result['status'],'error')
        self.assertIn('qa_patch_not_enabled',result['error']['message'])
        self.assertFalse((self.root/'QA_ADVANCE_ATTEMPT.json').exists())


class PatchVertex:
    def __init__(self,co):
        self._co=list(co)
        self.reject_setter=False
    @property
    def co(self):
        return self._co
    @co.setter
    def co(self,value):
        if self.reject_setter:
            raise RuntimeError('authored second vertex setter failure')
        self._co=list(value)


class QAUpdateWorkerTests(unittest.TestCase):
    """Same real fixture RPC loop with authored mesh objects, no Blender."""
    setUp=AuthoredWorkerTests.setUp
    cleanup_worker=AuthoredWorkerTests.cleanup_worker

    def configure_fake(self,fake):
        self.vertices=[PatchVertex([0.,0.,0.]),PatchVertex([1.,0.,0.])]
        mesh=types.SimpleNamespace(vertices=self.vertices,edges=[],polygons=[],materials=[],update=lambda:None)
        self.target=types.SimpleNamespace(name='Object_01',type='MESH',parent=None,data=mesh,
            matrix_world=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]],
            hide_render=False,hide_viewport=False,hide_get=lambda:False)
        fake.data.objects=[self.target]
        fake.context.view_layer=types.SimpleNamespace(update=lambda:None)
        self.patch_value=dict(target_name='Object_01',vertices=[dict(index=0,co=[2.,0.,0.]),dict(index=1,co=[3.,0.,0.])])
        self.patch_path=self.root/'qa_patch.json'
        n.save(self.patch_path,self.patch_value)
        self.config.update(max_calls=8,qa_vertex_patch=dict(path=str(self.patch_path),sha256=n.sha(self.patch_path)))
        n.save(self.root/'CONFIG.json',self.config,replace=True)

    def test_three_states_keep_namespace_process_and_updated_geometry_guard(self):
        first=self.session.run("cached=17; print(bpy.data.objects[0].data.vertices[0].co[0])")
        again=self.session.run("print(cached, bpy.data.objects[0].data.vertices[0].co[0])")
        receipt=self.session.qa_advance()
        changed=self.session.run("print(cached, bpy.data.objects[0].data.vertices[0].co[0])")
        self.assertEqual(first['response']['result']['result'],'0.0\n')
        self.assertEqual(again['response']['result']['result'],'17 0.0\n')
        self.assertEqual(changed['response']['result']['result'],'17 2.0\n')
        result=receipt['response']['result']
        self.assertEqual(result['stage'],1)
        self.assertEqual(result['vertices_written'],2)
        self.assertNotEqual(result['before_fingerprint'],result['after_fingerprint'])
        self.assertEqual(result['original_fingerprint'],n.load(self.root/'READY.json')['initial_fingerprint'])
        self.assertEqual(receipt['original_deadline_ns'],self.deadline)
        self.assertTrue(self.thread.is_alive())
        self.assertEqual(n.load(self.root/'QA_ADVANCE_RECEIPT.json'),receipt)

    def test_reopened_coordinator_and_direct_RPC_cannot_reapply_patch(self):
        self.session.qa_advance()
        with self.assertRaises(FileExistsError):
            n.NativeSession.open(self.root).qa_advance()
        result=self.session._exchange(dict(type='qa_advance',params=dict(patch_sha256=n.sha(self.patch_path))),1)
        self.assertEqual(result['status'],'error')
        self.assertIn('qa_patch_already_applied',result['error']['message'])
        self.assertEqual([vertex.co for vertex in self.vertices],[[2.,0.,0.],[3.,0.,0.]])

    def test_partial_setter_failure_poisoned_without_replay(self):
        self.vertices[1].reject_setter=True
        with self.assertRaisesRegex(ValueError,'qa_advance_failed'):
            self.session.qa_advance()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual([vertex.co for vertex in self.vertices],[[2.,0.,0.],[1.,0.,0.]])
        self.assertTrue(n.load(self.root/'WORKER_CLOSED.json')['poisoned'])
        self.assertFalse(n.load(self.root/'WORKER_CLOSED.json')['qa_patch_applied'])
        self.assertTrue((self.root/'QA_ADVANCE_ATTEMPT.json').exists())
        self.assertTrue((self.root/'QA_ADVANCE_FAILURE.json').exists())
        with self.assertRaisesRegex(ValueError,'session_poisoned'):
            self.session.qa_advance()

    def test_changed_patch_or_source_is_rejected_before_any_setter(self):
        self.patch_path.write_text(json.dumps(dict(self.patch_value,target_name='changed')),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'qa_patch_source_changed'):
            self.session.qa_advance()
        self.assertEqual([vertex.co for vertex in self.vertices],[[0.,0.,0.],[1.,0.,0.]])
        self.assertFalse((self.root/'QA_ADVANCE_ATTEMPT.json').exists())

    def test_changed_original_asset_is_rejected_before_any_setter(self):
        Path(self.config['asset']).write_bytes(b'authored unexpected source change')
        with self.assertRaisesRegex(ValueError,'qa_patch_source_changed'):
            self.session.qa_advance()
        self.assertEqual([vertex.co for vertex in self.vertices],[[0.,0.,0.],[1.,0.,0.]])
        self.assertFalse((self.root/'QA_ADVANCE_ATTEMPT.json').exists())

    def test_all_indices_are_validated_before_the_first_setter(self):
        bad_patch=dict(self.patch_value,vertices=[dict(index=0,co=[2.,0.,0.]),dict(index=99,co=[3.,0.,0.])])
        with self.assertRaisesRegex(ValueError,'qa_patch_index_range'):
            n._apply_qa_vertex_patch(self.fake,bad_patch)
        self.assertEqual([vertex.co for vertex in self.vertices],[[0.,0.,0.],[1.,0.,0.]])

    def test_unexpected_nonvertex_change_during_update_poisoned(self):
        self.fake.context.view_layer.update=lambda:setattr(self.fake.context.scene.unit_settings,'scale_length',2)
        with self.assertRaisesRegex(ValueError,'qa_advance_failed'):
            self.session.qa_advance()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(n.load(self.root/'WORKER_CLOSED.json')['poisoned'])
        self.assertFalse(n.load(self.root/'WORKER_CLOSED.json')['qa_patch_applied'])

    def test_concurrent_abort_during_update_cannot_commit_current_fingerprint(self):
        self.fake.context.view_layer.update=lambda:n.save(self.root/'POISONED.json',dict(reason='authored QA update abort'))
        with self.assertRaisesRegex(ValueError,'qa_advance_failed'):
            self.session.qa_advance()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        closed=n.load(self.root/'WORKER_CLOSED.json')
        self.assertTrue(closed['poisoned'])
        self.assertFalse(closed['qa_patch_applied'])
        self.assertEqual(closed['accepted_geometry_fingerprint'],closed['initial_geometry_fingerprint'])
        self.assertTrue((self.root/'QA_ADVANCE_FAILURE.json').exists())

    def test_consumer_mutation_after_advance_still_poisons(self):
        self.session.qa_advance()
        result=self.session.run('bpy.data.objects[0].data.vertices[0].co=[9.,0.,0.]')
        self.assertEqual(result['response']['status'],'error')
        self.assertTrue(result['response']['poisoned'])
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())


class QAPatchValidationTests(unittest.TestCase):
    def test_schema_coordinates_and_unique_indices_are_validated_without_setters(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'patch.json'
            valid=dict(target_name='Object_01',vertices=[dict(index=0,co=[.065,0.,0.])])
            invalid=[dict(valid,extra=True),dict(valid,vertices=[]),
                dict(valid,vertices=[dict(index=True,co=[0.,0.,0.])]),
                dict(valid,vertices=[dict(index=0,co=[float('nan'),0.,0.])]),
                dict(valid,vertices=[dict(index=0,co=[1e300,0.,0.])]),
                dict(valid,vertices=[valid['vertices'][0],valid['vertices'][0]])]
            for value in invalid:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value),encoding='utf8')
                    with self.assertRaises(ValueError):n._load_qa_vertex_patch(path)
            path.write_text(json.dumps(valid),encoding='utf8')
            patch,digest=n._load_qa_vertex_patch(path)
            expected=struct.unpack('f',struct.pack('f',.065))[0]
            self.assertEqual(patch['vertices'][0]['co'],[expected,0.,0.])
            self.assertEqual(digest,n.sha(path))

    def test_changed_file_hash_is_rejected_before_patch_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'patch.json'
            path.write_text('not JSON',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'qa_patch_source_changed'):
                n._load_qa_vertex_patch(path,'0'*64)

class FixtureCleanupTests(unittest.TestCase):
    def test_worker_start_publication_and_socket_errors_stop_owned_watchdog(self):
        def reject_watchdog_start(thread,*args,**kwargs):
            if thread.name.startswith('visual004-watchdog-'):raise failure
            return original_start(thread,*args,**kwargs)
        for stage in ('watchdog_start','publication','socket'):
            with self.subTest(stage=stage):
                before={thread.ident for thread in threading.enumerate()};failure=OSError('authored worker '+stage+' failure')
                original_start=threading.Thread.start
                intervention=(patch.object(n.threading.Thread,'start',new=reject_watchdog_start) if stage=='watchdog_start' else
                    patch.object(n,'publish_ready',side_effect=failure) if stage=='publication' else patch.object(n.socket,'socket',side_effect=failure))
                case=AuthoredWorkerTests('test_persistent_plain_bpy_exec_and_exact_BlenderMCP_success_envelope')
                with intervention:
                    try:
                        with self.assertRaises(OSError) as caught:case.setUp()
                    finally:self.assertTrue(case.doCleanups())
                self.assertIs(caught.exception,failure);self.assertEqual(case.errors,[failure]);self.assertFalse(case.thread.is_alive())
                self.assertFalse(any(t.ident not in before and t.name.startswith('visual004-watchdog-') for t in threading.enumerate()))

    def test_setup_read_failure_closes_worker_before_or_during_session_creation(self):
        for filename in ('READY.json','SESSION.json'):
            with self.subTest(filename=filename):
                before={thread.ident for thread in threading.enumerate()};original=n.load
                case=AuthoredWorkerTests('test_persistent_plain_bpy_exec_and_exact_BlenderMCP_success_envelope')
                def fail_selected_read(path):
                    if Path(path).name==filename:raise ValueError('authored setup read failure '+filename)
                    return original(path)
                with patch.object(n,'load',side_effect=fail_selected_read):
                    try:
                        with self.assertRaisesRegex(ValueError,'authored setup read failure'):case.setUp()
                    finally:self.assertTrue(case.doCleanups())
                self.assertFalse(case.thread.is_alive());self.assertEqual(case.errors,[])
                self.assertFalse(any(t.ident not in before and t.name.startswith('visual004-watchdog-') for t in threading.enumerate()))

if __name__=='__main__':unittest.main()
