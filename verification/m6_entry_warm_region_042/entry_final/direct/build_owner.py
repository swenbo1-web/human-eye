"""Derive only a fixed-port 042 controller from the verified ordinary GUI owner."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
ORIGINAL=HERE.parents[2]/'m6_post032_profile_036/gui.py'
RAW=Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/direct')


def main():
    source=ORIGINAL.read_bytes()
    assert hashlib.sha256(source).hexdigest()=='0fbaff15c0236747146616b827beb94d131abeeeb8d3ef11733bd370bc332208'
    text=source.decode('utf8')
    changes=[("PRIVATE = Path('D:/HumanEye/runs/M6-036-POST032-PROFILE')",f"PRIVATE = Path({str(RAW)!r})"),
             ("CYCLE = 'M6-036-POST032-PROFILE'","CYCLE = 'M6-042-E-FINAL-DIRECT'"),
             ('reservation.bind((self.host, 0))','reservation.bind((self.host, 48142))')]
    for old,new in changes:
        assert text.count(old)==1,old
        text=text.replace(old,new)
    output=HERE/'gui_owner.py'
    output.write_bytes(text.encode('utf8'))
    RAW.mkdir(parents=True,exist_ok=True)
    record={'original':{'path':str(ORIGINAL),'bytes':len(source),'sha256':hashlib.sha256(source).hexdigest()},
            'derived':{'path':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},
            'literal_replacements':changes,'addon_worker_or_serving_methods_modified':False}
    with (RAW/'OWNER_DERIVATION.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
