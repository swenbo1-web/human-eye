"""Attach the original image-bearing thin stdio to the qualification gate."""

from pathlib import Path
import runpy
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import bridge
from common import IMAGE_BRIDGE


if __name__ == '__main__':
    runpy.run_path(str(IMAGE_BRIDGE / 'thin_stdio.py'), run_name='__main__')
