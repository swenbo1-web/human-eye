"""Observe the actual installed service with its original byte-forwarding launcher."""

from pathlib import Path
import sys


sys.path.insert(0,str(Path(__file__).resolve().parent))
_source = Path(__file__).resolve().parents[2]/'m4_dense_sweep_integrated_native_pilot_001/harness/mcp_entry.py'
_scope = {**globals(),'__name__':'_retained_yanyite_mcp_entry'}
exec(compile(_source.read_bytes(),str(_source),'exec'),_scope)


if __name__ == '__main__':
    root = _scope['EXTERNAL']/'preflight/ingress'
    config = root/'slots/QP/PRODUCT_CONFIG.json'
    if '--config' in sys.argv and Path(sys.argv[sys.argv.index('--config')+1]).resolve()==config.resolve():
        _scope['EXTERNAL'] = root

        def deny_live(event, args):
            if event in ('socket.connect','subprocess.Popen','os.system','os.spawn','os.exec'):
                raise RuntimeError('offline_ingress_cannot_connect_or_launch_child')

        sys.addaudithook(deny_live)
    raise SystemExit(_scope['main']())
