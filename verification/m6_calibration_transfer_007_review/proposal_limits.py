"""Private-scoring diagnosis of the frozen proposal's coverage and direction."""
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6tr7/batch'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007')


def main():
    binding = json.loads((BASE / 'SOURCE_BINDING.json').read_bytes())
    path = Path(binding['proposals'][0]['payload']['path'])
    payload_path = BASE / path.relative_to(AUTHOR) if path.is_absolute() else BASE / path
    with np.load(payload_path) as packet:
        ids, values = packet['source_ids'], packet['displacements_world']
    assert len(ids) == 13
    # Proposal geometry is fixed before private target access.
    with np.load(BASE / 'private/scoring_input/target.npz') as target:
        clean, current = target['clean_vertices_world'], target['initial_vertices_world']
        support = target['support_ids']
    displacement = np.zeros_like(current)
    displacement[ids] = values
    error = current[support] - clean[support]
    direction = displacement[support]
    quadratic = float(np.sum(direction ** 2))
    cross = float(np.sum(error * direction))
    initial_energy = float(np.sum(error ** 2))
    optimal_alpha = -cross / quadratic
    optimal_energy = initial_energy - cross * cross / quadratic
    threshold_energy = .7 ** 2 * initial_energy
    discriminant = (2 * cross) ** 2 - 4 * quadratic * (initial_energy - threshold_energy)
    active_support = np.isin(support, ids)
    uncovered_energy = float(np.sum(error[~active_support] ** 2))
    independent_Y_energy = uncovered_energy + float(np.sum(error[active_support][:, [0, 2]] ** 2))
    result = dict(
        scope='Private scoring-only bound for one already frozen proposal; never a runtime alpha selector.',
        proposal_points=len(ids), support_points=len(support), covered_support=int(active_support.sum()),
        uncovered_support=int((~active_support).sum()),
        energy_quadratic=quadratic, energy_cross=cross, initial_energy=initial_energy,
        optimal_continuous_alpha=optimal_alpha,
        best_possible_support_RMSE=float(np.sqrt(optimal_energy / len(support))),
        best_possible_RMSE_reduction=float(1 - np.sqrt(optimal_energy / initial_energy)),
        thirty_percent_target_discriminant=discriminant,
        coverage_only_independent_3D_RMSE_reduction_ceiling=float(1 - np.sqrt(uncovered_energy / initial_energy)),
        covered_points_independent_Y_RMSE_reduction_ceiling=float(1 - np.sqrt(independent_Y_energy / initial_energy)),
        adding_alpha_samples_can_meet_thirty_percent=bool(discriminant >= 0),
        new_Pro=0, new_Blender=0, new_training=0,
    )
    assert discriminant < 0 and result['best_possible_RMSE_reduction'] < .3
    (HERE / 'PROPOSAL_LIMITS.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
