"""Ordinary Blender task-scope audit, outside the product implementation."""

import ast
import json
from pathlib import Path


def installation_script(scratch, source_asset, product_root):
    settings = json.dumps({"scratch": str(scratch), "source_asset": str(source_asset),
                           "product_root": str(product_root)}, ensure_ascii=True)
    source = Path(__file__).with_name("native_tools.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {"PUBLIC_IMPORT_ROOTS", "PRIVATE_BUILTINS", "validate_code", "public_getattr",
             "public_hasattr", "public_import", "public_builtins"}
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append(ast.get_source_segment(source, node))
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in names for target in node.targets):
            selected.append(ast.get_source_segment(source, node))
    guard = "import ast\nimport builtins\n" + "\n\n".join(selected) + "\n"
    return guard + """
import sys as _audit_sys
import json as _audit_json
from pathlib import Path as _AuditPath
_consumer_scope_state = {'running': False}
def _install_task_audit(_settings):
    _scratch = _AuditPath(_settings['scratch']).resolve()
    _source = _AuditPath(_settings['source_asset']).resolve()
    _product = _AuditPath(_settings['product_root']).resolve()
    _blender_root = _AuditPath(_audit_sys.executable).resolve().parent
    _python_roots = tuple(_AuditPath(p).resolve() for p in _audit_sys.path if p and
        _AuditPath(p).resolve().is_relative_to(_blender_root))
    def _audit(event, arguments):
        if not _consumer_scope_state['running']:
            return
        if event in ('subprocess.Popen','os.system','os.posix_spawn','socket.connect',
                     'socket.bind','socket.__new__','ctypes.dlopen'):
            print('NATIVE_TASK_AUDIT_DENIED', event)
            raise PermissionError('task_network_subprocess_or_native_library_forbidden')
        if event == 'exec':
            filename = _AuditPath(arguments[0].co_filename)
            if filename.is_absolute() and filename.resolve().is_relative_to(_product):
                print('NATIVE_TASK_AUDIT_DENIED', event, str(filename))
                raise PermissionError('task_uses_registered_product_tools')
            return
        if event not in ('open','os.listdir','os.scandir') or not arguments:
            return
        value = arguments[0]
        if not isinstance(value, (str, bytes)):
            return
        path = _AuditPath(value.decode() if isinstance(value,bytes) else value).resolve()
        mode = arguments[1] if event == 'open' and len(arguments)>1 else 'r'
        flags = arguments[2] if event == 'open' and len(arguments)>2 else 0
        writing = (isinstance(mode,str) and any(c in mode for c in 'wax+')) or bool(flags & 0x703)
        allowed = path.is_relative_to(_scratch) or not writing and (
            path == _source or any(path.is_relative_to(root) for root in _python_roots))
        if not allowed:
            print('NATIVE_TASK_AUDIT_DENIED',event,str(path))
            raise PermissionError('task_private_input_or_outside_scratch_write_forbidden')
    _audit_sys.addaudithook(_audit)
_install_task_audit(_audit_json.loads(""" + repr(settings) + "))\n" + (
        "_ordinary_blender_namespace = {'__name__':'__consumer_blender__', '__builtins__':public_builtins(), "
        "'bpy':bpy, 'scratch':_AuditPath(" + repr(str(scratch)) + ")}\n")


def wrap(code):
    return ("validate_code(" + repr(code) + ")\n_consumer_scope_state['running'] = True\n"
            "try:\n    exec(compile(" + repr(code) + ", '<ordinary-blender-task>', 'exec'), _ordinary_blender_namespace)\n"
            "finally:\n    _consumer_scope_state['running'] = False\n")
