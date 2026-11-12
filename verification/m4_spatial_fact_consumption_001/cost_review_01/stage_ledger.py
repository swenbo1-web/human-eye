"""Keep preparation, formal execution and unmeasured review resources distinct."""

from datetime import datetime
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def main():
    preparation = json.loads((BATCH / 'PREPARATION_COST.json').read_bytes())
    result = json.loads((BATCH / 'RUN_RESULT.json').read_bytes())
    installation = json.loads((BATCH / 'installations/P_READY.json').read_bytes())
    preparation_s = (datetime.fromisoformat(preparation['freeze_utc'])
                     - datetime.fromisoformat(preparation['recorded_start_utc'])).total_seconds()
    cells_ns = sum(row['full_cell_wall_ns'] for row in result['records'])
    ledger = {
        'preparation': {
            'source': 'PREPARATION_COST.json',
            'recorded_wall_window_s': preparation_s,
            'scope': preparation['scope'],
            'model_consumers': preparation['model_consumers'],
            'Blender_sessions': preparation['Blender_sessions'],
            'live_product_processes': preparation['live_product_processes'],
            'smoke_sessions': preparation['smoke_sessions'],
            'installation_rebuilds': preparation['installation_rebuilds'],
            'coordinator_model_cost': None,
            'coordinator_model_cost_status': 'unmeasured',
            'amortized_into_query_cost': False,
        },
        'historical_installation': {
            'source': 'installations/P_READY.json',
            'reused_version': installation['version'],
            'recorded_historical_installation_s': installation['elapsed_ns'] / 1e9,
            'scope': 'Prior isolated installation receipt. This batch reused that installation.',
            'charged_again_as_current_build': False,
        },
        'formal_six_consumers': {
            'source': 'RUN_RESULT.json',
            'consumers': len(result['records']),
            'batch_wall_s': result['batch_wall_ns'] / 1e9,
            'sum_full_cell_wall_s': cells_ns / 1e9,
            'batch_outside_cells_s': (result['batch_wall_ns'] - cells_ns) / 1e9,
            'scope': result['batch_timing_scope'],
            'monetary_fees': None,
            'monetary_fee_status': 'unmeasured',
        },
        'independent_quality_review': {
            'source': 'quality_source/QUALITY_SEAL.json',
            'model_or_staff_cost': None, 'elapsed_s': None,
            'status': 'No complete resource ledger exposed by the sealed review materials.',
        },
        'saved_data_cost_review': {
            'new_consumer_runs': 0, 'new_Blender_or_product_runs': 0,
            'coordinator_and_review_model_cost': None, 'total_review_elapsed_s': None,
            'status': 'Coordinator/reviewer cost and full review duration unmeasured.',
        },
    }
    with (HERE / 'STAGE_LEDGER.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(ledger, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'preparation_recorded_wall_window_s': preparation_s,
                      'formal_batch_wall_s': result['batch_wall_ns'] / 1e9,
                      'fees': 'unmeasured'}))


if __name__ == '__main__':
    main()
