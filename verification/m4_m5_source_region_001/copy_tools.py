"""Adapt accepted build and fixture process tooling into this isolated task."""

from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=HERE.with_name('m4_cross_scale_discovery_001')


def main():
    for name in ('build_install.py','freeze_product.py','schema_snapshot.py'):
        text=(PRIOR/name).read_text(encoding='utf8')
        text=text.replace('D:/he_m4_cross_scale_001','D:/he_m4_m5_source_region_001')
        text=text.replace("PRIOR = HERE.with_name('m4_global_local_qualification_001')", "PRIOR = HERE.with_name('m4_cross_scale_discovery_001')")
        text=text.replace("PRIOR/'B_RUN_BINDING.json'", "PRIOR/'R1_RUN_BINDING.json'")
        text=text.replace("PRIOR / 'B_RUN_BINDING.json'", "PRIOR / 'R1_RUN_BINDING.json'")
        text=text.replace("HERE.with_name('m4_global_local_qualification_001')/'B_RUN_BINDING.json'", "HERE.with_name('m4_cross_scale_discovery_001')/'R1_RUN_BINDING.json'")
        text=text.replace("{'human_eye_plugin/active_observation_region_task.py'}", "{'human_eye_plugin/source_region.py'}")
        text=text.replace("if len(manifest) != 142:", "if len(manifest) < 143:")
        text=text.replace('expected_142_runtime_sources','expected_source_region_runtime_sources')
        text=text.replace("(HERE.with_name('m5_observe_measure_001')/'build_final')", "(HERE.with_name('m4_cross_scale_discovery_001')/'build_R1')")
        text=text.replace('9.7.2+m4.cross.scale.001.', '9.7.2+m4.m5.source.region.001.')
        text=text.replace('D:/he_m4_global_local_001/fixture/main.blend','D:/he_m4_m5_source_region_001/fixture/main.blend')
        (HERE/name).write_text(text,encoding='utf8',newline='\n')
    source=HERE.with_name('m4_global_local_qualification_001')/'fixture_prepare.py'
    text=source.read_text(encoding='utf8').replace('D:/he_m4_global_local_001','D:/he_m4_m5_source_region_001')
    text=text.replace('oracle/STATIC_QUALIFICATION.json','oracle/STATIC_PREFLIGHT.json')
    text=text.replace("static.get('passed') is not True or static.get('status') != 'qualified'", "static.get('passed') is not True")
    (HERE/'fixture_prepare.py').write_text(text,encoding='utf8',newline='\n')


if __name__=='__main__':
    main()
