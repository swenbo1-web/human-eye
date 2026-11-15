"""Pinned independent geometry/pixel oracle from the accepted source task."""
import hashlib
import importlib.util
from pathlib import Path
SOURCE=Path('C:\\Users\\Administrator\\.codex\\worktrees\\m4-view-reuse-001\\hefe\\verification\\m4_occluded_scene_transfer_001\\oracle.py')
EXPECTED='42d4a7617e3b5ebb5b6a0073c0ab83be6e028cf0159e1abe1389e6b8847cafa7'
if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=EXPECTED:
    raise ValueError('accepted_independent_oracle_changed')
spec=importlib.util.spec_from_file_location('_source_face_accepted_oracle',SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
read=module.read
sha=module.sha
frame_pixels=module.frame_pixels
fraction=module.fraction
npy=module.npy
int32=module.int32
