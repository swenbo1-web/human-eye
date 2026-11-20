"""Use the reviewed image-bearing thin stdio with this task's bridge."""

from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bridge


if __name__ == '__main__':
    runpy.run_path(str(bridge.SOURCE_REGION / 'thin_stdio.py'), run_name='__main__')
