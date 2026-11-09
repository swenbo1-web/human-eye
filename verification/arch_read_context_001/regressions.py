"""Relevant existing numerical/cache/action contracts for the resident reader."""
import sys
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from verification.task_scope_impl_001 import test_scope
test_scope.OUT=Path(__file__).resolve().parent
NAMES=[
'verification.test_scene_cache',
'verification.test_live_service.LiveServiceTests',
'verification.test_task_query.TaskQueryTests.test_mcp_encodes_only_selected_body_once_without_deepcopy',
'verification.test_task_query.TaskQueryTests.test_mcp_task_response_and_expired_publication',
'verification.test_task_query.TaskQueryTests.test_original_budget_still_applies_during_mcp_encoding',
'verification.test_task_query.TaskQueryTests.test_service_prevalidation_no_capture_for_incompatible_options',
'verification.task_scope_impl_001.test_scope.ScopeTests.test_one_capture_validate_full_binding_four_entities_three_helpers_one_rank',
'verification.task_scope_impl_001.test_scope.ScopeTests.test_cold_hot_and_geometry_changes_aggregate_counts',
'verification.task_scope_impl_001.test_scope.ScopeTests.test_relation_unknown_does_not_become_complete_by_filtering',
'verification.task_scope_impl_001.test_scope.ScopeTests.test_containment_positive_surface_distance_is_not_separation_gap',
'verification.task_scope_impl_001.test_scope.ScopeTests.test_exact_rank_distinguishes_equal_float_displays',
'verification.nearest_integration_001.tests.test_integration.NearestIntegrationTests.test_g01_normal_unique_and_explicit_scope',
'verification.nearest_integration_001.tests.test_integration.NearestIntegrationTests.test_g02_exact_positive_and_zero_ties_stable_ids',
'verification.nearest_integration_001.tests.test_integration.NearestIntegrationTests.test_g03_equal_published_float_exact_order',
'verification.nearest_integration_001.tests.test_integration.NearestIntegrationTests.test_g09_directory_capture_identity_mismatches_reject_before_pairs',
]
def forbidden(*a,**kw):raise AssertionError('No network/Blender/subprocess')
suite=unittest.defaultTestLoader.loadTestsFromNames(NAMES)
with patch.object(socket,'socket',side_effect=forbidden),patch.object(socket,'create_connection',side_effect=forbidden),patch.object(subprocess,'Popen',side_effect=forbidden):
    result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
