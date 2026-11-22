"""Keep the original consumer behavior with a distinct recovery episode identity."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/consumer/driver.py'
_original = _source.read_text(encoding='utf8')
if _original.count('M4-DENSE-SWEEP-INTEGRATED-NATIVE-PILOT-001-') != 1:
    raise ValueError('original_consumer_episode_anchor_changed')
exec(compile(_original.replace('M4-DENSE-SWEEP-INTEGRATED-NATIVE-PILOT-001-',
                               'M4-DENSE-SWEEP-INTEGRATED-NATIVE-PILOT-RECOVERY-001-'),
             str(_source), 'exec'))
