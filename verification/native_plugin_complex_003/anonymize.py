"""Prepare unedited, label-free final texts before any cost conclusion."""
import hashlib,json,random,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
def main():
    out=HERE/'blind';out.mkdir(exist_ok=False);plan=read(HERE/'PLAN.json');rows=[];mapping={}
    for slot in plan['sequence']:
        p=HERE/'cells'/slot['cell']/'CONSUMER.json';data=read(p) if p.exists() else {}
        opaque=uuid.uuid4().hex
        text=data.get('final') or '[No final answer delivered]'
        (out/(opaque+'.txt')).write_text(text,encoding='utf8',newline='\n')
        rows.append({'answer_id':opaque,'text':text,'delivered':bool(data.get('valid_completion'))})
        mapping[opaque]=dict(slot,consumer_sha256=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None)
    random.SystemRandom().shuffle(rows)
    save(out/'ANSWERS.json',{'answers':rows,'scope':'explicit labels/order/cost removed; original method wording may identify tool route'})
    save(out/'RUBRIC.json',{'prompt':(HERE/'PROMPT.txt').read_text(),'criteria':plan['rules'],
        'truth':read(HERE/'private/TRUTH.json')['states']['initial'],
        'gap_acceptance':'abs(answer-d0)+original_E<=1e-6; legitimate unknown remains safe but incomplete',
        'instructions':'Score each semantic criterion independently; preserve omissions/unknown, no guessed missing facts. Do not inspect group map or costs.'})
    save(HERE/'private/BLIND_MAP.json',mapping)
    print(json.dumps({'anonymous_answers':len(rows),'cost_data_included':False}))
if __name__=='__main__':main()
