"""One-layer reuse of the accepted Pro CLI event, image and archive loop.

Import starts no CLI, model, Blender or raster. The root owns every actual slot.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import types
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
BASE_SHA256 = "50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869"
SEQUENCE = [("A1", "A"), ("B1", "B"), ("B2", "B"), ("A2", "A"), ("A3", "A"), ("B3", "B")]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def clone(function, replacements):
    namespace = dict(function.__globals__)
    namespace.update(replacements)
    derived = types.FunctionType(function.__code__, namespace, function.__name__,
                                 function.__defaults__, function.__closure__)
    derived.__kwdefaults__ = None if function.__kwdefaults__ is None else dict(function.__kwdefaults__)
    return derived


def common_prompt(group):
    if group not in ('A', 'B'):
        raise ValueError("registered_group")
    return (HERE / 'inputs' / ('PROMPT_' + group + '.txt')).read_bytes()


def consumer_adapter():
    accepted_path = ROOT / "verification/m4_consumer_error_contract_001/consumer.py"
    accepted = load("_target_task_accepted_consumer", accepted_path)
    bridge = load("_target_task_public_bridge_schema", HERE / "bridge.py")
    tools = {group: frozenset(row["name"] for row in bridge.public_tools(group)) for group in ("A", "B")}
    interface_path = HERE / "CLI_PREFLIGHT.json"

    def initial_argv(python, cell_path, work, final, group):
        if Path(python).resolve() != BASE.resolve() or sha(BASE) != BASE_SHA256:
            raise ValueError("fixed_base_Python")
        cell = read(cell_path)
        interface = read(interface_path)
        binary = interface["binary"]
        if (binary["sha256"] != "01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6"
                or sha(binary["path"]) != binary["sha256"]):
            raise ValueError("accepted_actual_CLI_changed")
        config = accepted.legacy.previous.settings()
        config["mcp_servers.arm_engine"] = {
            "command": str(BASE), "args": ["-I", "-B", str(accepted.legacy.previous.ATTACH_PATH),
                "--endpoint", cell["endpoint"], "--kind", "native", "--audit", str(Path(cell_path).parent / "attachments")],
            "cwd": str(work), "required": True, "startup_timeout_sec": 60, "tool_timeout_sec": 450,
            "tools": {name: {"approval_mode": "approve"} for name in sorted(tools[group])}}
        argv = [binary["path"], "exec", "--ignore-user-config", "--ignore-rules", "--strict-config",
                "--json", "--skip-git-repo-check", "-C", str(work), "--color", "never"]
        for key, value in config.items():
            argv.extend(["-c", key + "=" + accepted.legacy.previous.toml(value)])
        return argv + ["-m", "gpt-6.1-sol", "-o", str(final), "-"]

    consume = clone(accepted.consume_turn, {"initial_argv": initial_argv, "TOOLS_BY_GROUP": tools})
    proof = {"accepted_consumer_path": str(accepted_path), "accepted_consumer_sha256": sha(accepted_path),
             "event_loop_path": accepted.consume_turn.__code__.co_filename,
             "event_loop_sha256": sha(accepted.consume_turn.__code__.co_filename),
             "event_loop_code_reused": consume.__code__ is accepted.consume_turn.__code__,
             "unified_archive_reused": consume.__globals__["archive_turn"] is accepted.archive_turn,
             "result_matcher_path": accepted.result_contract.__file__,
             "result_matcher_sha256": sha(accepted.result_contract.__file__),
             "settings_path": accepted.legacy.previous.__file__,
             "settings_sha256": sha(accepted.legacy.previous.__file__),
             "thin_attach_path": str(accepted.legacy.previous.ATTACH_PATH),
             "thin_attach_sha256": sha(accepted.legacy.previous.ATTACH_PATH),
             "CLI_preflight_sha256": sha(interface_path), "model": "gpt-6.1-sol",
             "reasoning_effort": "medium", "service_tier": "default",
             "model_calls_during_adapter_creation": 0}
    return consume, proof


def consume_slot(*, slot_id, group, slot_root, endpoint, owner_output, deadline_ns,
                 model_consumer_enabled=False):
    if (slot_id, group) not in SEQUENCE:
        raise ValueError("registered_formal_slot")
    if model_consumer_enabled is not True:
        raise ValueError("root_explicit_consumer_gate")
    consume, proof = consumer_adapter()
    slot_root = Path(slot_root).resolve()
    folder, work = slot_root / "consumer", slot_root / "workspace"
    cell = {"endpoint": str(Path(endpoint).resolve()), "group": group,
            "audit_dir": str(Path(owner_output).resolve())}
    record = consume(episode_id="M5-TASK-CONSUMPTION-001-" + slot_id,
        turn_index=1, folder=folder, work=work, cell=cell, install={"python": str(BASE)},
        plan={"model_consumer_enabled": True}, prompt=common_prompt(group),
        episode_deadline_ns=deadline_ns, turn_deadline_ns=deadline_ns)
    return {"slot_id": slot_id, "group": group, "status": record["status"],
            "consumer_path": str(folder), "consumer_record": str(folder / "CONSUMER.json"),
            "consumer": record, "adapter_proof": proof,
            "source": {"product_source141_sha256": read(HERE / (group + '_RUN_BINDING.json'))['source_sha256'],
                       "common_task_sha256": sha(HERE / "inputs/COMMON_TASK.txt"),
                       "answer_schema_sha256": sha(HERE / "inputs/ANSWER_SCHEMA.json"),
                       "prompt_sha256": hashlib.sha256(common_prompt(group)).hexdigest()},
            "owned": {"owner_output": str(Path(owner_output).resolve()),
                      "scope": "Root attaches its actual owned lifecycle and full-slot publication clocks."}}
