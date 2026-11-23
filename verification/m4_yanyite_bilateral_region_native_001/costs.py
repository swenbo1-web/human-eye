"""Account for original bilateral CLI events, tools, image transfer and close."""

from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
PILOT = HERE.parent/'perf050_readonly_product_pilot_001/consumer/costs.py'
CURVED = HERE.parent/'m4_yanyite_dual_curved_region_native_001/costs.py'
BASE = run_path(str(PILOT))
CAPTURE = run_path(str(CURVED))


def summarize(slot, freeze):
    report = BASE['summarize'](slot, freeze)
    if report['status'] == 'unrun':
        return report
    original = BASE['read'](slot/'consumer/CONSUMER.json')
    source = BASE['read'](slot/'SLOT_RESULT.json')
    public = BASE['lines'](slot/'consumer/events.jsonl')
    image = next((item for item in report['actual_requests'] if item['CLI_received_ns'] is not None and
                  item['CLI_delivered_images']), None)
    elapsed = BASE['elapsed']
    report['clock_ms'].update(
        prompt_to_first_original_image=elapsed(original.get('prompt_submitted_ns'), image['CLI_received_ns'] if image else None),
        tool_wire_RTT_sum=sum(item['tool_wire_RTT_ms'] for item in report['actual_requests'] if item['tool_wire_RTT_ms'] is not None),
        owner_service_sum=sum(item['owner_window_ms'] for item in report['actual_requests'] if item['owner_window_ms'] is not None),
    )
    report['prompt_to_first_original_image_attempt'] = image['attempt'] if image else None
    usage = original.get('usage') or {}
    tokens = [usage.get(k) for k in ('input_tokens', 'cached_input_tokens', 'output_tokens')]
    if all(type(x) is int and x >= 0 for x in tokens):
        total, cached, output = tokens
        if cached > total or report['input_plus_output_tokens'] != total + output:
            report['cost_review_errors'].append('raw_cache_and_CLI_usage_not_consistent')
        report['usage'] = {'input': total, 'cached_input': cached, 'output': output,
                           'input_output': total + output, 'input_minus_cache_plus_output': total - cached + output}
    else:
        report['usage'] = None
    report['turn_failures'] = [{'perf_ns': row['perf_ns'], 'error': row['event'].get('error')}
                               for row in public if row['event']['type'] == 'turn.failed']
    report['public_timed_text_bytes'] = sum(len(piece['text'].encode('utf8')) for row in public
        if row['event']['type'] == 'item.completed' and row['event'].get('item', {}).get('type') == 'mcp_tool_call'
        for piece in ((row['event']['item'].get('result') or {}).get('content') or []) if piece['type'] == 'text')
    if not original.get('valid_completion'):
        for key in ('prompt_to_final', 'last_tool_to_final', 'final_to_publish'):
            report['clock_ms'][key] = None
    report['source_integrity'] = source.get('independent_before_after')
    report['closure'] = source.get('closure_verification')
    report['product_native_transport'] = CAPTURE['transport'](slot)
    report['product_service'] = CAPTURE['product_calls'](slot)
    report['cost_evidence_verified'] = not report['cost_review_errors']
    return report
