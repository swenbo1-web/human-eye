"""Seal the installed witness-path candidate and actual replay originals."""

from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
sys.path.insert(0,str(NS))
from freeze import CANDIDATE, ROOT, digest, read, require, save, verify


def seal():
    frozen=verify()
    slot=ROOT/'qualification'
    state=slot/'RESULT.json' if (slot/'RESULT.json').is_file() else slot/'FAILURE.json'
    conclusion=read(state)
    require(conclusion['freeze_sha256']==frozen,'actual_result_does_not_match_freeze')
    policy=run_path(str(NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'))
    check,pin=(policy[key] for key in ('check_named_bytes','digest'))
    target=NS/'ORIGINAL_RUNTIME.zip'
    roster={}
    external_paths=[(name,ROOT/name) for name in ('compatibility','qualification')]
    external_paths.extend([('independent_checks',Path(str(ROOT)+'_independent_checks'))])
    for folder in ROOT.iterdir():
        if folder.is_dir() and ('preflight' in folder.name or 'probe' in folder.name):
            external_paths.append((folder.name,folder))
    original_files=[(prefix+'/'+path.relative_to(folder).as_posix(),path) for prefix,folder in external_paths
                    for path in sorted(folder.rglob('*')) if path.is_file()]
    build=ROOT/'candidate_install'
    original_files.extend(('candidate_install/'+path.name,path)
                      for path in (Path(read(CANDIDATE)['wheel_path']),build/'PIP_STDOUT.bin',build/'PIP_STDERR.bin'))
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for name,path in original_files:
            require(name not in roster,'sealed_duplicate_member/' + name)
            data=path.read_bytes()
            check(name,data)
            roster[name]=pin(data)
            archive.writestr(name,data)
    with ZipFile(target) as archive:
        require(len(archive.namelist())==len(roster) and set(archive.namelist())==roster.keys()
                and all(pin(archive.read(name))==value for name,value in roster.items()),'archive_digest_check_failed')
    with (NS/'evidence'/state.name).open('xb') as out:
        out.write(state.read_bytes())
    save(NS/'RAW_INDEX.json',{'passed':conclusion['passed'],'freeze_sha256':frozen,
         'archive':{'name':target.name,'bytes':target.stat().st_size,'sha256':digest(target)},
         'member_count':len(roster),'members':roster})
    print('Sealed',len(roster),'members',target.stat().st_size,'bytes',digest(target),flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    seal()
