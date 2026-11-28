"""Freeze only structured facts stated by the two historical natural task prompts."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess

PLAN = '6f4baec050d258f8f934dfdb23350610c132a53ffc00047c7ed1068d4a08ea28'
LABELS = '03f11dae6aff1428cff5e751c959900a6be1ddaed5d6d29c05290519e991b39e'
ORIGINS = {
    'rail': ('m4_rail_source_region_product_native_001','a374e3dcde0334991a63c15d594604c068b0b614',
             '367973a31f51bc429be4f3ad121c49a18b5056273befc29d7c07a030fc7c659d'),
    'assembly': ('m4_assembly_cross_asset_product_native_001','4bc6b7d6da32a4204f57465f4311723e0836faff',
                 '66df13ff1348bf9153d6e399664879cd42c86c339cee5e6787357ac335d66f98'),
}
TOPIC = re.compile(r'([A-Z][0-9]+) 的选区闭盒最小角为 \(([^)]*)\)，最大角为 \(([^)]*)\)，参照 ([A-Z][0-9]+) 整件。')


def need(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return sha256(raw).hexdigest()


def pin(path):
    return {'path':str(path.resolve(strict=True)),'bytes':path.stat().st_size,'sha256':sha(path.read_bytes())}


def triplet(value):
    result=[float(c.strip().replace('−','-')) for c in value.split(',')]
    need(len(result)==3 and all(math.isfinite(c) for c in result),'prompt_not_finite_world_triplet')
    return result


def freeze(root, repo, previous):
    preflight=root/'preflight'
    need(sha((preflight/'ADMIN_PLAN.md').read_bytes())==PLAN,'wrong_admin_plan')
    need(sha(previous.read_bytes())==LABELS,'wrong_prior_frozen_labels')
    labels=json.loads(previous.read_bytes())
    topics,source_prompts={},{}
    for asset,(namespace,commit,wanted) in ORIGINS.items():
        def blob(file):
            return subprocess.check_output(['git','-C',str(repo),'show',
                                            f'{commit}:verification/{namespace}/{file}'])
        prompt=blob('inputs/PROMPT.txt')
        attestation=json.loads(blob('FROZEN.json'))['prompt']
        need(sha(prompt)==wanted==attestation['sha256'] and len(prompt)==attestation['bytes'],
             'historical_natural_prompt_bytes_changed')
        text=prompt.decode('utf8')
        need('世界坐标以米计。' in text and '三个顶点都在对应闭盒内' in text and '包含边界' in text,
             'natural_prompt_coordinate_or_closed_box_policy_missing')
        match=TOPIC.findall(text)
        need(len(match)==2,'natural_prompt_expected_two_groups')
        p=preflight/f'PROMPT_{asset.upper()}.txt'
        with p.open('xb') as fp:
            fp.write(prompt)
        source_prompts[asset]={'commit':commit,**pin(p)}
        for target,lower,upper,reference in match:
            need(target not in topics,'duplicate_target')
            box={'min':triplet(lower),'max':triplet(upper)}
            need(all(a<=b for a,b in zip(box['min'],box['max'],strict=True)),'invalid_closed_box')
            evidence=labels['tasks'][target]
            need((evidence['asset'],evidence['target'],evidence['reference'],evidence['world_box_m'])==
                 (asset,target,reference,box),'natural_prompt_does_not_match_prior_scoring_domain')
            topics[target]={'asset':asset,'target':target,'reference':reference,'world_box_m':box}
    need(list(topics)==labels['task_order'],'frozen_order_mismatch')
    with (preflight/'TASK_INPUTS.json').open('x',encoding='utf8',newline='\n') as out:
        json.dump({'passed':True,'task_order':list(topics),'tasks':topics,'assets':labels['assets'],
                   'prior_labels':pin(previous),'prompts':source_prompts,'admin_plan_sha256':PLAN},
                  out,ensure_ascii=False,sort_keys=True,indent=2)
        out.write('\n')
    print(pin(preflight/'TASK_INPUTS.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('repo',type=Path)
    p.add_argument('prior_labels',type=Path)
    a=p.parse_args()
    freeze(a.root,a.repo,a.prior_labels)
