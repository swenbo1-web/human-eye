"""Selected existing offline tests relevant to task restore and delivery."""
import io
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from verification.spatial_task_entry_001 import test_entry as entry
OUT = Path(__file__).resolve().parent
entry.OUT = OUT
entry.prior.OUT = OUT
NAMES = [
 'verification.test_task_query.TaskQueryTests.test_service_prevalidation_no_capture_for_incompatible_options',
 'verification.test_task_query.TaskQueryTests.test_does_not_reuse_prior_write_prepare_context',
 'verification.test_task_query.TaskQueryTests.test_mcp_task_response_and_expired_publication',
 'verification.test_task_query.TaskQueryTests.test_original_budget_still_applies_during_mcp_encoding',
 'verification.test_task_query.TaskQueryTests.test_mcp_encodes_only_selected_body_once_without_deepcopy',
 'verification.spatial_task_entry_001.test_entry.PublicContracts.test_mode_gates_unpublished_tools_and_strict_boolean',
 'verification.spatial_task_entry_001.test_entry.AliasRoutes.test_one_public_observe_no_image_and_same_legacy_result',
 'verification.spatial_task_entry_001.test_entry.AliasRoutes.test_cache_and_local_changes',
 'verification.spatial_task_entry_001.test_entry.AliasRoutes.test_domain_refusal_retains_unknown',
 'verification.spatial_task_entry_001.test_entry.AliasRoutes.test_trace_maps_to_observe_and_image_false_with_caller_id',
 'verification.spatial_task_entry_001.test_entry.AliasRoutes.test_encoding_budget_is_the_original_request_deadline',
 'verification.spatial_task_entry_001.test_entry.AliasRoutes.test_rejected_image_argument_still_has_no_image_trace_or_capture',
 'verification.test_auto_router.RouterTests.test_export_import_and_corrupt_state',
 'verification.test_auto_router.RouterTests.test_ttl_expiry_future_clock_and_reobserve',
 'verification.test_auto_router.RouterTests.test_missing_readback_cannot_reauthorize_old_scene',
 'verification.test_attention_retry.AttentionRetryTests.test_export_import_retains_short_retry_and_immediate_confirmed_recovery',
 'verification.test_attention_retry.AttentionRetryTests.test_corrupt_imported_feedback_discards_cached_cooldown',
 'verification.test_attention_retry.AttentionRetryTests.test_wall_clock_rollback_discards_feedback_and_future_pose',
 'verification.test_refill_recovery_independent.RefillRecoveryIndependentTests.test_restart_preserves_cooldown_and_does_not_hide_due_retry_behind_ttl',
 'verification.test_refill_recovery_independent.RefillRecoveryIndependentTests.test_text_only_then_restart_retains_original_image_episode',
 'verification.test_refill_recovery_independent.RefillRecoveryIndependentTests.test_corrupt_persisted_retry_cannot_pin_hold_or_inflate_wait',
 'verification.test_live_service.LiveServiceTests.test_corrupt_or_incomplete_state_is_not_reset',
 'verification.test_live_service.LiveServiceTests.test_configuration_change_requires_host_review',
 'verification.test_live_service.LiveServiceTests.test_unpaired_scene_has_real_overview_but_no_action_qualification',
]
from verification import test_host_runtime
for name in ('test_runtime_persistence_keeps_observation_and_quarantine',
             'test_corrupt_runtime_quarantine_is_not_silently_reset'):
    cls = next(cls for cls in vars(test_host_runtime).values()
               if isinstance(cls, type) and issubclass(cls, unittest.TestCase) and hasattr(cls, name))
    NAMES.append(cls.__module__ + '.' + cls.__name__ + '.' + name)

def forbidden(*a, **kw): raise AssertionError('Network/subprocess forbidden')
log = io.StringIO()
suite = unittest.defaultTestLoader.loadTestsFromNames(NAMES)
with patch.object(socket, 'socket', forbidden), patch.object(socket, 'create_connection', forbidden), patch.object(subprocess, 'Popen', forbidden):
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
(OUT / 'regressions.log').write_text(log.getvalue(), encoding='utf8')
print(log.getvalue())
sys.exit(0 if result.wasSuccessful() else 1)
