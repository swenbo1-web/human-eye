"""Bind the recovered admission checks to the one shading-source change."""

from common import CATALOGUE, PIXEL_BASE, SOURCE_SHA, load_retained


SCHEMA = 'm4-dense-raster-cross-v1'
BASELINE = {'commit': 'f72e648f763fb6399f82c8e5d7f2b35840597bed', 'source_sha256': SOURCE_SHA}
CHANGED = ['human_eye_plugin/attention_raster.py']
previous = load_retained('_dense_raster_previous_admission', PIXEL_BASE / 'harness/admission.py')
previous.SCHEMA, previous.BASELINE, previous.CHANGED = SCHEMA, BASELINE, CHANGED
registered_products, verify_freeze = previous.registered_products, previous.verify_freeze
publication, can_continue, admit = previous.publication, previous.can_continue, previous.admit
