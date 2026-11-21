"""Verify the frozen task, safe serial ownership, and per-arm qualification."""

from pathlib import Path

from common import ASSET_SHA256, EXTERNAL, NS, ORDER, SLOTS, DUAL, load_retained, product_for, read, sha


SCHEMA = 'm1-source-region-task-entry-holdout-001-v1'
QUALIFICATION = ('QA','QB')
FORMAL = ('A1','B1')
CANDIDATE = {'commit':'e6e29f1857dfdfaea8b6c41c373fe42a5a6bde24',
             'source_sha256':'66b8855a1e551f0a7e8f60c579b9f9116ec148a07988143077e9d57a08f3f7be',
             'wheel_sha256':'997c664fbb80aaaed4f9cf0479a682bc8f8b06bb741650c0cfd00144a42a589a'}
FIELDS = ('commit','source_sha256','wheel_sha256')
can_continue = load_retained('_task_entry_closure_admission',DUAL/'harness/admission.py').can_continue


def registered_product(label):
    spec = product_for(label)
    product = {key:spec[key] for key in FIELDS}
    binding = read(spec['binding'])
    if len(binding['source_manifest'])!=143 or (label in ('QB','B1') and product!=CANDIDATE):
        raise ValueError('fixed_143_source_task_entry_install_required')
    return product


def verify_freeze(path=None):
    own = NS/'FROZEN.json'
    path = own if path is None else Path(path)
    if path.resolve()!=own.resolve():
        raise ValueError('only_the_frozen_task_entry_comparison_is_admissible')
    frozen = read(path)
    if (frozen['schema']!=SCHEMA or frozen['slots']!=list(ORDER)
            or frozen['products']!={label:registered_product(label) for label in ORDER}
            or frozen['asset_sha256']!=ASSET_SHA256 or not frozen['offline_preflight_passed']):
        raise ValueError('frozen_task_entry_input_changed')
    for row in frozen['direct_inputs']:
        file = Path(row['path'])
        if file.stat().st_size!=row['bytes'] or sha(file)!=row['sha256']:
            raise ValueError('frozen_input_changed/' + str(file))
    return sha(path)


def publication(label,frozen):
    folder = EXTERNAL/'slots'/label
    result_path = folder/'SLOT_RESULT.json'
    result,receipt = read(result_path),read(folder/'SLOT_PUBLICATION.json')
    spec = product_for(label)
    if (receipt['result_sha256']!=sha(result_path) or receipt['label']!=label or result['label']!=label
            or (result['group'],result['phase'])!=SLOTS[label] or result['product_binding_sha256']!=sha(spec['binding'])
            or result['product_source_sha256']!=spec['source_sha256'] or result['asset_sha256']!=ASSET_SHA256
            or result['freeze_sha256']!=frozen):
        raise ValueError('original_publication_does_not_bind_the_frozen_arm/' + label)
    return result,receipt


def validate_admission(label,path):
    frozen = verify_freeze(path)
    slots = EXTERNAL/'slots'
    predecessors = ORDER[:ORDER.index(label)]
    names = {folder.name for folder in slots.iterdir()} if slots.is_dir() else set()
    if names!=set(predecessors) or any(not can_continue(*publication(p,frozen)) for p in predecessors):
        raise ValueError('unexpected_or_unclosed_serial_predecessor')
    if label in FORMAL:
        for q in QUALIFICATION:
            result,receipt = publication(q,frozen)
            qualification = result.get('qualification') or {}
            proof = read(EXTERNAL/'preflight'/f'{q}_CLOSED_IMAGE.json')
            if (result['status']!='completed' or result['model_consumers']!=0 or qualification.get('passed') is not True
                    or qualification!=read(slots/q/'QUALIFICATION.json')
                    or proof['result_sha256']!=receipt['result_sha256'] or proof['freeze_sha256']!=frozen
                    or proof['image']!=qualification['product_image'] or sha(proof['image']['path'])!=proof['image']['sha256']):
                raise ValueError('actual_closed_current_qualification_required/' + q)
    return {'freeze_sha256':frozen}
