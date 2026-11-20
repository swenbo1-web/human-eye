"""Reconcile archived packet costs without altering the frozen first reader."""

import json
from pathlib import Path
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS))
import costs
from common import ORDER, read, save, sha


def main():
    raw_reader = NS / 'costs.py'
    first = NS / 'RESOURCE_REVIEW.json'
    token = costs.verify_freeze(NS / 'FROZEN.json')
    original = read(first)
    if original['freeze_sha256'] != token or any(
        [(error['stage'], error['message']) for error in row['cost_issues']] != [
            ('public_and_task_audit', "'actual_TX_path'")] for row in original['rows']):
        raise ValueError('unexpected_first_cost_reader_result')
    raw_lines = costs.lines

    def bind_current_packet(path):
        rows = raw_lines(path)
        if path.name != 'PUBLIC_REQUESTS.jsonl':
            return rows
        resolved = []
        for row in rows:
            receipt = row['receipt']
            folder = path.parent / 'mcp' / f"rpc_{receipt['index']:02d}"
            tx, rx = folder / 'TX.bin', folder / 'RX.bin'
            if (tx.stat().st_size != receipt['TX_bytes'] or rx.stat().st_size != receipt['RX_bytes']
                    or sha(rx) != receipt['RX_sha256'] or read(tx) != row['request'] or read(rx) != row['response']
                    or read(folder / 'RECEIPT.json') != receipt or receipt['id'] != row['id'] or
                    row['request'].get('id') != row['response'].get('id')):
                raise ValueError('archived_client_wire_or_receipt_do_not_bind_to_public_request')
            resolved.append({**row, 'actual_TX_path': str(tx), 'actual_TX_sha256': sha(tx),
                             'actual_RX_path': str(rx), 'actual_RX_sha256': sha(rx),
                             'producer_archive_index': (row.get('producer_archive') or {}).get('index')})
        return resolved

    costs.lines = bind_current_packet
    rows = [costs.summarize(label, token) for label in ORDER]
    save(NS / 'RESOURCE_RECHECK.json', {**original, 'rows': rows, 'first_resource_review_sha256': sha(first),
        'first_frozen_cost_reader_sha256': sha(raw_reader),
        'replay_adapter': 'Resolve original stdio files from the retained receipt index. Check RX original hash and raw content, '
                          'derive TX hash from actual bytes and reconcile it with the server meter.'})
    print(json.dumps({row['label']: {'issues': row['cost_issues'], 'public_calls': len(row.get('public_packets', []))}
                      for row in rows}), flush=True)


if __name__ == '__main__':
    main()
