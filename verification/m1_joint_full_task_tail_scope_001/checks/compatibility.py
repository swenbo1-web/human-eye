"""Run the retained 24-case replay gate with the narrowed candidate."""

from pathlib import Path
import runpy


BASE = Path(__file__).resolve().parents[2] / 'm1_joint_full_task_tail_001'
gate = runpy.run_path(str(BASE / 'checks/controls.py'))
gate['main'].__globals__['AFTER_REVISION'] = '4e4c653a4d4726576f4f4d2a9d7b9decede44cbf'


if __name__ == '__main__':
    gate['main']()
