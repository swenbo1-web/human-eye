"""Retain the fully bound source-region device used by the pilot."""

from common import PILOT, load_retained


previous = load_retained('_m4_active_view_pilot_frame_device', PILOT / 'harness/frame_device.py')
FrameDevice = previous.FrameDevice
