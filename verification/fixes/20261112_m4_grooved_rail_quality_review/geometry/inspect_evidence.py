import json, hashlib
from pathlib import Path
P=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/runtime/handoff_01/public')
seen=set()
for folder in sorted(P.glob('answer_*')):
    e=json.loads((folder/'tool_evidence.json').read_text('utf-8'))
    print('\nANSWER',folder.name)
    for a in e['owner_attempts']:
        args=a.get('request',{}).get('params',{})
        print('ATTEMPT',a['order'],'ERROR',a['is_error'],'TOOL',args.get('name'))
        code=args.get('arguments',{}).get('code')
        if code:
            h=hashlib.sha256(code.encode()).hexdigest()
            print('CODE_HASH',h)
            if h not in seen: print('CODE',code);seen.add(h)
        for resp in a['responses']:
            for block in resp['value'].get('result',{}).get('content',[]):
                txt=block.get('text','')
                try: data=json.loads(txt)
                except ValueError: print('TEXT',txt);continue
                if data.get('result_kind')=='task_query':
                    print('QUERY_STATUS',data.get('status'),'COVERAGE',data.get('coverage'))
                    for pair in data.get('pairs',[]):
                        print('PAIR',pair.get('candidate_index'),json.dumps(pair.get('facts',{}),ensure_ascii=False))
                else: print('NATIVE',json.dumps(data,ensure_ascii=False))
