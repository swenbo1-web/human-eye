"""Launch the accepted image-bearing transport using the P2 bridge."""

from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'harness'))
import bridge


if __name__ == '__main__':
    runpy.run_path(str(HERE.parent.parent / 'm4_live_source_region_task_003/thin_stdio.py'), run_name='__main__')
