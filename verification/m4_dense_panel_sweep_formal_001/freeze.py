"""Freeze the actual seven-slot dense sweep, external QP, and fixed consumer."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path[:0] = [str(NS / 'harness'), str(NS)]
from admission import PRODUCT_GIT, SCHEMA, verify_freeze
from budget import LIMITS
from common import EXTERNAL, PRODUCT_BINDING, ROOT, SLOTS, SOURCE_SHA, asset_identity, read, save, sha
from qualification_gate import COMPACT, DENSE, external_qp


V = NS.parent
BASE = 'ea74b940dd78f3e467856659b197acdbe9710f6d'
PLAN_SHA = '35d42bfe26d69515044326332f95df53a9eb06ee74781bf81940fd4e45598560'
ASSET_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
TRUTH_SHA = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
GEOMETRY_SHA = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
ASSEMBLY = V / 'm4_cross_scale_assembly_transfer_001'
MANIFESTS = (
    (COMPACT, 'b0660b1eb64afec1c6f8a6c78e208dbe194c117efc9a36ccbae30213186a0f50',
     '47bc5f9aaa240fc91bd66564f4d0712ea3d270c86f163f4de087d487a2ea548e'),
    (DENSE, '9f4f30c3104f9bd0fae9f1021618aeff324063ff826515343ab82938130946fb',
     'c17e62c10ef163137b8e6057cab0802c5dce6cf5cc96222fcb2aead09870d0ad'),
    (ASSEMBLY, '5c42ef83e0bc6761798d0c18d6210684a59216eca3071202853fcf3d2adced69',
     '0be1c09cf34ce3392b02a5698db0922a4ed05a39a62ab6194c75e007853213b3'),
)


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('fresh_runtime_schedule_and_isolated_interpreter_required')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() != BASE:
        raise ValueError('not_directly_on_the_accepted_compact_brief_evidence_base')
    if tuple(SLOTS) != ('QN', 'N1', 'P1', 'P2', 'N2', 'N3', 'P3'):
        raise ValueError('registered_actual_qualification_and_consumer_order_changed')
    for name in ('inputs/PROMPT_COMMON.txt', 'inputs/PROMPT_N.txt', 'inputs/PROMPT_P.txt', 'inputs/REQUEST.json',
                 'inputs/PRODUCT_SCHEMA.json', 'inputs/TOOLS_SCHEMA.json', 'scoring/RUBRIC.md'):
        if (NS / name).read_bytes() != (DENSE / name).read_bytes():
            raise ValueError('original_task_instructions_and_scoring_must_remain_byte_identical/' + name)
    qp, qp_pins = external_qp()
    asset, asset_sha = asset_identity()
    if asset_sha != ASSET_SHA:
        raise ValueError('frozen_asset_changed')
    truth = DENSE / 'truth/CURRENT_TRUTH.json'
    if len(read(truth)['eligible']) != 13:
        raise ValueError('original_truth_denominator_changed')

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        row = pins.get(path)
        if row is None:
            row = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((digest is not None and row['sha256'] != digest)
                or (size is not None and row['bytes'] != size) or path.suffix == '.pyc'):
            raise ValueError('pre_registered_input_changed/' + str(path))
        pins[path] = row

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    pin(NS / 'inputs/PLAN.md', PLAN_SHA)
    pin(asset, ASSET_SHA)
    pin(asset.with_suffix('.GEOMETRY.json'), GEOMETRY_SHA)
    pin(truth, TRUTH_SHA)
    pin_rows(read(truth)['source_pins'])
    for path in qp_pins:
        pin(path)
    for directory, freeze_digest, manifest_digest in MANIFESTS:
        path = directory / 'FROZEN.json'
        manifest = directory / 'CONTENT_MANIFEST.json'
        pin(path, freeze_digest)
        pin(manifest, manifest_digest)
        pin_rows(read(path)['direct_inputs'])
        for row in read(manifest)['files']:
            pin(directory / row['path'], row['sha256'], row['bytes'])

    binding = read(PRODUCT_BINDING)
    install = read(PRODUCT_BINDING.parent / 'BUILD_INSTALL.json')
    if (binding != install['binding'] or install['passed'] is not True
            or binding['preparation_git'] != PRODUCT_GIT or binding['source_sha256'] != SOURCE_SHA
            or len(binding['source_manifest']) != 143
            or read(NS / 'inputs/PRODUCT_SCHEMA.json') != read(PRODUCT_BINDING.parent / 'PRODUCT_SCHEMA.json')
            or read(NS / 'inputs/TOOLS_SCHEMA.json') != read(PRODUCT_BINDING.parent / 'TOOLS_SCHEMA.json')):
        raise ValueError('fixed_installed_runtime_or_tool_catalogue_changed')
    pin(PRODUCT_BINDING, qp['product_binding_sha256'])
    pin(binding['wheel_path'], binding['wheel_sha256'])
    for key in ('installed_files', 'execution_and_input_pins'):
        pin_rows(install[key])

    shared = V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'
    sys.path[:0] = [str(NS), binding['dependency_root'], read(shared)['dependency_root']]
    from consumer import consumer_adapter

    _, cli, _ = consumer_adapter()
    if (cli['CLI_sha256'] != CLI_SHA or cli['CLI_version'] != '0.152.1' or cli['model'] != 'gpt-6.1-sol'
            or cli['reasoning_effort'] != 'medium' or cli['service_tier'] != 'default'
            or Path(cli['Python_path']).resolve() != Path(sys.executable).resolve()):
        raise ValueError('original_consumer_configuration_changed')
    pin(cli['CLI_path'], CLI_SHA)
    pin_rows(cli['execution_sources'])
    login = subprocess.run([cli['CLI_path'], 'login', 'status'], check=True, capture_output=True, timeout=15)
    if b'Logged in using ChatGPT' not in login.stdout + login.stderr:
        raise ValueError('current_fixed_CLI_ChatGPT_login_required')
    preflight_path = NS / 'harness/DISPATCH_PREFLIGHT.json'
    preflight = read(preflight_path)
    if (preflight['passed'] is not True or preflight['external_qp'] != qp
            or preflight['ledger_limits'] != LIMITS
            or any(preflight[key] != 0 for key in ('actual_Blender_processes', 'actual_model_runs', 'actual_raster_attempts'))
            or [(row['slot'], (row['group'], row['phase'])) for row in preflight['slots']] != list(SLOTS.items())
            or not all(row['result_path_suffix'] == f"slots/{row['slot']}/SLOT_RESULT.json"
                       and row['publication_path_suffix'] == f"slots/{row['slot']}/SLOT_PUBLICATION.json"
                       and row['tool_schema_verified'] is True for row in preflight['slots'])):
        raise ValueError('all_seven_slot_dispatch_and_archival_preflight_must_pass')
    pin_rows(preflight.get('source_pins', []))
    scorer = read(NS / 'scoring/SCORER_PREFLIGHT.json')
    if scorer['passed'] is not True:
        raise ValueError('the_registered_dense_scorer_must_pass_offline_controls')
    pin_rows(scorer.get('source_pins', []))
    for name in ('qualification/diagnostic.py', 'qualification/native_case.py', 'qualification/qualify.py',
                 'scoring/score.py', 'harness/run_slot.py', 'costs.py', 'publish.py'):
        if not (NS / name).is_file():
            raise ValueError('pre_registered_dispatch_or_scorer_missing/' + name)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    frozen = NS / 'FROZEN.json'
    save(frozen, {'schema': SCHEMA, 'slots': list(SLOTS), 'ledger_limits': LIMITS, 'external_qp': qp,
         'product_git': PRODUCT_GIT, 'product_source_sha256': SOURCE_SHA, 'product_diff_files': 0,
         'asset_sha256': ASSET_SHA, 'source_geometry_sha256': GEOMETRY_SHA, 'truth_sha256': TRUTH_SHA,
         'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'owned_s': 600, 'task_s': 450,
         'request_model': {'CLI_version': '0.152.1', 'CLI_sha256': CLI_SHA, 'model': cli['model'],
                           'reasoning_effort': cli['reasoning_effort'], 'service_tier': cli['service_tier']},
         'performance_gate': {'complete_correct_per_arm': 3, 'plugin_fact_adoptions_required': 3,
                              'median_paired_reduction_min': .10, 'plugin_faster_pairs_min': 2,
                              'raw_CLI_input_plus_output_delta_max': 0},
         'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze external QP, native qualification, and six fresh formal slots', len(pins), verify_freeze(frozen))


if __name__ == '__main__':
    freeze()
