"""Use the recovered six-slot, one-call, two-raster budget."""

from common import PIXEL_BASE, load_retained


previous = load_retained('_dense_raster_previous_budget', PIXEL_BASE / 'harness/budget.py')
LIMITS = previous.LIMITS
Budget, encoded, save = previous.Budget, previous.encoded, previous.save
