"""Launch the unmodified retained stdio protocol over this batch's owner."""

from pathlib import Path
import runpy
import sys


sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import PRIOR, add_paths

add_paths()
import bridge

runpy.run_path(str(PRIOR/'thin_stdio.py'),run_name='__main__')
