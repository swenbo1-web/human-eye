"""Seal original fixtures, preflight wires, and owned slots after the trial stops."""

import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


NS = Path(__file__).resolve().parent
ROOT = Path('D:/he_perf050_dense_micro_surface_holdout_001')
FOLDERS = {'runtime': ROOT, **{name:ROOT.with_name(ROOT.name + '_' + name)
           for name in ('fixture', 'transport_preflight', 'transport_preflight_v2', 'product_preflight')}}
PRIVATE_MARKERS = re.compile(rb'(?i)\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{30,}|ghp_[A-Za-z0-9]{36}|'
                             rb'github_pat_[A-Za-z0-9_]{40,}|Bearer [A-Za-z0-9._~-]{24,})\b')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(data):
    return {'bytes':len(data), 'sha256':sha(data)}


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write('\n')


def archive():
    NS.joinpath('evidence').mkdir(exist_ok=True)
    freeze = NS / 'FROZEN.json'
    token = sha(freeze.read_bytes())
    for row in read(freeze)['direct_inputs']:
        assert pin(Path(row['path']).read_bytes()) == {k:row[k] for k in ('bytes','sha256')}, row['path']
    journal = ROOT / 'preflight/FORMAL_SEQUENCE.jsonl'
    sequence = [json.loads(line) for line in journal.read_bytes().splitlines()]
    assert [row['event'] for row in sequence] == ['start','publication','start','publication','formal_not_admitted']
    assert sorted(p.name for p in (ROOT/'slots').iterdir()) == ['QN','QP']
    assert all(row['model_consumers'] == 0 and row['safe_to_continue'] for row in (sequence[1],sequence[3]))
    (NS/'evidence/FORMAL_SEQUENCE.jsonl').write_bytes(journal.read_bytes())
    observed = {}
    for label, status in (('QN','completed'), ('QP','failed')):
        folder = ROOT/'slots'/label
        result, receipt = (read(folder/f'SLOT_{suffix}.json') for suffix in ('RESULT','PUBLICATION'))
        assert result['freeze_sha256']==token and result['status']==receipt['status']==status
        assert receipt['result_sha256']==sha((folder/'SLOT_RESULT.json').read_bytes())
        assert result['model_consumers']==result['paid_API_calls']==0 and result['closure_verification']['passed']
        assert result['independent_before_after']['passed']
        observed[label] = {'status':status,'wall_ms':receipt['complete_slot_ns']/1e6,
            'time_to_ready_ms':(result['ready_ns']-result['started_ns'])/1e6,
            'cleanup_ms':(result['closed_ns']-result['cleanup_started_ns'])/1e6,'business_calls':[]}
        for sub in ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json'):
            (NS/'evidence'/f'{label}_{sub}').write_bytes((folder/sub).read_bytes())
        for row in result['diagnostic_calls']:
            directory = folder/'client'/f'call_{row["index"]:02}'
            raw = (directory/'RESPONSE.json').read_bytes()
            assert sha(raw)==row['response_sha256']
            content = json.loads(raw)['result']['content']
            observed[label]['business_calls'].append({'name':row['name'],'outer_qualification_ms':(row['returned_ns']-row['started_ns'])/1e6,
                'public_text_bytes':sum(len(part['text'].encode()) for part in content if part['type']=='text'),
                'PNG_bytes':[len(base64.b64decode(part['data'],validate=True)) for part in content if part['type']=='image'],
                'RX':pin(raw)})
    for relative in ('preflight/QN_CLOSED_IMAGES.json','slots/QN/QUALIFICATION.json',
                     'slots/QP/product_qualification/discovery_CLI.json'):
        source = ROOT/relative
        (NS/'evidence'/('QN_' + source.name if source.name=='QUALIFICATION.json' else source.name)).write_bytes(source.read_bytes())
    record = read(ROOT/'slots/QP/product_full/call_001/SERVICE_RESULT.json')
    observed['QP']['producer_stages'] = record['stages']
    observed['QP']['producer_work'] = record['work']
    observed['QP']['producer_stage_times_overlap'] = True
    save(NS/'evidence/QUALIFICATION_COSTS.json', observed)

    archive_path = NS/'ORIGINAL_RUNTIME.zip'
    members = {}
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for name, root in sorted(FOLDERS.items()):
            assert root.is_dir(),root
            for path in sorted(root.rglob('*')):
                if not path.is_file():
                    continue
                data = path.read_bytes()
                relative = path.relative_to(root)
                assert not any(part.lower() in {'auth.json','credentials.json','.env','id_ed25519','id_rsa'}
                               for part in relative.parts), relative
                assert not PRIVATE_MARKERS.search(data), relative
                record = f'{name}/{relative.as_posix()}'
                members[record] = pin(data)
                bundle.writestr(record,data)
    with zipfile.ZipFile(archive_path) as bundle:
        assert set(bundle.namelist()) == set(members)
        assert all(pin(bundle.read(name))==record for name,record in members.items())
    save(NS/'RAW_INDEX.json', {'freeze_sha256':token,'archive':{'name':archive_path.name, **pin(archive_path.read_bytes())},
          'member_count':len(members),'qualification':{'completed':1,'failed':1,'started':2,'registered':2},
          'formal':{'completed':0,'started':0,'unrun':6,'registered':6},'product_rasters':3,'ordinary_rasters':3,
          'fixture_builds':1,'replacements':0,'members':members})
    print('Verified raw members',len(members),pin(archive_path.read_bytes()))


if __name__=='__main__':
    assert sys.flags.isolated and sys.dont_write_bytecode
    archive()
