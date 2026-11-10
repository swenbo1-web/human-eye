"""Read-only proof of actual isolated wheel imports; no path injection."""
import importlib.metadata
import json
from pathlib import Path
import sys
import sysconfig

import numpy
import PIL
import human_eye_plugin
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.goal_execution import ArmAxialTaskSpec
from human_eye_plugin.goal_scheduler import OwnedGoalScheduler

identity=runtime_identity(mode='live')
print(json.dumps({'isolated':bool(sys.flags.isolated),'python':sys.executable,'prefix':sys.prefix,
    'site_root':sysconfig.get_paths()['purelib'],'plugin_file':human_eye_plugin.__file__,
    'goal_task_file':sys.modules[ArmAxialTaskSpec.__module__].__file__,
    'scheduler_file':sys.modules[OwnedGoalScheduler.__module__].__file__,
    'numpy_version':numpy.__version__,'numpy_file':numpy.__file__,
    'pillow_version':PIL.__version__,'pillow_file':PIL.__file__,
    'distribution_version':importlib.metadata.version('human-eye-spatial-plugin'),
    'source_kind':identity['source_kind'],'runtime_identity':identity,'sys_path':sys.path}))
