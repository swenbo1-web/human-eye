"""Use the retained production harness in this batch's module namespace."""

from pathlib import Path

_source = (Path(__file__).resolve().parents[2] / 'm3_whole_object_witness_triangle_consumption_001'
           / Path(__file__).parent.name / Path(__file__).name)
exec(compile(_source.read_bytes(), str(_source), 'exec'))
