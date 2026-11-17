"""Adapt the bounded accepted archive/seal, including the retained camera correction."""

from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    source=HERE.with_name('m4_cross_scale_discovery_001')/'seal.py'
    text=source.read_text(encoding='utf8').replace('D:/he_m4_cross_scale_001','D:/he_m4_m5_source_region_001')
    text=text.replace("BASELINE='99f939513111637b76a1d486622b4841cad9ccda'", "BASELINE='3c26b43d197e6de252f65db69c061733e5a7216e'")
    text=text.replace("baseline['old_direct_seals']+[baseline['qualification_asset'],baseline['qualification_geometry']]", "baseline['old_direct_seals']+[baseline['accepted_install']]")
    text=text.replace("for version in ('R0','R1'):", "for version in ('R0','R0F','R1'):")
    text=text.replace("        for row in frozen['harness_pins']+[frozen['task'],frozen['oracle'],frozen['asset']]:\n            if sha(row['path'])!=row['sha256']:\n                raise ValueError('frozen_direct_input_changed/'+row['path'])",
        "        for row in frozen['harness_pins']:\n"
        "            relative=Path(row['path']).relative_to(ROOT).as_posix()\n"
        "            blob=subprocess.check_output(['git','show',frozen['preparation_git']+':'+relative],cwd=ROOT)\n"
        "            if hashlib.sha256(blob).hexdigest()!=row['sha256']:\n                raise ValueError('historical_frozen_harness_changed/'+relative)\n"
        "        for row in [frozen['task'],frozen['oracle'],frozen['asset']]:\n"
        "            if sha(row['path'])!=row['sha256']:\n                raise ValueError('frozen_direct_input_changed/'+row['path'])")
    start=text.index("    allowed={'human_eye_plugin/")
    stop=text.index("    prefix=HERE.relative_to(ROOT)",start)
    text=text[:start]+"    allowed={'human_eye_plugin/source_region.py','human_eye_plugin/active_observation_images.py',\n             'human_eye_plugin/surface_proximity.py','human_eye_plugin/live_service.py',\n             'human_eye_plugin/live_spatial_mcp.py','human_eye_plugin/query_policy.py','human_eye_plugin/read_context.py'}\n"+text[stop:]
    (HERE/'seal.py').write_text(text,encoding='utf8',newline='\n')


if __name__=='__main__':
    main()
