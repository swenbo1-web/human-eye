"""Pre-generation source winding inspection entry point."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_views import render_sources

if __name__ == "__main__":
    render_sources()
