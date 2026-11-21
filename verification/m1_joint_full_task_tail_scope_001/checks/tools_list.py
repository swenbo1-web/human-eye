"""Compare actual installed stdio tools/list bytes independently of build probes."""

import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory


NS = Path(__file__).resolve().parents[1]
EARLIER = NS.parent / 'm1_pair_distance_entry_001'


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_interpreter_required')
    probe = runpy.run_path(str(EARLIER / 'checks/check.py'))
    packets, receipts = {}, []
    with TemporaryDirectory(prefix='he-joint-tail-catalogue-') as temp:
        for label, root in (('A', NS.parent / 'm1_joint_full_task_tail_001'), ('B', NS)):
            path = root / 'install/PRODUCT_RUN_BINDING.json'
            binding = probe['read'](path)
            folder = Path(temp) / label
            folder.mkdir()
            _, listing, raw = probe['actual_catalogue'](binding, probe['configuration'](folder, binding))
            _, packet = raw.splitlines(keepends=True)
            if json.loads(packet) != listing:
                raise ValueError('catalogue_stdout_not_bound_to_decoded_tool_list')
            packets[label] = packet
            dest = NS / 'evidence' / ('TOOLS_LIST_' + label + '_RX.bin')
            receipts.append({'arm': label, 'file': probe['save_wire'](dest, packet),
                'binding': probe['pin'](path), 'tool_count': len(listing['result']['tools']),
                'runtime_source_sha256': binding['source_sha256']})
    if packets['A'] != packets['B']:
        raise ValueError('public_tools_list_wire_changed')
    with (NS / 'checks/TOOLS_LIST.json').open('x', encoding='utf8', newline='\n') as out:
        json.dump({'passed': True, 'tool_count': 5, 'tools_list_raw_RX_bytes_equal': True,
                   'receipts': receipts, 'new_Blender': 0}, out, ensure_ascii=False, indent=2)
        out.write('\n')


if __name__ == '__main__':
    main()
