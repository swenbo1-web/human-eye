"""Reuse the ordinary globally and locally fitted frame device on both arms."""

from common import FORMAL, load_retained


previous = load_retained('_perf050_dense_frame_device', FORMAL / 'frame_device.py')
FrameDevice = previous.FrameDevice
