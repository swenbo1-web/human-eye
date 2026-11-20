"""Replay accepted A and ordinary attachments, then check six fresh Python routes."""

import inspect
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BINDINGS, CATALOGUE, ORDER, PIXEL_BASE, V, load_retained, read, save, sha
from admission import registered_products
from budget import LIMITS


previous = load_retained('_dense_raster_recovered_preflight', PIXEL_BASE / 'harness/preflight.py')
previous.HERE = HERE


def replay_accepted_baseline(original):
    """Use the unchanged protocol and image checks with the accepted prior B1 slot."""
    registered = "original.root / 'slots/QP'"
    source = inspect.getsource(previous.product)
    if source.count(registered) != 1:
        raise ValueError('retained_dense_product_replay_anchor_changed')
    scope = dict(vars(previous))
    exec(compile(source.replace(registered, "original.root / 'slots/B1'"),
                 str(PIXEL_BASE / 'harness/preflight.py'), 'exec'), scope)
    return scope['product'](original)


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    fresh = previous.fresh_entrypoints()
    pins = {}
    original = previous.Original(PIXEL_BASE,
        'c412558ed01216ffed1dff1634112cb95a2fd70469ca049d86874e5c8ba15a9e',
        '853d1bbde7295110e2a5a7214c40eb59a7cfed5169302e5f94e0c5b96fd6c9ef', pins)
    native = previous.Original(V / 'm4_dense_panel_sweep_formal_001',
        '77aa19ccde90e13c790de13370755f4a6bce76075651e6d91dd583b03ceb463b',
        '31c389c0815507a2a71c01073e99f9f445758e0d4f3afb2409bd3672fecd0dbf', pins)
    products = registered_products()
    for path in BINDINGS.values():
        sys.path.insert(0, read(path)['dependency_root'])
        previous.require(read(path.with_name('TOOLS_SCHEMA.json')) == read(CATALOGUE), 'candidate_tools_changed')
    request, response, dense_receipt = replay_accepted_baseline(original)
    native_receipt = previous.ordinary(native)
    mcp = original.root / 'slots/B1/mcp'
    handshake = [original.json(mcp / 'rpc_01/RESPONSE.json'), None, original.json(mcp / 'rpc_03/RESPONSE.json')]
    previous.require(handshake[0]['result']['_meta']['human_eye']['source_sha256'] == products['A']['source_sha256'],
                     'accepted_dense_original_identity_changed')
    with TemporaryDirectory(prefix='m4_dense_raster_cross_preflight_') as directory:
        routes = [previous.dispatch(label, Path(directory) / label, request, response, handshake) for label in ORDER]
    for name in ('harness/common.py', 'harness/admission.py', 'harness/budget.py', 'harness/run_slot.py',
                 'harness/preflight.py', 'run_sequence.py'):
        path = (PIXEL_BASE / name).resolve()
        pins[path] = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
    save(HERE / 'DISPATCH_PREFLIGHT_RECOVERY.json', {
        'passed': all(row['passed'] for row in routes), 'slots': routes,
        'fresh_isolated_entrypoints': fresh,
        'retained_product': dense_receipt, 'retained_common_ordinary_attach': native_receipt,
        'retained_product_slot': 'B1 of M4-GLOBAL-PIXEL-BOUND-SHORT-CIRCUIT-001',
        'MCP_product_instrumentation': False,
        'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
        'products': products, 'ledger_limits': LIMITS, 'source_pins': list(pins.values()),
    })
    print('Replayed six inert routes and two real sealed transmissions; no Blender, raster or model launched.', flush=True)


if __name__ == '__main__':
    main()
