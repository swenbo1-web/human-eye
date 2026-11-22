"""Use the retained shared raw capture, local viewport and source ownership."""

from common import FORMAL, load_retained


_retained = load_retained('_yanyite_retained_frame_device', FORMAL / 'frame_device.py')


class FrameDevice(_retained.FrameDevice):
    """Bind the shared device to this owned runner's namespace."""
