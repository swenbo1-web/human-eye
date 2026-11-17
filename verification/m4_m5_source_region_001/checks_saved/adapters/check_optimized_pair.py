"""Add actual R1 cold/warm payload instrumentation review to local source checks."""

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_local_pair

saved = check_local_pair.check_saved
ORIGINAL_CHECK_SESSION = saved.check_session


def optimized_session(session, run_binding, call_index=1, translated=False):
    result = ORIGINAL_CHECK_SESSION(session, run_binding, call_index, translated)
    session = Path(session).resolve()
    audit = saved.Audit()
    audit.file(__file__)
    calls = [json.loads(line) for line in audit.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    record = calls[call_index - 1]['producer_archive']
    full = audit.read(record['path'], record['sha256'], session)
    work = full['work']
    wanted_payload = int(call_index == 1)
    audit.check(work['fresh_payload_reuses'] == wanted_payload and work['frame_array_decodes'] == 0,
                'actual_R1_cold_warm_fresh_payload_and_array_decode_counters')
    generation = full['generation_work']
    audit.check(generation['fresh_payload_reuses'] == 1 and generation['frame_array_decodes'] == 0,
                'actual_R1_retained_generation_payload_counters')
    if call_index == 2:
        audit.check(work['frame_reuses'] == 1, 'actual_R1_warm_frame_reuse_counter')
    frame = full['frames'][0]
    transient = frame['temporary_encoded_archive_bytes']
    private = frame['stages']['private_encoded_archive']
    audit.check(transient > 0 and private['retained_encoded_payload_bytes'] == 0,
                'actual_R1_private_encoded_archive_transient_scope')
    result['actual_optimized_payload_review'] = dict(cold=call_index == 1,
        fresh_payload_reuses=work['fresh_payload_reuses'], frame_array_decodes=work['frame_array_decodes'],
        frame_reuses=work['frame_reuses'], temporary_encoded_archive_bytes=transient,
        generation_fresh_payload_reuses=generation['fresh_payload_reuses'],
        generation_frame_array_decodes=generation['frame_array_decodes'],
        private_encoded_archive_stage=private, counters_scope='actual producer work instrumentation',
        baseline_decode_count_scope='One R0F decode is derived from its frozen successful validation source path. It was not instrumented in that run.')
    result['checks'].extend(audit.checks)
    result['input_pins'].extend(audit.pins.values())
    return result


if __name__ == '__main__':
    saved.check_session = optimized_session
    check_local_pair.main()
