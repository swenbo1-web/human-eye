"""Account for the observed formal calls without decoding private CLI events."""

from pathlib import Path
from runpy import run_path
import re


HERE = Path(__file__).resolve().parent
V = HERE.parent
PUBLIC = run_path(str(V/'m4_source_region_score_admission_001/score.py'))
RETAINED = run_path(str(V/'m4_yanyite_bilateral_region_native_001/costs.py'))
BASE = RETAINED['BASE']
RAW_LINES = BASE['lines']
HEADER = re.compile(rb'^\s*\{\s*"perf_ns"\s*:\s*([0-9]+)\s*,\s*"event"\s*:')
USAGE_FIELDS = PUBLIC['USAGE_FIELDS']


def public_timestamps(path):
    with path.open('rb') as source:
        for line in source:
            head = line[:4096]
            match = PUBLIC['PUBLIC_TOOL_HEADER'](head,timed=True)
            if ((match and match.group(1) == b'item.completed')
                    or PUBLIC['MESSAGE_HEADER'].match(head) or PUBLIC['TURN_HEADER'].match(head)):
                yield int(HEADER.match(head)[1])


def lines(path):
    if path.name != 'events.jsonl':
        return RAW_LINES(path)
    if not path.is_file():
        return []
    return [{'perf_ns':timestamp,'event':event} for timestamp,event in
            zip(public_timestamps(path),PUBLIC['public_events'](path),strict=True)]


def counts(value):
    value = value or {}
    return {key:value[key] for key in USAGE_FIELDS if type(value.get(key)) is int and value[key] >= 0}


def usage(folder,consumer,errors):
    timed = [row['event']['usage'] for row in lines(folder/'events.jsonl')
             if row['event']['type'] == 'turn.completed']
    retained = [counts(value) for value in consumer.get('raw_usage_events', [])]
    if timed != retained:
        errors.append('public_timed_and_retained_consumer_usage_not_equal')
    if len(timed) != 1:
        return timed,None
    report = timed[0]
    if set(report) != set(USAGE_FIELDS) or report['cached_input_tokens'] > report['input_tokens']:
        errors.append('single_public_event_missing_consistent_token_counts')
        return timed,None
    return timed,report['input_tokens']+report['output_tokens']


def summarize(slot,freeze):
    BASE['summarize'].__globals__.update(usage=usage,lines=lines)
    BASE['lines'] = lines
    result = RETAINED['summarize'](slot,freeze)
    if result['status'] != 'unrun':
        result['CLI_usage_evidence_scope'] = 'public timed usage and consumer receipt; raw stdout hash only'
    return result
