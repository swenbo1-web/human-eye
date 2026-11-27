"""Build the frozen D package using the previously verified installation recipe."""
from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZipFile

from transform import transform

HERE=Path(__file__).resolve().parent
ROOT=Path("D:/HumanEye/runs/M6-046-R3-PREVIOUS-WITNESS")
DEST=ROOT/"candidate"
EDITION="9.7.2+k046prev"
C_SHA="b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e"
C_PINS=ROOT.parent/"M6-043-R3-REGION-ATTRIBUTION/candidate/PINS.json"
DESIGN_SHA="466f074a7062615bc857b6559fc73dbb45530b76b707451383ff82f1b24b93c9"
KERNEL="human_eye_plugin/surface_proximity.py"
RECIPE=HERE.parents[1]/"m6_r3_region_attribution_043/candidate/build.py"


def old_helpers():
    spec=importlib.util.spec_from_file_location("_046_candidate_recipe",RECIPE)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


old=old_helpers()
sha,artifact,put,save,replace_exact=(old.sha,old.artifact,old.put,old.save,old.replace_exact)


def binding(cmeta):
    older=Path(cmeta["binding"]["path"])
    assert artifact(older)==cmeta["binding"]
    base=json.loads(older.read_bytes())
    assert base["identity"]["source_sha256"]==C_SHA
    assert base["site_packages"]==cmeta["site"] and len(base["source_files"])==143
    return older,base


def main():
    design_ref=artifact(ROOT/"DESIGN.json")
    assert design_ref["sha256"]==DESIGN_SHA
    design=json.loads((ROOT/"DESIGN.json").read_bytes())
    assert design["C_installation"]==artifact(C_PINS)
    c=json.loads(C_PINS.read_bytes())
    ref,base=binding(c)
    prior_root=Path(c["source"])
    site=Path(c["site"])
    local=DEST/"source"
    source_entries=base["source_files"]
    paths=[row["path"] for row in source_entries]
    assert len(paths)==143 and sorted(set(paths))==paths
    for row in source_entries:
        path=row["path"]
        assert ".." not in PurePosixPath(path).parts and not PurePosixPath(path).is_absolute()
        contents=(site/path).read_bytes()
        assert sha(contents)==row["sha256"]
        put(local/path,transform(contents) if path==KERNEL else contents)
    for file in old.EXTRAS:
        put(local/file,(prior_root/file).read_bytes())
    patch="".join(difflib.unified_diff((site/KERNEL).read_text(encoding="utf-8").splitlines(True),
                                       (local/KERNEL).read_text(encoding="utf-8").splitlines(True),
                                       fromfile="a/"+KERNEL,tofile="b/"+KERNEL))
    put(HERE/"D.patch",patch.encode())
    put(DEST/"D.patch",patch.encode())
    py=base["dependency_python"]
    output=DEST/"build"
    run=subprocess.run([py,"-I","-B",str(local/old.BUILD),"--output",str(output),"--version",EDITION],
                       cwd=local,capture_output=True,timeout=90)
    put(DEST/"BUILDER.stdout",run.stdout)
    put(DEST/"BUILDER.stderr",run.stderr)
    run.check_returncode()
    built=json.loads((output/"BUILD.json").read_bytes())
    identities=built["runtime_identity"]
    assert built["deterministic_rebuild"]
    all_sources=[{"path":k,"sha256":sha((local/k).read_bytes())} for k in paths]
    assert all_sources==identities["source_files"]
    assert [e["path"] for e,p in zip(all_sources,source_entries,strict=True) if e!=p]==[KERNEL]
    new_sha=identities["source_sha256"]
    assert new_sha!=C_SHA
    release=DEST/".human-eye/releases"/EDITION
    installed=release/"site-packages"
    wheel=next(i for i in built["artifacts"] if i["file"].endswith(".whl"))
    wheel_path=output/wheel["file"]
    assert artifact(wheel_path)["sha256"]==wheel["sha256"]
    with ZipFile(wheel_path) as package:
        assert len(package.namelist())==len(set(package.namelist()))
        for name in package.namelist():
            path=PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts and ":" not in name and "\\" not in name
            put(installed/Path(*path.parts),package.read(name))
    assert all((installed/k).read_bytes()==(local/k).read_bytes() for k in paths)
    admin=release/"admin"
    c_admin=ref.parent
    c_launch=(c_admin/"target_runtime_entry.py").read_bytes()
    c_manager=(c_admin/"installed_release.py").read_bytes()
    assert sha(c_launch)==base["launcher_sha256"] and sha(c_manager)==base["admin_sha256"]
    launcher=replace_exact(c_launch,base["identity"]["distribution_version"],EDITION,2)
    launcher=replace_exact(launcher,C_SHA,new_sha,3)
    manager=replace_exact(c_manager,base["launcher_sha256"],sha(launcher),1)
    put(admin/"target_runtime_entry.py",launcher)
    put(admin/"installed_release.py",manager)
    identity={k:identities[k] for k in base["identity"] if k!="distribution_version"}
    identity["distribution_version"]=EDITION
    updated=dict(base,target_release=str(release.resolve()),site_packages=str(installed.resolve()),identity=identity,
                 launcher_sha256=sha(launcher),admin_sha256=sha(manager),source_files=all_sources)
    save(admin/"RUNTIME_BINDING.json",updated)
    result=subprocess.run([py,"-I","-B",str(admin/"target_runtime_entry.py"),"identity"],cwd=DEST,
                          capture_output=True,timeout=30)
    put(DEST/"STARTUP.stdout.json",result.stdout)
    put(DEST/"STARTUP.stderr",result.stderr)
    result.check_returncode()
    v=json.loads(result.stdout)
    assert all(v["runtime_identity"][k]==value for k,value in identity.items()) and not result.stderr
    bind_ref=artifact(admin/"RUNTIME_BINDING.json")
    assert v["launcher"]["binding_sha256"]==bind_ref["sha256"]
    assert all(sha((site/row["path"]).read_bytes())==row["sha256"] for row in source_entries)
    out=dict(schema="m6-046-private-D-installation",status="pass",design=design_ref,
             baseline=artifact(C_PINS),baseline_binding=artifact(ref),identity=identity,
             source_sha256=new_sha,source_count=len(paths),source_manifest=all_sources,
             binding=bind_ref,launcher=artifact(admin/"target_runtime_entry.py"),admin=artifact(admin/"installed_release.py"),
             site=str(installed.resolve()),source=str(local.resolve()),dependency_python=py,
             patch=artifact(HERE/"D.patch"),builder=artifact(Path(__file__)),inherited_builder=artifact(RECIPE),
             transform=artifact(HERE/"transform.py"),wheel=artifact(wheel_path),startup=artifact(DEST/"STARTUP.stdout.json"),
             # Directly reusable by the existing ordinary Client once offline passes.
             arm={"site_packages":str(installed.resolve()),"source_sha256":new_sha,"version":EDITION,
                  "role":"046 private D ordinary stdio","command_prefix":[py,"-I","-B",str(admin/"target_runtime_entry.py")]},
             changed_kernel=artifact(installed/KERNEL),candidate_run=False)
    save(DEST/"PINS.json",out)
    save(HERE/"PINS.json",out)
    print(json.dumps({"source_sha256":new_sha,"pins":artifact(DEST/"PINS.json")}))


if __name__=="__main__":
    main()
