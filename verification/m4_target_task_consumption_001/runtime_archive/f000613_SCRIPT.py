import ast
import builtins
PUBLIC_IMPORT_ROOTS = frozenset({"numpy", "PIL", "fractions", "shapely", "math", "cmath",
    "collections", "itertools", "functools", "operator", "json", "pathlib", "statistics",
    "decimal", "random", "re", "heapq", "bisect", "array", "copy", "dataclasses",
    "typing", "enum", "time", "hashlib", "struct", "zlib", "base64", "io", "csv",
    "bpy", "mathutils", "bmesh"})

PRIVATE_BUILTINS = frozenset({"globals", "locals", "vars", "eval", "exec", "compile",
                             "breakpoint", "input", "help"})

def validate_code(code):
    """Apply this experiment's common public-input and reflection boundary."""
    tree = ast.parse(code, filename="<consumer-python>", mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise PermissionError("consumer_private_attribute:" + node.attr)
        if isinstance(node, ast.Name) and (node.id in PRIVATE_BUILTINS or node.id == "__builtins__"):
            raise PermissionError("consumer_private_reflection:" + node.id)
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [node.module.split(".", 1)[0]] if node.module and not node.level else [""]
            if any(alias.name.startswith("_") for alias in node.names):
                raise PermissionError("consumer_private_import_attribute")
        else:
            roots = []
        if any(root not in PUBLIC_IMPORT_ROOTS for root in roots):
            raise PermissionError("consumer_module_outside_public_input_scope")
    return tree

def public_getattr(value, name, *default):
    if type(name) is not str or name.startswith("_"):
        raise PermissionError("consumer_private_dynamic_attribute")
    return builtins.getattr(value, name, *default)

def public_hasattr(value, name):
    try:
        public_getattr(value, name)
    except AttributeError:
        return False
    return True

def public_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".", 1)[0] not in PUBLIC_IMPORT_ROOTS:
        raise PermissionError("consumer_module_outside_public_input_scope")
    fromlist = () if fromlist is None else fromlist
    if any(type(item) is not str or item.startswith("_") for item in fromlist):
        raise PermissionError("consumer_private_import_attribute")
    return builtins.__import__(name, globals, locals, fromlist, level)

def public_builtins():
    values = dict(builtins.__dict__)
    for name in PRIVATE_BUILTINS:
        values.pop(name, None)
    values.update(getattr=public_getattr, hasattr=public_hasattr, __import__=public_import)
    return values

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
_install_task_audit(_audit_json.loads('{"scratch": "D:\\\\he_m4_target_consume_001\\\\formal\\\\P1\\\\blender_scratch", "source_asset": "D:\\\\he_m4_target_consume_001\\\\formal\\\\P1\\\\native\\\\input.blend", "product_root": "D:\\\\he_m4_target_002\\\\B\\\\product"}'))
_ordinary_blender_namespace = {'__name__':'__consumer_blender__', '__builtins__':public_builtins(), 'bpy':bpy, 'scratch':_AuditPath('D:\\he_m4_target_consume_001\\formal\\P1\\blender_scratch')}
