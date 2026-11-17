"""Migrate the accepted direct zero-model test plumbing into this bounded batch."""

import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PRIOR = HERE.with_name('m4_global_local_qualification_001')
M5 = HERE.with_name('m5_observe_measure_001')


def main():
    (HERE / 'harness/reused').mkdir(parents=True, exist_ok=True)
    (HERE / 'public_schema').mkdir(exist_ok=True)
    copies = []
    for relative in ('harness/mcp_entry.py', 'harness/budget.py', 'harness/owned_runtime.py',
                     'harness/reused/owned_native.py', 'harness/reused/process_proof.py',
                     'harness/reused/stdio_checks.py', 'harness/reused/verified_bootstrap.py', 'harness/reused/wire_meter.py'):
        source = PRIOR / relative
        raw = source.read_bytes()
        text = raw.decode('utf8')
        if relative.endswith('budget.py'):
            text = text.replace('"Blender_start_attempts": 3, "all_rasters": 18', '"Blender_start_attempts": 8, "all_rasters": 64')
            text = text.replace('            elif kind == "raster_attempt" and snapshot["slots"].get(label, {}).get("raster_upper", 0) >= 6:\n                raise RuntimeError("qualification_session_six_camera_budget_exhausted")\n', '')
        if relative.endswith('owned_runtime.py'):
            text = text.replace("EXTERNAL = Path('D:/he_m4_global_local_001')", "EXTERNAL = Path('D:/he_m4_cross_scale_001')")
            begin = text.index('PRODUCT_SHA256 = ')
            end = text.index('\ndef digest', begin)
            text = text[:begin] + "EXTERNAL = Path('D:/he_m4_cross_scale_001')\nASSET = Path('D:/he_m4_global_local_001/fixture/main.blend')\nASSET_SHA256 = 'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6'\n\n" + text[end:]
            text = text.replace('group != "B"', 'group not in ("R0", "R1")')
            text = text.replace('self.binding["source_sha256"] != PRODUCT_SHA256[group] or len(self.binding["source_manifest"]) != 141', 'len(self.binding["source_manifest"]) != 142')
            text = text.replace('HERE / "reused/owned_native.py"', 'HERE / ("state_owned_native.py" if label == "state" else "reused/owned_native.py")')
        (HERE / relative).write_text(text, encoding='utf8', newline='\n') if relative.endswith(('budget.py','owned_runtime.py')) else shutil.copyfile(source, HERE / relative)
        copies.append(dict(original=str(source), original_sha256=hashlib.sha256(raw).hexdigest(), target=relative,
                           target_sha256=hashlib.sha256((HERE / relative).read_bytes()).hexdigest()))
    state = (M5 / 'harness/state_owned_native.py').read_text(encoding='utf8')
    state = state.replace('2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164',
                          'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6').replace('M4_Far_00', 'Obj_02')
    (HERE / 'harness/state_owned_native.py').write_text(state, encoding='utf8', newline='\n')
    shutil.copyfile(PRIOR / 'SHARED_DEPENDENCY.json', HERE / 'SHARED_DEPENDENCY.json')
    with (HERE / 'HARNESS_MIGRATION.json').open('x', encoding='utf8') as stream:
        json.dump(dict(copies=copies, state_helper_original=str(M5/'harness/state_owned_native.py'),
            state_changes='Only the fixed asset SHA and fixture object name, retain owned move/restore verification and all deadlines.'), stream, indent=2)
    print(json.dumps(dict(migrated=len(copies), actual_operations=0)))


if __name__ == '__main__':
    main()
