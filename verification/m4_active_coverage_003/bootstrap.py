"""Explicit dependency site plus runpy, with shared lazy import verification."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SITE = Path('D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Lib/site-packages')
BASELINE = ROOT / 'verification/m4_active_coverage_001'
CORE = BASELINE / 'coverage.py'
ADAPTER = BASELINE / 'render/adapter.py'
BASELINE_SHA256 = {CORE: '2561ecaf2f2df98ec7c03ed48cb95dd08c34f10ce73c1e9ecc2e32f31c41daf4',
                   ADAPTER: 'df7e207ebd38c2876c54683e29899fccbe23187a4dd544cde1fcd9ed6ace82cd'}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install_old_evidence_audit(trace):
    evidence = {'installed_before_dynamic_imports': True, 'allowed_source_reads': [],
                'forbidden_old_evidence_reads': 0, 'old_evidence_read_attempts': [],
                'forbidden_old_writes': 0, 'old_write_attempts': []}

    def hook(event, arguments):
        if event != 'open' or not isinstance(arguments[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(arguments[0])).resolve()
        if not path.is_relative_to(BASELINE.resolve()):
            return
        mode, flags = arguments[1], arguments[2]
        writing = (isinstance(mode, str) and any(character in mode for character in 'wax+'))
        writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        record = {'path': str(path), 'mode': mode, 'flags': flags}
        if writing:
            evidence['forbidden_old_writes'] += 1
            evidence['old_write_attempts'].append(record)
            trace.emit('forbidden_old_write', durable=True, **record)
            raise PermissionError('old_active_coverage_tree_write_forbidden')
        source = path in BASELINE_SHA256
        cache = ((path.parent == BASELINE / '__pycache__' and path.name.startswith('coverage.'))
                 or (path.parent == BASELINE / 'render/__pycache__' and path.name.startswith('adapter.')))
        if source or cache and path.suffix == '.pyc':
            evidence['allowed_source_reads'].append(record)
            trace.emit('allowed_baseline_source_read', **record)
            return
        evidence['forbidden_old_evidence_reads'] += 1
        evidence['old_evidence_read_attempts'].append(record)
        trace.emit('forbidden_old_evidence_read', durable=True, **record)
        raise PermissionError('old_active_coverage_evidence_read_forbidden')

    sys.addaudithook(hook)
    return evidence


def load_dependencies():
    """Probe and runtime call this same function after installing their audit."""
    launch = load('_active003_shared_launch_contract', HERE / 'launch.py')
    contract = launch.describe()
    actual_executable = Path(sys.executable).resolve()
    if actual_executable != Path(contract['base_executable']).resolve() or sha(actual_executable) != contract['base_executable_sha256']:
        raise ValueError('actual_base_interpreter_binding')
    for path, wanted in BASELINE_SHA256.items():
        if sha(path) != wanted:
            raise ValueError('frozen_baseline_source_changed:' + str(path))
    core = load('_active003_fixed_geometry', CORE)
    adapter = load('_active003_fixed_raster', ADAPTER)
    import numpy
    import PIL
    observed = {}
    for name, module in (('numpy', numpy), ('pillow', PIL)):
        path = Path(module.__file__).resolve()
        value = {'path': str(path), 'version': module.__version__, 'init_sha256': sha(path)}
        if not path.is_relative_to(SITE.resolve()) or value != contract['expected_dependencies'][name]:
            raise ValueError('actual_original_dependency_binding:' + name)
        observed[name] = value
    product = adapter.dependency_binding()
    install = Path(contract['product_install_root']).resolve()
    if product['source_sha256'] != '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6' or product['source_count'] != 138:
        raise ValueError('fixed_product_identity')
    if not all(Path(row['path']).resolve().is_relative_to(install) for row in product['loaded_product_modules'].values()):
        raise ValueError('actual_product_import_location')
    environment = {'bootstrap_path': str(Path(__file__).resolve()), 'bootstrap_sha256': sha(__file__),
        'launch_path': str((HERE / 'launch.py').resolve()), 'launch_sha256': sha(HERE / 'launch.py'),
        'base_executable': contract['base_executable'], 'base_executable_sha256': contract['base_executable_sha256'],
        'python_executable': str(actual_executable), 'process_id': os.getpid(),
        'sys_prefix': sys.prefix, 'sys_base_prefix': sys.base_prefix,
        'sys_exec_prefix': sys.exec_prefix, 'sys_base_exec_prefix': sys.base_exec_prefix,
        'explicit_site_packages': str(SITE.resolve()), 'sys_path': list(sys.path),
        'numpy': observed['numpy'], 'pillow': observed['pillow'],
        'product_install_root': str(install), 'product_binding': product,
        'baseline_sources_sha256': {str(path.resolve()): wanted for path, wanted in BASELINE_SHA256.items()},
        'dependency_manifest_path': contract['dependency_manifest_path'],
        'dependency_manifest_sha256': contract['dependency_manifest_sha256']}
    return core, adapter, environment


def main():
    target = str(Path(sys.argv[1]).resolve())
    sys.path.insert(0, str(SITE))
    sys.argv = [target, *sys.argv[2:]]
    runpy.run_path(target, run_name='__main__', init_globals={
        'ACTIVE003_LOAD_DEPENDENCIES': load_dependencies,
        'ACTIVE003_INSTALL_OLD_AUDIT': install_old_evidence_audit})


if __name__ == '__main__':
    main()
