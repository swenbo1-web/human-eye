"""Build a new Windows local-test bundle; never replace or upload a release.

Default is a read-only plan. Use --build only after runtime source is frozen.
The package ships its own engine wheel and Python-3.12 Windows dependency wheels.
Installation validation uses a new isolated venv and never imports the checkout.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from verification.build_release_bundle import portable

VERSION_PREFIX = "9.7.2+20261023.rigid.frame"
NAME_PREFIX = "human_eye_engine_" + VERSION_PREFIX.split("+", 1)[1]
EVIDENCE_ROOT = ROOT / "verification/fixes/20261023_field_validation/extreme_01/repair_02"
EXPECTED_IMPLEMENTATION_REVISION = "v1-rigid-frame-20261023"
DEPENDENCIES = ("numpy==2.3.5", "Pillow==12.3.0")
DEPENDENCY_CACHE = ROOT / "artifacts/local_release_dependency_cache"
DEFAULT_TESTS = (
    "test_auto_router", "test_host_runtime", "test_live_service", "test_live_spatial_mcp",
    "test_task_verification", "test_mcp_goal_verification", "test_strict_execution_collision",
    "test_scene_cache", "test_attention_policy", "test_attention_cache_flow", "test_agent_acceptance",
    "test_task_intent", "test_hook_intent", "test_live_hooks", "test_spatial_index",
    "test_routing_spatial_integration", "test_partial_observation", "test_flow_result_contract",
    "test_scene_rendering", "test_attention_rendering", "test_attention_raster", "test_attention_dwell",
    "test_v1_execution_capabilities", "test_v1_final_boundaries", "test_v1_goal_service", "test_v1_observation_flow",
    "test_query_policy", "test_observation_queries", "test_visual_readability", "test_delivery_pipeline",
    "test_hook_setup_events", "test_hook_bootstrap", "test_observation_reuse", "test_deferred_q4",
    "test_cache_accounting", "test_prepared_render_inputs", "test_contact_section",
    "test_rigid_frame_contract", "test_preparation_rejection", "test_extreme_engine_boundaries",
)
INSTALLED_TEST_EXCLUSIONS = {
    'verification.test_attention_raster.AttentionRasterTests.test_real_blender_tiny_yaw_snapshot_has_both_witnesses_supported':
        'Requires sealed historical Blender snapshot; full project regression owns this case. Installed tests retain synthetic raster cases without copying old live material.',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def child_environment():
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    for key in list(env):
        if key.startswith("PIP_"):
            env.pop(key, None)
    for key in ("PYTHONPATH", "PYTHONHOME", "HUMAN_EYE_CONFIG"):
        env.pop(key, None)
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INPUT="1")
    return env


def public_evidence(value, stage):
    """Keep path relationships in the ZIP; retain full local proof separately."""
    replacements = []
    for path, marker in ((Path(stage), "<BUILD_WORKDIR>"), (ROOT, "<SOURCE_CHECKOUT>"),
                         (Path(sys.base_prefix), "<BUILD_PYTHON>")):
        replacements.extend(((str(path), marker), (path.as_posix(), marker)))
    def visit(item):
        if isinstance(item, str):
            for source, destination in replacements:
                item = item.replace(source, destination)
            return item
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        return item
    return visit(value)


def run(executable, arguments, cwd, *, input=None, timeout=180, allow_failure=False):
    result = subprocess.run([str(executable), "-B", *map(str, arguments)], cwd=cwd,
        env=child_environment(), input=input, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode and not allow_failure:
        raise RuntimeError("Child process failed: " + result.stdout + result.stderr)
    return result


def runtime_files():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    files = [name + ".py" for name in project["tool"]["setuptools"]["py-modules"]]
    for package in project["tool"]["setuptools"]["packages"]:
        files.extend(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / package).glob("*.py")))
    return project, sorted(set(files))


def new_release_identity(suffix=None):
    if suffix is None:
        suffix = "t" + datetime.now(timezone.utc).strftime("%H%M%S") + "." + secrets.token_hex(3)
    if not re.fullmatch(r"[a-z0-9]+(?:\.[a-z0-9]+)*", suffix):
        raise ValueError("Suffix must contain lowercase alphanumeric dot-separated labels")
    # PEP 440 removes leading zeroes from fully numeric local-version labels.
    suffix = ".".join(str(int(part)) if part.isdigit() else part for part in suffix.split("."))
    version = VERSION_PREFIX + "." + suffix
    name = NAME_PREFIX + "." + suffix
    return version, name


def audit_engine_wheel(wheel, source, files, version):
    """Bind installed Python/data/entry points to the allowlisted source copy."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if archive.testzip() is not None or len(names) != len(set(names)):
            raise RuntimeError("Engine wheel has corrupt or duplicate members")
        python_members = {name for name in names if name.endswith('.py')}
        if python_members != set(files):
            raise RuntimeError("Wheel Python inventory differs from declared runtime sources")
        for relative in [*files, "human_eye_plugin/plugin.json", "human_eye_plugin/mcp_config.json"]:
            if archive.read(relative) != (source / relative).read_bytes():
                raise RuntimeError("Wheel differs from staged source/data: " + relative)
        metadata = archive.read(next(name for name in names if name.endswith('.dist-info/METADATA'))).decode().splitlines()
        if ("Version: " + version not in metadata
                or not any(line.startswith('Requires-Dist: numpy') for line in metadata)
                or not any(line.startswith('Requires-Dist: Pillow') for line in metadata)):
            raise RuntimeError("Wheel metadata omits version/dependencies")
        entries = archive.read(next(name for name in names if name.endswith('.dist-info/entry_points.txt'))).decode()
        for name in ("human-eye-mcp-server", "human-eye-live"):
            if name + " = human_eye_plugin.production_server:main" not in entries:
                raise RuntimeError("Wheel console entry is not the production server: " + name)
        if 'human-eye-hook = human_eye_hook:main' not in entries:
            raise RuntimeError('Wheel hook console entry is not the lightweight bootstrap')
    return {"runtime_python_files": len(files), "source_data_files": 2,
            "entry_points_checked": ["human-eye-mcp-server", "human-eye-live", "human-eye-hook"], "passed": True}


def validate_public_text(text, *, label):
    """Reject local checkout/account references in public text, not binary deps."""
    forbidden = {str(ROOT), ROOT.as_posix(), str(Path.home()), Path.home().as_posix()}
    folded = text.casefold().replace('\\', '/')
    if any(value.casefold().replace('\\', '/') in folded for value in forbidden):
        raise RuntimeError("Public bundle text contains a local account/workspace path: " + label)


def release_project(source, version):
    document = tomllib.loads(source)
    scripts = document["project"]["scripts"]
    for key in ("human-eye-mcp-server", "human-eye-live"):
        if scripts.get(key) != "human_eye_plugin.production_server:main":
            raise ValueError("Production console script must use production_server: " + key)
    if scripts.get('human-eye-hook') != 'human_eye_hook:main':
        raise ValueError('Hook console script must use human_eye_hook:main')
    source, count = re.subn(r'(?m)^version\s*=\s*"[^"\r\n]+"\s*$',
                            'version = "' + version + '"', source, count=1)
    if count != 1:
        raise ValueError("Cannot identify project version")
    source = re.sub(r'(?m)^requires-python\s*=\s*"[^"\r\n]+"\s*$',
                    'requires-python = ">=3.11"', source, count=1)
    result = tomllib.loads(source)
    if result["project"]["version"] != version:
        raise ValueError("Release metadata version failed to update")
    return source


def identity_from(executable, source_root, *, cwd):
    code = ("import json,sys;sys.path.insert(0," + repr(str(source_root)) + ");"
        "from human_eye_plugin.runtime_identity import runtime_identity;"
        "print(json.dumps(runtime_identity(mode='live')))" )
    return json.loads(run(executable, ["-I", "-c", code], cwd).stdout)


def dependency_wheels():
    DEPENDENCY_CACHE.mkdir(parents=True, exist_ok=True)
    names = {"numpy": "2.3.5", "pillow": "12.3.0"}
    found = {}
    for path in DEPENDENCY_CACHE.glob("*.whl"):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("Corrupt cached dependency wheel: " + path.name)
            metadata = archive.read(next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))).decode()
            name = next(line.split(": ", 1)[1].lower() for line in metadata.splitlines() if line.startswith("Name: "))
            version = next(line.split(": ", 1)[1] for line in metadata.splitlines() if line.startswith("Version: "))
            if name in names and version == names[name]:
                if "cp312-cp312-win_amd64" not in path.name:
                    raise ValueError("Local offline dependencies must match CPython3.12/Windows AMD64")
                if name in found:
                    raise ValueError("Ambiguous cached dependency wheels")
                found[name] = path
    if set(found) != set(names):
        raise FileNotFoundError("Download exact dependency wheels first: python -m pip download --only-binary=:all: --no-deps "
            "--index-url https://pypi.org/simple --dest artifacts/local_release_dependency_cache " + " ".join(DEPENDENCIES))
    return [found[name] for name in sorted(found)]


SMOKE_SOURCE = r'''"""Windows installed-wheel checks, no model requests or Blender connection."""
import argparse
import copy
import base64
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import pkgutil
import sys
import sysconfig

import numpy as np
import PIL
from PIL import Image
from human_eye_module1_operators import MeshEntity3D
import human_eye_plugin
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from human_eye_plugin.geometry_safety import measure_pair_geometry
from human_eye_plugin.runtime_identity import runtime_identity


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--tests-root', type=Path)
    parser.add_argument('--output-dir', type=Path)
    args=parser.parse_args()
    installed=Path(sysconfig.get_path('purelib')).resolve()
    distribution=importlib.metadata.distribution('human-eye-spatial-plugin')
    assert distribution.version==args.expected_version
    loaded={}
    names=['human_eye_module1_operators']
    names += [str(item)[:-3] for item in distribution.files or ()
              if str(item).endswith('.py') and '/' not in str(item) and '\\' not in str(item)]
    names += ['human_eye_plugin.'+item.name for item in pkgutil.iter_modules(human_eye_plugin.__path__)]
    for name in names:
        module=importlib.import_module(name)
        assert Path(module.__file__).resolve().is_relative_to(installed), (name,module.__file__)
        loaded[name]=str(Path(module.__file__).resolve())
    assert Path(np.__file__).resolve().is_relative_to(installed)
    assert Path(PIL.__file__).resolve().is_relative_to(installed)
    dependency_records={}
    for name in ('numpy','Pillow','human-eye-spatial-plugin'):
        info=importlib.metadata.distribution(name)
        checked,unhashed=0,0
        for item in info.files or ():
            path=Path(info.locate_file(item))
            assert path.is_file(),(name,str(item),'missing_installed_file')
            if item.hash:
                digest=hashlib.new(item.hash.mode,path.read_bytes()).digest()
                assert base64.urlsafe_b64encode(digest).rstrip(b'=').decode()==item.hash.value,(name,str(item),'record_hash_mismatch')
                checked+=1
            else:unhashed+=1
        assert checked>0
        dependency_records[name]={'record_hashes_verified':checked,'unhashed_record_entries':unhashed,'missing_files':0}
    import io
    image=Image.new('RGB',(4,4),(1,2,3));buffer=io.BytesIO();image.save(buffer,format='PNG')
    assert Image.open(io.BytesIO(buffer.getvalue())).getpixel((0,0))==(1,2,3)
    assert np.allclose(np.eye(4) @ np.ones((4,4)),np.ones((4,4)))
    identity=runtime_identity(mode='live')
    assert identity['source_kind']=='installed_distribution',identity
    assert identity['distribution_version']==args.expected_version
    examples=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('_local_route_corpus',examples/'agent_acceptance.py')
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    routing=audit.route_corpus(examples/'route_corpus.json')
    assert routing['total']==100 and routing['all_required_expectations_met'],routing
    scene=audit.fixture_scene()
    router=HumanEyeAutoRouter(quad_size=64)
    observed=router.handle_event({'event':'before_model','session_id':'local-package',
        'task_kind':'spatial_3d','focal_id':'part','reference_id':'base','scene':scene,'include_image':False})
    assert observed['route']=='engine',observed
    facts=json.loads(observed['context_text'])
    assert abs(facts['measurement']['signed_clearance_m']-.1)<1e-10
    blocked=router.handle_event({'event':'before_action','session_id':'local-package',
        'focal_id':'part','reference_id':'base','observation_id':observed['observation_id'],
        'action':{'translation':[0,0,-.10005]}})
    assert blocked['allow_action'] is False,blocked
    assert 'candidate_collision' in blocked['reason_codes'],blocked
    part=MeshEntity3D.from_dict(scene['meshes'][1]).translated([0,0,-.10005])
    exact=measure_pair_geometry(part,MeshEntity3D.from_dict(scene['meshes'][0]),need_clearance=True)
    assert exact['measurement_valid'] and exact['is_penetrating']
    # Keep an actual rendered engine image, from a public synthetic fixture.
    near_scene=copy.deepcopy(scene)
    near_scene['revision']='installed-synthetic-near-gap'
    target=next(mesh for mesh in near_scene['meshes'] if mesh['object_id']=='part')
    for point in target['vertices']:point[2]-=.098
    if target.get('pivot_world') is not None:target['pivot_world'][2]-=.098
    near_result=HumanEyeAutoRouter(quad_size=128).handle_event({'event':'before_model',
        'session_id':'installed-visual','task_kind':'spatial_3d','focal_id':'part',
        'reference_id':'base','scene':near_scene,'include_image':True})
    assert near_result['route']=='engine' and near_result.get('image'),near_result
    png=base64.b64decode(near_result['image']['data'],validate=True)
    with Image.open(io.BytesIO(png)) as picture:
        picture.load();assert picture.size==(256,256) and picture.format=='PNG'
    image_root=args.output_dir or examples/'local_test_outputs'
    image_root.mkdir(parents=True,exist_ok=True)
    image_path=image_root/'synthetic_near_gap.png'
    image_path.write_bytes(png)
    visual_facts=json.loads(near_result['context_text'])
    synthetic_visual={'file':str(image_path.resolve()),'sha256':hashlib.sha256(png).hexdigest(),
        'size':[256,256],'provenance':'public synthetic box fixture; not Blender or model output',
        'canvas':visual_facts.get('canvas'),'attention':visual_facts.get('attention')}
    result={'passed':True,'runtime_identity':identity,'routing_corpus':routing,
        'strict_geometry':exact,'collision_action_rejected':True,'installed_module_paths':loaded,
        'dependency_paths':{'numpy':str(np.__file__),'Pillow':str(PIL.__file__)},
        'dependency_versions':{'numpy':np.__version__,'Pillow':PIL.__version__},
        'dependency_record_integrity':{name:dependency_records[name] for name in ('numpy','Pillow')},
        'engine_record_integrity':dependency_records['human-eye-spatial-plugin'],
        'synthetic_visual':synthetic_visual,'numpy_pillow_native_operations':True,
        'isolated_prefix':sys.prefix,'base_prefix':sys.base_prefix,'sys_path':sys.path,
        'model_api_calls':0,'blender_contacted':False,'linux_container_executed':False}
    if args.tests_root:
        import io,unittest
        sys.path.insert(0,str(args.tests_root.resolve()))
        test_list=json.loads((args.tests_root/'selected_tests.json').read_text(encoding='utf-8'))
        exclusions=json.loads((args.tests_root/'excluded_tests.json').read_text(encoding='utf-8'))
        suite=unittest.TestSuite();excluded=[]
        def cases(suite):
            for item in suite:
                if isinstance(item,unittest.TestSuite):yield from cases(item)
                else:yield item
        for name in test_list:
            loaded_suite=unittest.defaultTestLoader.loadTestsFromName('verification.'+name)
            for case in cases(loaded_suite):
                if case.id() in exclusions:excluded.append({'test':case.id(),'reason':exclusions[case.id()]})
                else:suite.addTest(case)
        stream=io.StringIO();tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        result['installed_regressions']={'tests':tests.testsRun,'passed':tests.wasSuccessful(),
            'selected_modules':test_list,'explicit_exclusions':excluded,
            'fixture_adaptations':json.loads((args.tests_root/'fixture_adaptations.json').read_text(encoding='utf-8')),
            'output':stream.getvalue()}
        assert tests.wasSuccessful(),stream.getvalue()
        for name,module in list(sys.modules.items()):
            if (name=='human_eye_foveated_renderer' or name.startswith(('human_eye_plugin','human_eye_module1_operators','module_2_','module_3_'))):
                location=getattr(module,'__file__',None)
                if location:assert Path(location).resolve().is_relative_to(installed),(name,location)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
'''


def readme(version, identity, engine_wheel, dependency_names):
    return f"""# Human Eye 本地测试包

本包版本：`{version}`；基础API版本：`{identity['base_version']}`；实现revision：`{identity['implementation_revision']}`。
实际源码身份以`BUILD_INFO.json`和MCP握手的`build_id`为准。这是新的rigid.frame本地测试包，与adaptive.perception、perf.repair、flow.complete、routing/spatial和已上传的attention/cache旧包分开，未自动上传或替换旧包。

本地离线依赖附带Windows AMD64 / CPython3.12 的 NumPy 2.3.5 与 Pillow 12.3.0 wheels。引擎wheel本身是纯Python包。本轮只声明Windows本地安装验收；没有实跑Linux、Docker、远程宿主或模型评测。

## 本地安装与检查

在解压后的包根目录，使用64位Python3.12：

```powershell
python verify_bundle.py
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install --no-index --find-links dependency_wheels wheels/{engine_wheel}
.\\.venv\\Scripts\\python.exe -I examples/local_test.py --expected-version {version}
```

本地检查包含100条离线路由语料、严格碰撞候选拒绝，以及保存实际引擎PNG的合成近间隙场景。未连接Blender，也不能证明实际agent收到了图片。完整安装后回归覆盖范围化结果、partial观察不授动作权限、查询策略、视觉可读性和准备/回读交付流水线，模块及来源路径见`validation/installation.json`。`validation/synthetic_near_gap.png`是隔离安装时的合成图，不是宿主实战证据。依赖wheel：{', '.join(dependency_names)}。

本轮还验收标准库hook入口、按事件注册的可信`--event`、观察缓存/几何支持复用边界，以及延后绘制Q4的兼容回退。`human-eye-hook`对应顶层`human_eye_hook:main`：普通/unknown和PostToolUse不导入重引擎且不授动作权限，空间观察/PreToolUse仍进入原生产服务。新setup为每事件绑定`--event`，现有合法legacy无该参数的注册保留且不自动重写；旧注册对无法解析stdin的限制不能冒称已经消除。

本轮修复了非盒体的明确世界坐标刚体操作被旧面向对齐检查误拒的问题。新增`rigid_frame_valid`，要求明确的宿主来源、有限正交右手轴和实际枢轴；旧`measurement.axes_valid`与角度目标检查保留原含义。坐标系有效不等于动作获准，当前完整场景的实体支持、预算、碰撞、版本和实际回读仍逐一检查。准备阶段已知拒绝保留具体原因，且不先创建无法执行的操作日志。

继续提供观察缓存增量计账、操作内渲染输入复用，以及显式可选的`query.visual_diagnostic="contact_section"`接触剖面。剖面放在原四个自然视图旁，来自真实网格与平面求交；它是诊断图，不是自然视角、真实可见空缝、实体占用分类或动作许可。所有对象参与求交，预算/未知/退化状态须按证据解释；数值尺寸标注不等于独立真值。默认查询不附加剖面。这些回归不能据此宣称模型收益或普适性能提升。

安装回归不复制历史实战或私有盲题快照；需要旧封存Blender快照的一个raster回归方法由项目全量检查承担，安装结果中明确列出其排除原因，其余合成raster反例照常执行。

## 默认生产入口

```powershell
.\\.venv\\Scripts\\python.exe -m human_eye_plugin.production_server --config config/live-connector.example.json
```

这个入口使用stdio MCP，必须有可信配置；连接失败不回退演示。正式连接需要另外启动同机Blender及BlenderMCP服务，并确保引擎source目录可读。示例配置的相对路径基于配置文件所在目录，运行状态写到解压目录的runtime子目录。先复制配置到独立目录再按实际路径配置，避免覆盖已有连接状态。

安装新包不会重载已运行的agent MCP进程。重载后核对握手revision/build_id；示例配置已固定本包的实现与build_id，版本不符时保持拒绝执行。

独立JSONL宿主可运行`python -m human_eye_plugin.router_server`，事件和实际场景由宿主提供。显式`production_server --demo`仅用于旧合成演示；其工具/场景不等于实时能力。

## 验收边界

路由命中、原生图片载荷生成、实际宿主触发、模型消费图片、执行一致性和任务成功是不同检查。空间粗筛只提供保守下界/候选，精确量测和执行检查应按证据字段解释。未知或超预算继续拒绝，不静默简化网格。检查候选终态不保证运动途中安全；默认GPU计算、视觉微调和通用凹体支持均不能从本包推定。

自动注意力通过采样、可见性和实际成本检查后采用，hold属于正常结果。缓存对持续变化场景可能有负收益。新版本没有继承旧实验的模型成功率；本轮未包含私有双盲材料、答案或Agent Learning知识。

历史routing/spatial开发基准属于旧实现和受限场景，本包不沿用其百分比作为新版本收益。粗筛次数减少、避免准备图、几何可测与图像可读分别核验；渲染、标注和查询语义变化后，不能把不同输出直接当作相同质量的纯提速。新版本的真实宿主收益、图片可读性和模型效果仍需分别提供实测，安装回归本身不证明这些收益。

此前flow.complete与perf.repair性能结果属于旧版本及其采样条件，不作为本包的性能百分比证明。新旧启动/出图/缓存收益需在相同依赖字节码条件下重新采样，失败或退化应保留。

不包含原机器账户、项目设置或运行状态，不修改宿主信任设置。ZIP外侧SHA文件与包内MANIFEST用于检查传输完整性。云端旧包保持原样。
"""


def adapt_installed_test_source(name, source):
    """Adapt a copied standalone-host fixture to the active installed wheel.

    The project test remains untouched. Its standalone import test still opens
    the real installed blender_host.py, including in its isolated subprocess.
    Refuse a changed fixture loader instead of silently reverting to checkout.
    """
    if name == 'test_hook_bootstrap.py':
        original = 'ENTRY = Path(bootstrap.__file__).resolve()\nROOT = ENTRY.parent'
        if source.count(original) != 1:
            raise RuntimeError('Hook bootstrap test root changed; review installed fixture adaptation')
        return source.replace(original, '\n'.join([
            'import sysconfig as _installed_bootstrap_sysconfig',
            original,
            'assert ROOT.is_relative_to(Path(_installed_bootstrap_sysconfig.get_path("purelib")).resolve()), "Hook fixture must inspect installed bootstrap"',
        ]))
    if name != 'test_blender_host_contracts.py':
        return source
    original = 'MODULE_PATH = Path(__file__).resolve().parents[1] / "human_eye_plugin" / "blender_host.py"'
    if source.count(original) != 1:
        raise RuntimeError('Standalone Blender host test loader changed; review installed fixture adaptation')
    replacement = '\n'.join([
        'import sysconfig as _installed_fixture_sysconfig',
        'import human_eye_plugin.blender_host as _installed_fixture_host',
        'MODULE_PATH = Path(_installed_fixture_host.__file__).resolve()',
        'assert MODULE_PATH.is_relative_to(Path(_installed_fixture_sysconfig.get_path("purelib")).resolve()), "Fixture must load installed wheel host"',
    ])
    return source.replace(original, replacement)


def prepare_tests(directory, extra_modules):
    directory.mkdir()
    (directory / "verification").mkdir()
    (directory / "verification/__init__.py").write_text("", encoding="utf-8")
    adaptations = []
    for path in (ROOT / "verification").glob("test_*.py"):
        destination = directory / "verification" / path.name
        if path.name in {'test_blender_host_contracts.py', 'test_hook_bootstrap.py'}:
            destination.write_text(adapt_installed_test_source(path.name, path.read_text(encoding='utf-8')),
                                   encoding='utf-8', newline='\n')
            adaptations.append({'file': path.name, 'original_sha256': sha(path),
                'copied_sha256': sha(destination),
                'reason': 'Test fixture resolves active installed runtime and asserts purelib origin; no runtime source copied to test root.'})
        else:
            shutil.copy2(path, destination)
    shutil.copy2(ROOT / "verification/agent_acceptance.py", directory / "verification/agent_acceptance.py")
    if (ROOT / "verification/measure_spatial_index.py").is_file():
        # The selected index unit tests reuse deterministic fixture builders;
        # the old-runtime benchmark main is never run or shipped in the ZIP.
        shutil.copy2(ROOT / "verification/measure_spatial_index.py", directory / "verification/measure_spatial_index.py")
    (directory / "verification/fixtures").mkdir()
    shutil.copy2(ROOT / "verification/fixtures/agent_routes_v1.json",
                 directory / "verification/fixtures/agent_routes_v1.json")
    (directory / "examples/agents").mkdir(parents=True)
    shutil.copy2(ROOT / "examples/agents/live_entry.py", directory / "examples/agents/live_entry.py")
    modules = list(dict.fromkeys([*DEFAULT_TESTS, *extra_modules]))
    for name in modules:
        if not re.fullmatch(r"test_[a-z0-9_]+", name) or not (directory / "verification" / (name + ".py")).is_file():
            raise ValueError("Selected installed-test module missing: " + name)
    write_json(directory / "selected_tests.json", modules)
    write_json(directory / "excluded_tests.json", INSTALLED_TEST_EXCLUSIONS)
    write_json(directory / "fixture_adaptations.json", adaptations)
    return modules


def validate_install(stage, bundle, wheel, version, dependencies, *, extra_tests):
    env_root = stage / "isolated_venv"
    run(sys.executable, ["-m", "venv", "--copies", env_root], stage, timeout=180)
    executable = env_root / "Scripts/python.exe"
    proof_code = ("import importlib.util,json,sys,sysconfig;"
        "print(json.dumps({'prefix':sys.prefix,'base_prefix':sys.base_prefix,'purelib':sysconfig.get_path('purelib'),"
        "'preinstalled':{n:importlib.util.find_spec(n) is not None for n in ['human_eye_plugin','numpy','PIL']}}))")
    clean = json.loads(run(executable, ["-I", "-c", proof_code], stage).stdout)
    if clean["prefix"] == clean["base_prefix"] or any(clean["preinstalled"].values()):
        raise RuntimeError("Venv unexpectedly shares engine or dependency packages")
    installed = run(executable, ["-I", "-m", "pip", "install", "--no-index", "--no-compile",
        "--find-links", bundle / "dependency_wheels", "--disable-pip-version-check", wheel], stage, timeout=180)
    (stage / "pip_install.log").write_text(installed.stdout + installed.stderr, encoding="utf-8")
    tests = stage / "installed_tests"
    modules = prepare_tests(tests, extra_tests)
    smoke_process = run(executable, ["-I", bundle / "examples/local_test.py", "--expected-version", version,
        "--tests-root", tests, "--output-dir", stage / "installation_visuals"], stage, timeout=180, allow_failure=True)
    (stage / "installed_smoke.stdout.log").write_text(smoke_process.stdout, encoding="utf-8")
    (stage / "installed_smoke.stderr.log").write_text(smoke_process.stderr, encoding="utf-8")
    if smoke_process.returncode:
        raise RuntimeError("Installed-wheel smoke failed; full logs retained in " + str(stage) + ": " + smoke_process.stderr[-8000:])
    smoke = json.loads(smoke_process.stdout)
    identity = smoke["runtime_identity"]
    # These are real module launches in the isolated environment; neither call
    # reads a Blender scene. The configured port is deliberately closed.
    config = stage / "handshake.json"
    write_json(config, {"schema_version": "1.0", "project_root": str(bundle / "source"),
        "state_file": "handshake-state.json", "audit_file": "handshake-audit.jsonl",
        "expected_identity": {"implementation_revision": identity["implementation_revision"], "build_id": identity["build_id"]},
        "quad_size": 64, "blender": {"host": "127.0.0.1", "port": 1, "timeout_s": .1}})
    requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
    wire = "\n".join(json.dumps(item) for item in requests) + "\n"
    process = run(executable, ["-I", "-m", "human_eye_plugin.production_server", "--config", config], stage, input=wire)
    replies = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    handshake = replies[0]["result"]["_meta"]["human_eye"]
    if (handshake["build_id"] != identity["build_id"] or handshake["production_mode"] is not True
            or handshake.get("identity_check", {}).get("compatible") is not True):
        raise RuntimeError("Installed production handshake identity disagrees with installed engine")
    names = {item["name"] for item in replies[1]["result"]["tools"]}
    if names != {"human_eye_scene_observe", "human_eye_transform", "human_eye_connection_status"}:
        raise RuntimeError("Wrong production tool inventory")
    if (stage / "handshake-state.json").exists():
        raise RuntimeError("Pure handshake unexpectedly wrote execution state")
    missing = run(executable, ["-I", "-m", "human_eye_plugin.production_server", "--config", stage / "missing.json"],
        stage, input=wire, allow_failure=True)
    if missing.returncode == 0 or missing.stdout.strip():
        raise RuntimeError("Missing production config unexpectedly served a fallback")
    hook_console = env_root / 'Scripts/human-eye-hook.exe'
    hook = subprocess.run([str(hook_console), '--config', str(config), '--agent', 'codex',
        '--event', 'UserPromptSubmit'], cwd=stage, env=child_environment(),
        input=json.dumps({'hook_event_name': 'UserPromptSubmit', 'session_id': 'local-package-hook',
                         'prompt': '继续'}), capture_output=True, text=True, encoding='utf-8', timeout=30)
    if hook.returncode or json.loads(hook.stdout) != {} or (stage / 'handshake-state.json').exists():
        raise RuntimeError('Installed lightweight console did not skip without state/authority: ' + hook.stderr[-2000:])
    return {"passed": True, "platform": sys.platform, "interpreter": sys.version,
        "isolated_environment_before_install": clean, "isolated_install": smoke,
        "installed_regressions": smoke["installed_regressions"], "selected_tests": modules,
        "production_handshake": handshake, "production_tools": sorted(names),
        'lightweight_hook_console': {'command': str(hook_console), 'event': 'UserPromptSubmit',
            'output': json.loads(hook.stdout), 'returned_without_state': True, 'passed': True},
        "missing_config_rejected_without_demo": True,
        "dependency_install_method": "pip offline wheels in new venv; no system site packages; -I",
        "dependencies": [{"file": path.name, "sha256": sha(path)} for path in dependencies],
        "blender_contacted": False, "model_api_calls": 0, "linux_container_executed": False}


def plan(extra_tests=(), suffix=None):
    version, name = new_release_identity(suffix)
    project, files = runtime_files()
    return {"mode": "read_only_plan", "release_version": version, "name": name,
        "runtime_source_files": len(files), "destination": str(ROOT / "dist" / (name + ".zip")),
        "source_base_version": project["project"]["version"], "default_entry": "human_eye_plugin.production_server --config PATH",
        "dependency_cache": str(DEPENDENCY_CACHE), "dependencies": list(DEPENDENCIES),
        "selected_installed_tests": [*DEFAULT_TESTS, *extra_tests],
        "installed_test_exclusions": INSTALLED_TEST_EXCLUSIONS,
        "evidence_root": str(EVIDENCE_ROOT), "synthetic_render_png_retained": True,
        "required_implementation_revision": EXPECTED_IMPLEMENTATION_REVISION,
        "install_isolation": "fresh Windows CPython3.12 venv; -I; no system-site-packages; neutral cwd",
        "build_requires_explicit_flag": True, "uploads_performed": 0}


def build(*, extra_tests=(), suffix=None):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or sysconfig.get_platform() != "win-amd64":
        raise RuntimeError("This local-test builder requires Windows AMD64 CPython3.12; no Linux claim is made")
    version, name = new_release_identity(suffix)
    project, files = runtime_files()
    destination = ROOT / "dist" / (name + ".zip")
    checksum = destination.with_suffix(".sha256.txt")
    evidence = EVIDENCE_ROOT / name
    if destination.exists() or checksum.exists() or evidence.exists():
        raise FileExistsError("Unique release output already exists; never overwrite it")
    dependencies = dependency_wheels()
    input_files = [ROOT / relative for relative in files]
    input_files += [ROOT / "pyproject.toml", ROOT / "human_eye_plugin/plugin.json", ROOT / "human_eye_plugin/mcp_config.json",
        ROOT / "verification/agent_acceptance.py", ROOT / "verification/fixtures/agent_routes_v1.json", Path(__file__),
        ROOT / "verification/build_release_bundle.py", ROOT / "deployment/cloud/verify_bundle.py",
        ROOT / "deployment/cloud_current/config/live-connector.example.json"]
    input_files += [ROOT / "examples" / relative for relative in (
        "agents/configure.py", "agents/live_entry.py", "agents/hook_entry.py", "blender_worker.py")]
    input_files += list((ROOT / "verification").glob("test_*.py"))
    if (ROOT / "verification/measure_spatial_index.py").is_file():
        input_files.append(ROOT / "verification/measure_spatial_index.py")
    before = {path.relative_to(ROOT).as_posix(): sha(path) for path in input_files}
    old_dist = {path.name: sha(path) for path in (ROOT / "dist").iterdir() if path.is_file()}
    stage = Path(tempfile.mkdtemp(prefix="local_rigid_frame_", dir=ROOT / "artifacts"))
    bundle = stage / name
    bundle.mkdir()
    allowed = set()
    evidence.mkdir(parents=True)
    write_json(evidence / "preservation_before.json", {"dist_sha256": old_dist, "input_sha256": before})

    def add(relative, *, origin=None, text=None):
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if origin is not None:
            shutil.copyfile(origin, path)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
        allowed.add(relative)
        return path

    origin_identity = identity_from(sys.executable, ROOT, cwd=stage)
    if origin_identity['implementation_revision'] != EXPECTED_IMPLEMENTATION_REVISION:
        raise RuntimeError('Runtime is not the intended rigid.frame release; preserve stage and freeze the correct implementation first')
    edits = []
    for relative in files:
        source, count = portable((ROOT / relative).read_text(encoding="utf-8"))
        path = add("source/" + relative, text=source)
        if path.read_bytes() != (ROOT / relative).read_bytes():
            edits.append({"file": relative, "portable_fallback_loops_removed": count,
                          "line_endings_normalized": True})
    add("source/pyproject.toml", text=release_project((ROOT / "pyproject.toml").read_text(encoding="utf-8"), version))
    plugin = json.loads((ROOT / "human_eye_plugin/plugin.json").read_text(encoding="utf-8"))
    plugin.update(version=version, entry="human_eye_plugin.production_server",
        buildRevision=origin_identity["implementation_revision"],
        description="Known-mesh observation with scoped pair goals, read-only partial facts, explicit query policy and guarded endpoint transforms; task benefit requires separate evaluation.")
    add("source/human_eye_plugin/plugin.json", text=json.dumps(plugin, ensure_ascii=False, indent=2) + "\n")
    mcp = {"mcpServers": {"human_eye_live": {"command": "python", "args": ["-m",
        "human_eye_plugin.production_server", "--config", "/ABSOLUTE/PATH/TO/RELEASE/config/live-connector.example.json"]}}}
    add("source/human_eye_plugin/mcp_config.json", text=json.dumps(mcp, indent=2) + "\n")
    add("config/mcp-production.example.json", text=json.dumps(mcp, indent=2) + "\n")
    add("config/live-connector.example.json", origin=ROOT / "deployment/cloud_current/config/live-connector.example.json")
    for relative in ("agents/configure.py", "agents/live_entry.py", "agents/hook_entry.py", "blender_worker.py"):
        add("source/examples/" + relative, origin=ROOT / "examples" / relative)
    add("examples/local_test.py", text=SMOKE_SOURCE)
    add("examples/agent_acceptance.py", origin=ROOT / "verification/agent_acceptance.py")
    add("examples/route_corpus.json", origin=ROOT / "verification/fixtures/agent_routes_v1.json")
    add("requirements.lock.txt", text="\n".join(DEPENDENCIES) + "\n")
    add("verify_bundle.py", origin=ROOT / "deployment/cloud/verify_bundle.py")
    for dependency in dependencies:
        add("dependency_wheels/" + dependency.name, origin=dependency)
    # setuptools needs a readme while building; it is also shipped with source.
    add("source/README.md", text="Human Eye Windows local-test release. Production entry: human_eye_plugin.production_server --config PATH.\n")
    wheels = bundle / "wheels"
    wheels.mkdir()
    run(sys.executable, ["-m", "pip", "wheel", bundle / "source", "--no-deps", "--no-build-isolation",
        "--wheel-dir", wheels, "--disable-pip-version-check"], stage)
    wheel, = wheels.glob("*.whl")
    allowed.add(wheel.relative_to(bundle).as_posix())
    wheel_audit = audit_engine_wheel(wheel, bundle / "source", files, version)
    staged_identity = identity_from(sys.executable, bundle / "source", cwd=stage)
    connector_path = bundle / "config/live-connector.example.json"
    connector = json.loads(connector_path.read_text(encoding="utf-8"))
    connector["expected_identity"] = {"implementation_revision": staged_identity["implementation_revision"],
                                     "build_id": staged_identity["build_id"]}
    connector_path.write_text(json.dumps(connector, indent=2) + "\n", encoding="utf-8")
    checks = validate_install(stage, bundle, wheel, version, dependencies, extra_tests=extra_tests)
    installed_identity = checks["isolated_install"]["runtime_identity"]
    if installed_identity["build_id"] != staged_identity["build_id"]:
        raise RuntimeError("Installed and staged runtime build IDs disagree")
    add("README.md", text=readme(version, installed_identity, wheel.name, [path.name for path in dependencies]))
    add("validation/synthetic_near_gap.png", origin=stage / "installation_visuals/synthetic_near_gap.png")
    add("validation/installation.json", text=json.dumps(public_evidence(checks, stage), ensure_ascii=False, indent=2) + "\n")
    build_info = {"release_version": version, "implementation_revision": installed_identity["implementation_revision"],
        "origin_runtime_identity": origin_identity, "packaged_runtime_identity": installed_identity,
        "staged_runtime_identity": staged_identity, "origin_source_sha256": {relative: before[relative] for relative in files},
        "copy_byte_changes": edits,
        "identity_note": "Origin and packaged build IDs can differ because portable copies normalize source line endings and remove machine-specific fallback import loops. Installed identity is authoritative for this bundle.",
        "default_entry": "human_eye_plugin.production_server --config PATH",
        "offline_dependency_platform": "Windows AMD64 CPython3.12", "source_wheel_python_requirement": ">=3.11",
        "wheel_source_audit": wheel_audit,
        "old_builder_audit": ["Old cloud builder fixes implementation revision to attention-cache",
            "Old source mcp_config copy selects legacy demonstration", "Old README/install record applies to the uploaded historical release only",
            "New builder uses current identity and explicit production config; historical artifacts are preserved"],
        "performance_evidence_scope": {
            "historical_routing_spatial_benchmark_is_not_current_release_evidence": True,
            "new_runtime_speedup_proven_by_packaging": False,
            "observation_bytes_identical": False,
            "model_benefit_proven": False},
        "excluded": ["T04 frozen snapshots/private materials", "user state/configuration/credentials", "Agent Learning knowledge",
                     "private test answers", "host trust changes"],
        "uploads_performed": 0, "linux_container_executed": False,
        "installed_regressions": checks["installed_regressions"]}
    add("BUILD_INFO.json", text=json.dumps(public_evidence(build_info, stage), ensure_ascii=False, indent=2) + "\n")
    forbidden = {".codex", ".human-eye", ".agents", "__pycache__", "AGENTS.md", "auth.json", ".env", "private", "frozen_runtime", "responses"}
    for relative in allowed:
        if any(part in forbidden for part in Path(relative).parts):
            raise RuntimeError("Forbidden bundle path: " + relative)
        if Path(relative).suffix in {'.py','.json','.toml','.md','.txt'}:
            validate_public_text((bundle / relative).read_text(encoding='utf-8'), label=relative)
    manifest = {relative: sha(bundle / relative) for relative in sorted(allowed)}
    add("MANIFEST.json", text=json.dumps({"version": version, "files": manifest}, indent=2) + "\n")
    if not json.loads(run(sys.executable, ["verify_bundle.py"], bundle).stdout)["passed"]:
        raise RuntimeError("Bundle inventory validation failed")
    for relative, expected in before.items():
        if sha(ROOT / relative) != expected:
            raise RuntimeError("Input changed during package validation: " + relative)
    for old, expected in old_dist.items():
        if sha(ROOT / "dist" / old) != expected:
            raise RuntimeError("Historical distribution changed: " + old)
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in sorted(allowed):
            archive.write(bundle / relative, name + "/" + relative)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(allowed):
            raise RuntimeError("New ZIP integrity failed")
        for relative, expected in manifest.items():
            if hashlib.sha256(archive.read(name + "/" + relative)).hexdigest() != expected:
                raise RuntimeError("ZIP member checksum mismatch: " + relative)
    digest = sha(destination)
    with checksum.open("x", encoding="utf-8") as stream:
        stream.write(digest + "  " + destination.name + "\n")
    result = {"passed": True, "release_version": version, "file": destination.name,
        "local_path": str(destination), "checksum_path": str(checksum), "sha256": digest,
        "bytes": destination.stat().st_size, "bundle_files": len(allowed), "stage_path": str(bundle),
        "implementation_revision": installed_identity["implementation_revision"],
        "build_id": installed_identity["build_id"], "origin_build_id": origin_identity["build_id"],
        "installed_regressions": checks["installed_regressions"],
        "routing_corpus": {"total": 100, "matched": checks["isolated_install"]["routing_corpus"]["matched"]},
        "historical_dist_preserved": old_dist, "engine_source_unchanged": True,
        "windows_local_install_tested": True, "linux_container_executed": False,
        "blender_contacted_in_packaging": False, "model_api_calls": 0, "uploads_performed": 0}
    write_json(evidence / "build_result.json", result)
    write_json(evidence / "installation.json", checks)
    write_json(evidence / "build_info.json", build_info)
    print(json.dumps({key: value for key, value in result.items() if key not in {"installed_regressions", "historical_dist_preserved"}}, ensure_ascii=False))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Build only after all runtime writers have stopped")
    parser.add_argument("--suffix", help="Unique lowercase dot-separated build suffix; default UTC time plus random nonce")
    parser.add_argument("--test-module", action="append", default=[], help="Additional installed-wheel unittest module, without verification prefix")
    args = parser.parse_args(argv)
    if args.build:
        build(extra_tests=args.test_module, suffix=args.suffix)
    else:
        print(json.dumps(plan(args.test_module, args.suffix), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
