"""Root-only byte-exact archive of the fully closed M5 runtime."""
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m5_observe_measure_001').resolve()
ARCHIVE = HERE / 'runtime_archive'
REPORTS = ['QUALITY.json', 'QUALITY_SEAL.json', 'DECISION.json', 'RUNTIME_REVIEW.json',
           'RUNTIME_COST_CROSSCHECK.json', 'REPORT.md']
ORDER = ['A1','B1','B2','A2','A3','B3','A_task_only','B_task_only']


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def snapshot():
    files = []
    for directory, names, filenames in os.walk(RUNTIME, topdown=True, followlinks=False):
        for name in names+filenames:
            path = Path(directory)/name
            if path.is_symlink() or path.is_junction():
                raise ValueError('runtime_reparse_entry')
            path.resolve().relative_to(RUNTIME)
        files.extend(Path(directory)/name for name in filenames)
    return [(path.relative_to(RUNTIME).as_posix(),path.stat().st_size,sha(path)) for path in sorted(files)]


def same_bytes(first,second):
    with first.open('rb') as left, second.open('rb') as right:
        while True:
            a,b=left.read(1024*1024),right.read(1024*1024)
            if a!=b:
                return False
            if not a:
                return True


def main():
    for name in REPORTS:
        if not (HERE/name).is_file():
            raise ValueError('closed_final_report_required:'+name)
    review=read(HERE/'RUNTIME_REVIEW.json')
    if (review.get('passed_checked_scope') is not True or review.get('qualification_only') is not False
            or review['actual_slot_count']!=12 or review['budget']['counts']['starts']!=12
            or review['budget']['model_consumers']!=0 or review['budget']['paid_API_calls']!=0):
        raise ValueError('complete_twelve_owned_review_required')
    run=read(RUNTIME/'formal/RUN_RESULT.json')
    if (run['all_eight_transport_closed'] is not True or [row['label'] for row in run['records']]!=ORDER
            or run['dispatched']!=8 or run['retries']!=0 or run['replacement_samples']!=0
            or run['blocker'] is not None):
        raise ValueError('one_closed_eight_slot_run_required')
    if ARCHIVE.exists() or (HERE/'RUNTIME_ARCHIVE.json').exists():
        raise FileExistsError('runtime_archive_write_once')
    before=snapshot()
    if not before:
        raise ValueError('empty_closed_runtime')
    ARCHIVE.mkdir()
    rows=[]
    for index,(relative,size,expected) in enumerate(before,1):
        original=RUNTIME/relative
        target=ARCHIVE/('f'+str(index).zfill(6)+'_'+original.name[:110])
        actual=hashlib.sha256()
        copied=0
        with original.open('rb') as incoming,target.open('xb') as outgoing:
            for block in iter(lambda:incoming.read(1024*1024),b''):
                outgoing.write(block)
                actual.update(block)
                copied+=len(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if copied!=size or actual.hexdigest()!=expected or not same_bytes(original,target):
            raise ValueError('archive_copy_or_closed_original_changed:'+relative)
        rows.append(dict(original_path=str(original),relative_path=relative,
                         archive_path=target.relative_to(HERE).as_posix(),bytes=size,sha256=expected))
    if snapshot()!=before:
        raise ValueError('closed_runtime_changed_during_archive')
    result=dict(schema='m5-observe-measure-runtime-archive-v1',runtime_root=str(RUNTIME),
        file_count=len(rows),bytes=sum(row['bytes'] for row in rows),files=rows,
        all_copies_verified_byte_exact=True,original_runtime_retained=True,runtime_exclusions=[],
        report_pins={name:sha(HERE/name) for name in REPORTS},new_owned_starts=0,new_rasters=0,
        new_model_calls=0,new_paid_API_calls=0,
        scope='Entire closed D runtime, including actual installations, all original process/wire/producer/budget files and failed/unknown evidence. New namespace bytecode outside D runtime is outside this archive.')
    with (HERE/'RUNTIME_ARCHIVE.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(dict(files=len(rows),bytes=result['bytes'],byte_exact=True)))


if __name__=='__main__':
    main()
