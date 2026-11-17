"""Reuse the accepted root-held caller with public-reference handoff and expected stale errors."""

from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    prior=HERE.with_name('m4_cross_scale_discovery_001')/'harness/run_slot.py'
    text=prior.read_text(encoding='utf8').replace('D:/he_m4_cross_scale_001','D:/he_m4_m5_source_region_001')
    text=text.replace('import base64\n','import base64\nimport copy\n')
    text=text.replace('def request(runtime,arguments,label,folder,deadline):','def request(runtime,arguments,label,folder,deadline,expected_error=False):')
    text=text.replace("    if 'error' in response or response.get('result',{}).get('isError') is True:\n        raise RuntimeError('original_public_error_preserved')\n    return record",
        "    is_error = 'error' in response or response.get('result',{}).get('isError') is True\n"
        "    if is_error != expected_error:\n        raise RuntimeError('unexpected_public_error_or_success_preserved')\n"
        "    record['expected_error'] = expected_error\n"
        "    record['public_result'] = None if is_error else json.loads(next(block['text'] for block in response['result']['content'] if block['type']=='text'))\n"
        "    return record")
    text=text.replace("        labels=sequence['state_order'] if label=='state' else ['main']", "        labels=sequence['state_order'] if label=='state' else sequence['main_order']\n        initial_ref = None")
    text=text.replace("if stage=='moved':", "if stage=='moved_old':")
    text=text.replace("if stage=='restored':", "if stage=='restored_old':")
    text=text.replace("            result['requests'].append(request(runtime,sequence['requests'][stage],stage,folder,deadline))",
        "            arguments = copy.deepcopy(sequence['requests'][stage])\n"
        "            if stage in sequence['use_initial_public_region_ref']:\n"
        "                if initial_ref is None:\n                    raise ValueError('original_public_region_ref_unavailable')\n"
        "                del arguments['query']['region']\n                arguments['query']['region_ref'] = copy.deepcopy(initial_ref)\n"
        "            completed = request(runtime,arguments,stage,folder,deadline,stage in sequence['expected_error_stages'])\n"
        "            result['requests'].append(completed)\n"
        "            if stage == 'initial':\n                initial_ref = copy.deepcopy(completed['public_result']['region_ref'])")
    (HERE/'harness/run_slot.py').write_text(text,encoding='utf8',newline='\n')


if __name__=='__main__':
    main()
