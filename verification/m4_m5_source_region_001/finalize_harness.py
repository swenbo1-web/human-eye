"""Bind the accepted fresh asset to the fixed, owned state-control helper."""

import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    binding=json.loads((HERE/'fixture/ASSET_BINDING.json').read_bytes())
    path=HERE/'harness/state_owned_native.py'
    before=path.read_bytes()
    text=before.decode().replace('a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6',binding['asset_sha256']).replace('Obj_02','Obj_07')
    path.write_text(text,encoding='utf8',newline='\n')
    record=dict(schema='source-region-state-fixture-binding-v1',asset=binding['asset_sha256'],target='Obj_07',
        transform='world X +1/4 then exact identity restore in the owned unsaved copy',
        before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        process_starts=0,raster_attempts=0)
    with (HERE/'STATE_HELPER_BINDING.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(record,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(bound=True,asset=binding['asset_sha256'])))


if __name__=='__main__':
    main()
