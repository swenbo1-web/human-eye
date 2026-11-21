"""Use the same ordinary raw geometry and frame device in both arms."""

from common import FORMAL, load_retained


previous = load_retained('_task_entry_dense_frame_device', FORMAL / 'frame_device.py')
FrameDevice = previous.FrameDevice
