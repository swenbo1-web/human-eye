"""Add the established M2 wire meter to the frozen pose fixture explicitly."""
from __future__ import annotations

import difflib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, ROOT, WORKER, save, sha


def main():
    original = WORKER / 'pose_native.py'
    target = HERE / 'pose_native_metered.py'
    original_raw = original.read_bytes()
    source = original_raw.decode('utf8')
    replacements = [
        ("    initial=_scene_fingerprint(bpy);current=initial;qa_advanced=False",
         "    import importlib.util\n"
         "    meter_spec=importlib.util.spec_from_file_location('_scan_wire_meter',Path(__file__).with_name('wire_meter.py'))\n"
         "    meter=importlib.util.module_from_spec(meter_spec);meter_spec.loader.exec_module(meter)\n"
         "    initial=_scene_fingerprint(bpy);current=initial;qa_advanced=False"),
        ("                connection,_=server.accept()\n                with connection:",
         "                connection,_=server.accept()\n"
         "                connection=meter.WireSocket(connection,sequence+1)\n                with connection:"),
        ("                    try:\n                        need(not (workspace/'POISONED.json').exists(),'session_poisoned')",
         "                    m2_before=[]\n                    try:\n"
         "                        m2_before=meter.host_work()\n"
         "                        need(not (workspace/'POISONED.json').exists(),'session_poisoned')"),
        ("                    finally:\n                        event['elapsed_ns']",
         "                    finally:\n                        event['m2_work']=meter.finish_rpc(m2_before,namespace)\n"
         "                        event['elapsed_ns']"),
        ("    save(workspace/'WORKER_CLOSED.json',closed)",
         "    meter.flush(workspace)\n    save(workspace/'WORKER_CLOSED.json',closed)"),
    ]
    for before, after in replacements:
        assert source.count(before) == 1, before
        source = source.replace(before, after, 1)
    compile(source, str(target), 'exec', dont_inherit=True)
    with target.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(source)
    meter_source = ROOT / 'verification/m2_tight_directory_001/measurement/wire_meter.py'
    meter_target = HERE / 'wire_meter.py'
    with meter_target.open('xb') as stream:
        stream.write(meter_source.read_bytes())
    difference = ''.join(difflib.unified_diff(original_raw.decode().splitlines(True),
        source.splitlines(True), fromfile=str(original), tofile=str(target)))
    with (HERE / 'METERED_HELPER.diff').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(difference)
    save(HERE / 'METERED_HELPER_PROVENANCE.json', {
        'original': str(original), 'original_sha256': sha(original),
        'derived': str(target), 'derived_sha256': sha(target),
        'meter_original': str(meter_source), 'meter_sha256': sha(meter_source),
        'meter_copy_unchanged': sha(meter_target) == sha(meter_source),
        'replacements': len(replacements), 'diff_sha256': sha(HERE / 'METERED_HELPER.diff'),
        'pose_patch_unchanged': True, 'deadline_and_lifecycle_unchanged': True,
        'product_calls': 0, 'Blender_starts': 0})


if __name__ == '__main__':
    main()
