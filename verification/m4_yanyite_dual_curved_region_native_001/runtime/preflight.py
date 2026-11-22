"""Prove the actual cold imports, owner, thin stdio and held, installed P endpoint."""

from pathlib import Path
import sys
import time
from types import SimpleNamespace

import admission
from bridge import Owner, PRODUCT_TOOL, TOOLS
from common import (ASSET, BLENDER, CATALOGUE, CLI, CLI_SHA, EXTERNAL, FORMAL, GENERIC_WORKER, HERE, NATIVE,
                    NS, PRIOR, PRODUCT_BINDING, PRODUCT_SCHEMA, PYTHON_SHA, SEAL, V, read, save, sha)
from consumer import consumer_adapter
from diagnostic import INIT, LIST, NOTIFY, body
from frame_device import FrameDevice
from runtime import Runtime, transport


def prove():
    origin = EXTERNAL/'preflight'
    private = origin/'ingress'
    private.mkdir(parents=True,exist_ok=False)
    if (EXTERNAL/'slots').exists() or sha(CLI)!=CLI_SHA or sha(sys.executable)!=PYTHON_SHA:
        raise ValueError('true_ingress_preflight_requires_fixed_tools_and_empty_real_slots')
    binding = read(PRODUCT_BINDING)
    require = admission.require
    require(admission.registered_product()['source_sha256']==binding['source_sha256'],'wrong_fixed_install')
    _,consumer_proof,_ = consumer_adapter()
    require((consumer_proof['CLI_version'],consumer_proof['model'],consumer_proof['reasoning_effort'],
             consumer_proof['service_tier'],consumer_proof['completed_CLI_tool_limit'])==
            ('0.152.1','gpt-6.1-sol','medium','default',12),'actual_CLI_config_or_limit_changed')
    require(Path(sys.modules[Owner.__module__].__file__).resolve()==NATIVE/'bridge.py'
            and Path(sys.modules[FrameDevice.__module__].__file__).resolve()==NATIVE/'frame_device.py',
            'actual_owner_or_ordinary_device_import_from_wrong_namespace')
    for cls in Runtime.__mro__:
        init = vars(cls).get('__init__')
        if hasattr(init,'__globals__') and init.__globals__.get('EXTERNAL')==EXTERNAL:
            init.__globals__['EXTERNAL'] = private
    deadline = time.perf_counter_ns()+120_000_000_000
    found = {}
    for label in ('QN','QP'):
        folder = private/'slots'/label
        folder.mkdir(parents=True,exist_ok=False)
        runtime = Runtime(folder,label,deadline,deadline)
        owner = wire = None
        try:
            if label=='QP':
                runtime.native = SimpleNamespace(host='127.0.0.1',port=1)
                runtime._start_public_mcp(PRODUCT_BINDING,binding)
                runtime.native = None
            else:
                require(runtime.product_tools==[],'native_diagnostic_got_product_catalogue')
            endpoint_config = {'label':label,'group':label[-1],'phase':'qualification','worker_deadline_ns':deadline,
                               'output':str(folder/'owner')}
            # Only ordinary computation is invoked here, so this proof never touches a Blender device.
            runtime.cameras = {'views':[]}
            runtime.buffers = {}
            owner = Owner(runtime,endpoint_config,budget=runtime.budget)
            endpoint = owner.start(folder/'ENDPOINT.json')
            wire = transport.StdioClient([sys.executable,'-IB','-X','utf8',str(HERE/'thin_stdio.py'),
                       '--endpoint',str(endpoint),'--audit',str(folder/'attachments')],
                       folder,folder/'ingress_wire',deadline)
            wire.call(INIT)
            wire.call(NOTIFY)
            tools = wire.call(LIST)['result']['tools']
            require([arg for arg in tools if arg['name']!=PRODUCT_TOOL]==TOOLS and tools==owner.tools
                    and len(tools)==len(TOOLS)+(label=='QP'),'actual_common_catalogue_changed')
            def call(ident, name, arguments):
                response = wire.call({'jsonrpc':'2.0','id':ident,'method':'tools/call',
                                      'params':{'name':name,'arguments':arguments}})
                return response
            one = call('session-set','execute_python',{'code':'import numpy as np\nimport shapely\ns=np.arange(9)\nprint(int(s.sum()))'})
            require(body(one)['stdout'].strip()=='36','ordinary_persistent_session_setup_failed')
            denied = call('product-reject',PRODUCT_TOOL,{'include_image':'bad-contract'})
            require(denied['result']['isError'] is True,'invalid_public_product_request_not_rejected')
            two = call('session-get','execute_python',{'code':'print(int(s[2]+s[-1]))'})
            require(body(two)['stdout'].strip()=='10','ordinary_storage_or_rejection_recovery_failed')
            found[label] = {'tools':tools,'actual_product_handshake':label=='QP',
                            'requests_after_handshake':len(wire.records)-3,
                            'public_product_attempts':len(runtime.public_requests),'closed':False}
            require(len(runtime.public_requests)==(label=='QP'),'native_or_plugin_wrong_actual_dispatch_count')
        finally:
            if wire is not None:
                closed = wire.finish()
                require(closed['confirmed'] is True and closed['exit_code']==0,'thin_stdio_preflight_exit_failed')
            if owner is not None:
                require(owner.close()['confirmed'] is True,'owner_preflight_exit_failed')
            runtime.native = None
            actual = runtime.close('preflight')
            require(not actual['errors'],'offline_worker_cleanup_or_retained_process_handle_failed')
            if label=='QP':
                require(actual['public_MCP_close']['production_eof_and_exit_verified'] is True
                        and actual['public_MCP_exit']['confirmed'] is True,'actual_product_eof_or_process_exit_failed')
            meter = runtime.budget.snapshot()['counts']
            require(all(meter[key]==0 for key in ('Blender_start_attempts','consumer_admissions','all_raster_upper')),
                    'actual_preflight_started_Blender_model_or_raster')
        found[label]['closed'] = True
    pins = {ASSET,BLENDER,CLI,Path(sys.executable),PRODUCT_BINDING,PRODUCT_SCHEMA,CATALOGUE,
            GENERIC_WORKER,SEAL/'SHARED_DEPENDENCY.json',FORMAL/'harness/run_slot.py'}
    pins.update(Path(row['path']) for row in consumer_proof['execution_sources'])
    pins.update(Path(mod.__file__).resolve() for mod in tuple(sys.modules.values())
                if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().is_relative_to(V))
    receipt = {'passed':True,'arms':found,'fixed_cli':consumer_proof,
               'new_Blender':0,'new_models':0,'new_rasters':0,
               'source_pins':[{'path':str(path.resolve()),'bytes':path.stat().st_size,'sha256':sha(path)}
                              for path in sorted({p.resolve() for p in pins}) if path.is_file()]}
    save(origin/'RUNTIME_PREFLIGHT.json',receipt)
    print('Actual owned ingress, held installed MCP and thin stdio passed',flush=True)
    return 0
