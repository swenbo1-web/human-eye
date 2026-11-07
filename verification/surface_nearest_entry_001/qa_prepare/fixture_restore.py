"""Unconditional disarm and restore, including an unentered/failed capture."""
import json
import sys
sys.setprofile(None)
assert globals().get('_surface_entry_fixture') is not None, 'fixture_receipt_missing'
assert _surface_entry_fixture['state'] == STATE
_qa_restore_geometry()
_surface_entry_fixture['finally_disarmed'] = True
_surface_entry_fixture['after_finally'] = _qa_snapshot()
_qa_persist()
print('SURFACE_ENTRY_RESTORE:'+json.dumps(_surface_entry_fixture, separators=(',',':'), allow_nan=False))
_surface_entry_fixture = None
