"""Independent byte-prefix, serial, source-path and window association oracle."""

import hashlib
import json
from pathlib import Path


def require(value, reason):
    if not value:
        raise ValueError(reason)


def records(raw):
    require(type(raw) is bytes, 'index_original_bytes_required')
    require(not raw or raw.endswith(b'\n'), 'index_complete_line_boundary')
    result = [json.loads(line) for line in raw.splitlines() if line.strip()]
    serials = [row['index'] for row in result]
    require(all(type(value) is int and value > 0 for value in serials), 'service_serial_positive_integer')
    require(all(left < right for left, right in zip(serials, serials[1:])), 'service_serial_not_strictly_increasing')
    return result


def transition(before, after, started_ns, closed_ns, response_is_error, archive_root):
    """Read an already closed capture; production correlate_archive is unused."""
    require(type(started_ns) is int and type(closed_ns) is int and started_ns <= closed_ns,
            'public_call_window_invalid')
    require(type(response_is_error) is bool, 'original_MCP_error_boolean_required')
    previous = records(before)
    require(type(after) is bytes and after.startswith(before), 'previous_archive_prefix_changed')
    complete = records(after)
    appended = complete[len(previous):]
    require(len(appended) <= 1, 'multiple_service_records_in_one_public_call')
    if not appended:
        require(after == before and response_is_error, 'successful_public_reply_missing_service_record')
        return {'service_archive_index': None, 'new_service_records': 0,
                'archive_prefix_preserved': True, 'original_MCP_error': True}
    entry = appended[0]
    expected = (Path(archive_root) / ('call_' + str(entry['index']).zfill(3)) / 'SERVICE_RESULT.json').resolve()
    require(Path(entry['path']).resolve() == expected, 'archive_entry_cross_slot_or_noncanonical_path')
    require(type(entry.get('started_ns')) is int and type(entry.get('producer_returned_ns')) is int
            and started_ns <= entry['started_ns'] <= entry['producer_returned_ns'] <= closed_ns,
            'service_record_outside_original_public_window')
    digest = hashlib.sha256(expected.read_bytes()).hexdigest()
    require(type(entry.get('sha256')) is str and entry['sha256'] == digest, 'archive_payload_content_SHA_changed')
    return {'service_archive_index': entry['index'], 'new_service_records': 1,
            'archive_prefix_preserved': True, 'archive_payload_path': str(expected),
            'archive_payload_sha256': digest, 'original_MCP_error': response_is_error,
            'independent_service_serial': True}
