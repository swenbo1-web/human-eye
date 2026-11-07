"""Record dispatch/collection and close the existing owner; no consumer calls."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=('dispatch', 'close'))
parser.add_argument('sequence', type=int)
parser.add_argument('--status', choices=('completed', 'timed_out', 'failed'), default='completed')
args = parser.parse_args()
path = ROOT/'dispatch/BINDINGS.json'
manifest = json.loads(path.read_text('utf8'))
row = manifest['bindings'][args.sequence-1]
assert row['sequence'] == args.sequence
now = datetime.now(timezone.utc)
chain = ROOT/'chains'/row['chain_id']
if args.action == 'dispatch':
    assert row['status'] == 'planned'
    assert (chain/'READY.json').is_file()
    assert hashlib.sha256(Path(row['prompt_path']).read_bytes()).hexdigest() == row['prompt_sha256']
    if args.sequence > 1:
        prior = manifest['bindings'][args.sequence-2]
        assert prior['status'] in ('closed_completed', 'closed_timed_out', 'closed_failed')
        final = json.loads((ROOT/'chains'/prior['chain_id']/'FINAL.json').read_text('utf8'))
        assert final['worker_exited'] and final['worker_exit_code'] == final['launcher_exit_code'] == 0
        assert not final['forced_cleanup']
    launch = json.loads((ROOT/('owner_'+row['chain_id']+'.LAUNCH.json')).read_text('utf8'))
    row.update(status='dispatched', agent_path='/root/consume_%02d'%args.sequence,
        dispatch_utc=now.isoformat(), answer_deadline_utc=(now+timedelta(seconds=150)).isoformat(),
        chain_started_unix=launch['started_unix'], chain_folder='chains/'+row['chain_id'])
else:
    assert row['status'] == 'dispatched'
    row.update(status='collected_'+args.status, notification_received_utc=now.isoformat())
    (chain/'CLOSE').write_text(now.isoformat()+'\n', encoding='utf8')
    limit = time.monotonic()+40
    while not (chain/'FINAL.json').is_file():
        if time.monotonic() >= limit:
            raise TimeoutError('Owner close result absent; do not launch another chain')
        time.sleep(.05)
    final = json.loads((chain/'FINAL.json').read_text('utf8'))
    assert final['worker_exited'] and final['worker_exit_code'] == final['launcher_exit_code'] == 0
    assert final['watchdog_joined'] and not final['forced_cleanup']
    row.update(status='closed_'+args.status, owner_ended_utc=final['ended_utc'],
        owner_launch_to_reap_seconds=final['launch_to_reap_seconds'])
path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf8')
print(json.dumps(dict(sequence=args.sequence, status=row['status'],
    dispatch_utc=row['dispatch_utc'], answer_deadline_utc=row['answer_deadline_utc'])))
