"""Execute the exact engine source snapshot bound by a trusted entry.

Only the two engine packages and declared root modules are intercepted. The
fixed Python/Blender interpreter, standard library and third-party extensions
remain trusted external dependencies; this is not a Python sandbox.
"""
from __future__ import annotations
import hashlib,importlib.abc,importlib.util,json,sys,types
from pathlib import Path,PurePosixPath
from types import MappingProxyType
import re

try:
    from nt import _getfinalpathname as _native_final_path
except ImportError:
    _native_final_path = None

PROTOCOL='human-eye-verified-source-v1'
LIMIT=4*1024*1024

_PLAIN_DRIVE_PATH = re.compile(r'[A-Za-z]:\\[^\\/:*?"<>|\x00-\x1f\x7f-\x9f]+(?:\\[^\\/:*?"<>|\x00-\x1f\x7f-\x9f]+)*')
_RESERVED_NAMES = frozenset({'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} |
    {prefix + suffix for prefix in ('COM', 'LPT') for suffix in '123456789\xb9\xb2\xb3'})


class SourceBindingError(ValueError):pass


def _ordinary_source_path(raw):
    if type(raw) is not str or len(raw) >= 240:
        return False
    if _PLAIN_DRIVE_PATH.fullmatch(raw) is None:
        return False
    try:
        if len(raw.encode('utf-16-le')) >= 480:
            return False
    except UnicodeEncodeError:
        return False
    return all(part[-1] not in '. ' and
               part.partition('.')[0].rstrip(' ').upper() not in _RESERVED_NAMES
               for part in raw[3:].split('\\'))


def _resolve_source_origin(path):
    """Resolve a fresh ordinary origin for comparison, retaining old fallbacks."""
    if _native_final_path is not None and _ordinary_source_path(path):
        try:
            canonical = _native_final_path(path)
        except (OSError, ValueError):
            return Path(path).resolve()
        if (type(canonical) is str and canonical.startswith('\\\\?\\')
                and _ordinary_source_path(canonical[4:])):
            return Path(canonical[4:])
    return Path(path).resolve()


def _read(path):
    with path.open('rb') as stream:blob=stream.read(LIMIT+1)
    if len(blob)>LIMIT:raise SourceBindingError('verified_source_byte_budget')
    return blob


def capture(root,manifest):
    root=Path(root)
    if not root.is_absolute() or root.resolve()!=root:raise SourceBindingError('verified_source_root')
    if type(manifest) is not list or not 1<=len(manifest)<=512:raise SourceBindingError('verified_source_manifest')
    sources={}
    for row in manifest:
        if type(row) is not dict or set(row)!={'path','sha256'}:raise SourceBindingError('verified_source_manifest')
        relative=row['path']
        if type(relative) is not str:raise SourceBindingError('verified_source_path')
        part=PurePosixPath(relative)
        if (part.as_posix()!=relative or part.is_absolute() or '\\' in relative
                or any(v in ('','..','.') or ':' in v for v in part.parts) or not relative.endswith('.py')
                or relative in sources):raise SourceBindingError('verified_source_path')
        path=root/relative
        if path.resolve()!=path or not path.is_file():raise SourceBindingError('verified_source_path')
        blob=_read(path)
        if hashlib.sha256(blob).hexdigest()!=row['sha256']:raise SourceBindingError('verified_source_changed:'+relative)
        sources[relative]=blob
    return MappingProxyType(sources)


def current_guard(root=None):
    for finder in sys.meta_path:
        if getattr(finder,'protocol',None)==PROTOCOL and (root is None or finder.root==Path(root).resolve()):return finder
    return None


class _SourceLoader(importlib.abc.Loader):
    def __init__(self,guard,relative):self.guard=guard;self.relative=relative
    def create_module(self,spec):return None
    def exec_module(self,module):self.guard.exec_path(module,self.guard.root/self.relative)


class SourceGuard(importlib.abc.MetaPathFinder):
    protocol=PROTOCOL
    def __init__(self,root,sources):
        self.root=Path(root);self.sources=MappingProxyType(dict(sources));self._executed={};self._namespaces={};self._mapping={}
        for relative in self.sources:
            parts=PurePosixPath(relative).parts
            if len(parts)==1:fullname=parts[0][:-3]
            elif len(parts)==2 and parts[0] in ('human_eye_plugin','human_eye_module1_operators'):
                fullname=parts[0] if parts[1]=='__init__.py' else parts[0]+'.'+parts[1][:-3]
            else:raise SourceBindingError('verified_source_layout')
            self._mapping[fullname]=relative
    def _owned_name(self,name):
        return name in self._mapping or name in ('human_eye_plugin','human_eye_module1_operators') or name.startswith(('human_eye_plugin.','human_eye_module1_operators.'))
    def find_spec(self,fullname,path=None,target=None):
        if not self._owned_name(fullname):return None
        relative=self._mapping.get(fullname)
        if relative is None:raise SourceBindingError('verified_source_unlisted_module:'+fullname)
        source=self.root/relative;package=relative.endswith('/__init__.py')
        return importlib.util.spec_from_file_location(fullname,source,loader=_SourceLoader(self,relative),
            submodule_search_locations=[str(source.parent)] if package else None)
    def exec_path(self,module,path,*,expected_blob=None):
        path=Path(path)
        if path.resolve()!=path or not path.is_relative_to(self.root):raise SourceBindingError('verified_source_path')
        relative=path.relative_to(self.root).as_posix();blob=self.sources.get(relative)
        if blob is None:raise SourceBindingError('verified_source_unlisted_path:'+relative)
        if _read(path)!=blob or expected_blob is not None and expected_blob!=blob:raise SourceBindingError('verified_source_changed:'+relative)
        # Attest before execution: a module may inspect its binding while its
        # top-level code is still running. Remove the witness after an error.
        self._executed[id(module)]=(module,relative)
        try:exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)
        except BaseException:self._executed.pop(id(module),None);raise
    def allow_namespace(self,module):
        if getattr(module,'__file__',None) is not None or module.__name__ not in ('human_eye_plugin','human_eye_module1_operators'):
            raise SourceBindingError('verified_source_namespace')
        if list(getattr(module,'__path__',[]))!=[str(self.root/module.__name__)]:raise SourceBindingError('verified_source_namespace')
        self._namespaces[id(module)]=module
    def verify_loaded(self):
        for name,module in list(sys.modules.items()):
            path=getattr(module,'__file__',None)
            owned=self._owned_name(name);namespace=self._namespaces.get(id(module)) is module
            # Owned non-namespace names always require an execution witness;
            # origin classification cannot exempt them. Keep the final fresh
            # origin resolution below, without resolving twice for classification.
            # Unknown names and namespaces retain their original path checks.
            if not owned or namespace:
                internal=path is not None and Path(path).is_absolute() and _resolve_source_origin(path).is_relative_to(self.root)
                if not owned and not internal:continue
            if namespace:continue
            witness=self._executed.get(id(module))
            if witness is None or witness[0] is not module or path is None or _resolve_source_origin(path)!=self.root/witness[1]:
                raise SourceBindingError('verified_source_preloaded_module:'+name)
        return True


def install(root,manifest,*,sources=None,bootstrap_module=None):
    root=Path(root);frozen=capture(root,manifest) if sources is None else sources
    # A caller supplying a pre-read snapshot must still bind every byte to the
    # externally checked manifest; it cannot inject a second source payload.
    if {r['path']:r['sha256'] for r in manifest}!={name:hashlib.sha256(blob).hexdigest() for name,blob in frozen.items()}:
        raise SourceBindingError('verified_source_manifest')
    existing=current_guard(root)
    if existing is not None:
        if dict(existing.sources)!=dict(frozen):raise SourceBindingError('verified_source_generation_changed')
        existing.verify_loaded();return existing
    guard=SourceGuard(root,frozen)
    if bootstrap_module is not None:
        relative='human_eye_plugin/verified_source_loader.py'
        if Path(bootstrap_module.__file__).resolve()!=root/relative:raise SourceBindingError('verified_source_bootstrap')
        guard._executed[id(bootstrap_module)]=(bootstrap_module,relative)
    guard.verify_loaded();sys.meta_path.insert(0,guard);return guard


def exec_verified(module,path,blob=None):
    """Same-byte path imports, including lightweight Blender-only aliases."""
    path=Path(path).resolve();guard=current_guard(path.parents[1])
    if guard is not None:return guard.exec_path(module,path,expected_blob=blob)
    raw=_read(path) if blob is None else blob
    # Uncontrolled SDK/development imports get same-byte compilation, but do
    # not acquire an external manifest witness or claim a trusted entry.
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)


def worker_expression(root,worker,manifest):
    """Blender argv bootstrap: hash/freeze source before executing any worker."""
    root=Path(root).resolve();worker=Path(worker).resolve();sources=capture(root,manifest)
    relative=worker.relative_to(root).as_posix()
    if relative not in sources:raise SourceBindingError('verified_source_worker_not_listed')
    helper='human_eye_plugin/verified_source_loader.py'
    if helper not in sources:raise SourceBindingError('verified_source_loader_not_listed')
    pin=hashlib.sha256(sources[helper]).hexdigest()
    return '\n'.join(['import sys,types,hashlib,json','from pathlib import Path',
        '_root=Path('+repr(str(root))+')','_path=_root/'+repr(helper),'_blob=_path.read_bytes()',
        'if len(_blob)>4194304 or hashlib.sha256(_blob).hexdigest()!='+repr(pin)+": raise ValueError('verified_source_worker_loader_pin')",
        "_helper=types.ModuleType('_human_eye_verified_source_bootstrap');_helper.__file__=str(_path)",
        "sys.modules[_helper.__name__]=_helper;exec(compile(_blob,str(_path),'exec',dont_inherit=True),_helper.__dict__)",
        '_guard=_helper.install(_root,json.loads('+repr(json.dumps(manifest,separators=(',',':')))+'),bootstrap_module=_helper)',
        "_main=types.ModuleType('__main__');_main.__file__="+repr(str(worker)),"sys.modules['__main__']=_main",
        '_guard.exec_path(_main,Path('+repr(str(worker))+'))'])


def worker_arguments(root,worker):
    from .runtime_identity import runtime_identity,check_source_drift
    if check_source_drift()['compatible'] is not True:raise SourceBindingError('verified_source_parent_drift')
    return ['--python-expr',worker_expression(root,worker,runtime_identity()['source_files'])]
