"""Seal the one qualification, its actual preflights and its one distributable."""

from hashlib import sha256
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qualification import CANDIDATE, HERE, launch, read, require, save
from freeze import verify


def seal():
    freeze = verify()
    root = launch.EXTERNAL
    formal = root / 'qualification'
    install = root / 'candidate_install'
    outcome_path = formal / 'RESULT.json'
    if not outcome_path.is_file():
        outcome_path = formal / 'FAILURE.json'
    outcome = read(outcome_path)
    if outcome['passed']:
        require(outcome['freeze_sha256'] == freeze, 'qualification_does_not_match_frozen_assets')
    inputs = [path for folder in ('launch_baseline_preflight', 'production_preflight', 'qualification')
              for path in (root / folder).rglob('*') if path.is_file()]
    inputs.extend((Path(read(CANDIDATE)['wheel_path']), install / 'PIP_STDOUT.bin', install / 'PIP_STDERR.bin'))
    output = HERE / 'ORIGINAL_RUNTIME.zip'
    members = {}
    with ZipFile(output, 'x', compression=ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(inputs):
            member = path.relative_to(root).as_posix()
            original = path.read_bytes()
            members[member] = {'bytes': len(original), 'sha256': sha256(original).hexdigest()}
            bundle.writestr(member, original)
    with ZipFile(output) as bundle:
        require(set(bundle.namelist()) == members.keys() and len(bundle.namelist()) == len(members),
                'sealed_member_set_changed')
        for member, expected in members.items():
            actual = bundle.read(member)
            require(len(actual) == expected['bytes'] and sha256(actual).hexdigest() == expected['sha256'],
                    'sealed_member_changed/' + member)
    copy = HERE / 'evidence' / outcome_path.name
    with copy.open('xb') as result:
        result.write(outcome_path.read_bytes())
    archive = launch.pin(output)
    save(HERE / 'RAW_INDEX.json', {'archive': {'name': output.name, 'bytes': archive['bytes'], 'sha256': archive['sha256']},
                                  'freeze_sha256': freeze, 'passed': outcome['passed'],
                                  'member_count': len(members), 'members': members})
    print('Sealed', len(members), 'members', archive['bytes'], 'bytes', archive['sha256'])


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_interpreter_required')
    seal()
