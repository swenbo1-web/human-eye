"""Pin the accepted predecessor and independently verify its complete local seal."""

from hashlib import file_digest
from pathlib import Path
import sys
from zipfile import ZipFile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from experiment import LEGACY, OLD_COMMIT, git, pin, read, require, write

PRIOR=HERE.parent/'m2_source_region_selective_residency_001'
ORIGINAL=Path('D:/he_m2_source_region_selective_residency_001')


def main():
    paths={PRIOR/name for name in ('REPORT.md','RESULT.json','METRICS.json','FROZEN.json','PUBLIC_EVIDENCE.zip')}
    for path in paths:
        require(path.read_bytes()==git('show',OLD_COMMIT+':'+path.relative_to(HERE.parents[1]).as_posix()),
                'accepted_prior_git_blob_changed')
    local_manifest=ORIGINAL/'sealed/RAW_INDEX.json'
    original=read(local_manifest)
    archive=Path(original['archive']['path'])
    accepted=read(PRIOR/'RESULT.json')
    require(original['member_count']==1145 and original['archive']==pin(archive)
            and original['archive']['sha256']==accepted['raw_archive']['archive']['sha256']
            and accepted['passed'] is True and accepted['live']['closed_valid_slots']==4 and accepted['live']['requests']==12,
            'accepted_prior_complete_actual_slot_or_archive_changed')
    with ZipFile(archive) as zipped:
        require(zipped.testzip() is None and len(zipped.namelist())==1145
                and set(zipped.namelist())==set(original['members']),'prior_native_archival_crc_or_members')
        for name,row in original['members'].items():
            with zipped.open(name) as stream:
                require(zipped.getinfo(name).file_size==row['bytes']
                        and file_digest(stream,'sha256').hexdigest()==row['sha256'],'prior_native_archive_member_changed/'+name)
            require(all(pin(ORIGINAL/name)[key]==row[key] for key in ('bytes','sha256')),
                    'prior_native_original_changed/'+name)
    paths.update((archive,local_manifest,ORIGINAL/'SCORE.json'))
    for label in ('AA','AB','YA','YB'):
        slot=ORIGINAL/'slots'/label
        for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json','HOST_RECEIPT.json','TERMINAL_SOURCE.json'):
            path=slot/name
            require(all(pin(path)[key]==original['members'][path.relative_to(ORIGINAL).as_posix()][key]
                        for key in ('bytes','sha256')),'prior_actual_slot_binding_changed')
            paths.add(path)
        require(read(slot/'HOST_RECEIPT.json')['closure_verification']['passed'] is True,
                'accepted_prior_actual_owned_close_missing')
    write(LEGACY,{'passed':True,'previous_formal_passed':True,'prior_commit':OLD_COMMIT,'members_verified':1145,
                  'prior_live_blender_starts':4,'prior_live_measurements':12,
                  'source_pins':[pin(path) for path in sorted(paths)]})


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_custody_interpreter')
    main()
