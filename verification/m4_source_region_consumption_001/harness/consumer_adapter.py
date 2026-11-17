"""Fresh sealed-observation consumers through the accepted Pro CLI loop.

Import and adapter construction perform local source reads only. Root owns
the actual call to consume and its original task and lifecycle deadlines.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import types


HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
ROOT = HERE.parents[2]
BASE = Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
BASE_SHA256 = "50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869"
CLI = Path("C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe")
CLI_SHA256 = "01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6"
ACCEPTED = ROOT / "verification/m4_consumer_error_contract_001/consumer.py"
SERVER = HERE / "read_observation.py"
TOOLS_BY_GROUP = {"C": frozenset({"read_observation"})}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def fresh_argv(argv, expected_thread_id=None):
    """Keep the ephemeral fresh command and reject every resume entry."""
    command = list(argv)
    if expected_thread_id is not None:
        raise ValueError("fresh_consumer_has_no_resume_entry")
    if (len(command) < 3 or command[1] != "exec" or command[-1] != "-"
            or "--ephemeral" not in command
            or any(value in command for value in ("resume", "fork", "--last", "--all"))):
        raise ValueError("fresh_ephemeral_exec_command_required")
    return command


def consumer_adapter():
    """Return the original event-loop code with this batch's private globals."""
    specification = importlib.util.spec_from_file_location(
        "_source_region_accepted_consumer", ACCEPTED)
    accepted = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = accepted
    specification.loader.exec_module(accepted)

    def initial_argv(python, cell_path, work, final, group):
        if group != "C" or Path(python).resolve() != BASE.resolve():
            raise ValueError("fixed_consumer_group_and_base_Python")
        if sha(BASE) != BASE_SHA256 or sha(CLI) != CLI_SHA256:
            raise ValueError("fixed_CLI_or_Python_bytes_changed")
        cell = read(cell_path)
        if cell["group"] != group or sha(cell["input_file"]) != cell["input_sha256"]:
            raise ValueError("bound_sealed_input_changed")
        config = accepted.legacy.previous.settings()
        config["mcp_servers.arm_engine"] = {
            "command": str(BASE),
            "args": ["-I", "-B", "-X", "utf8", str(SERVER),
                     "--input", cell["input_file"], "--input-sha256", cell["input_sha256"],
                     "--owner", cell["audit_dir"],
                     "--audit", str(Path(cell_path).parent / "attachments"),
                     "--deadline-ns", str(cell["task_deadline_ns"])],
            "cwd": str(work), "required": True,
            "startup_timeout_sec": 60, "tool_timeout_sec": 450,
            "tools": {"read_observation": {"approval_mode": "approve"}},
        }
        command = [str(CLI), "exec", "--ignore-user-config", "--ignore-rules",
                   "--ephemeral", "--strict-config", "--json", "--skip-git-repo-check",
                   "-C", str(work), "--color", "never"]
        for key, value in config.items():
            command.extend(["-c", key + "=" + accepted.legacy.previous.toml(value)])
        return command + ["-m", "gpt-6.1-sol", "-o", str(final), "-"]

    original_cli = accepted.consume_turn.__globals__["cli"]
    fresh_cli = types.SimpleNamespace(
        argv_for_turn=fresh_argv,
        summarize_turn=original_cli.summarize_turn,
        TURN_LABELS=original_cli.TURN_LABELS,
    )
    namespace = dict(accepted.consume_turn.__globals__)
    namespace.update(initial_argv=initial_argv, archive_turn=accepted.archive_turn,
                     TOOLS_BY_GROUP=TOOLS_BY_GROUP, cli=fresh_cli)
    consume_turn = types.FunctionType(
        accepted.consume_turn.__code__, namespace, accepted.consume_turn.__name__,
        accepted.consume_turn.__defaults__, accepted.consume_turn.__closure__)
    consume_turn.__kwdefaults__ = dict(accepted.consume_turn.__kwdefaults__ or {})
    proof = {
        "schema": "m4-source-region-consumption-001-consumer-adapter-v1",
        "adapter_path": str(Path(__file__).resolve()),
        "adapter_sha256": sha(__file__),
        "accepted_consumer_path": str(ACCEPTED),
        "accepted_consumer_sha256": sha(ACCEPTED),
        "event_loop_path": accepted.consume_turn.__code__.co_filename,
        "event_loop_sha256": sha(accepted.consume_turn.__code__.co_filename),
        "event_loop_code_reused": consume_turn.__code__ is accepted.consume_turn.__code__,
        "unified_archive_reused": consume_turn.__globals__["archive_turn"] is accepted.archive_turn,
        "result_matcher_path": accepted.result_contract.__file__,
        "result_matcher_sha256": sha(accepted.result_contract.__file__),
        "settings_path": accepted.legacy.previous.__file__,
        "settings_sha256": sha(accepted.legacy.previous.__file__),
        "safe_environment_reused": consume_turn.__globals__["safe_environment"] is accepted.safe_environment,
        "summarize_turn_reused": fresh_cli.summarize_turn is original_cli.summarize_turn,
        "fresh_ephemeral_argv_adapter": True,
        "resume_entry_available": False,
        "server_path": str(SERVER),
        "server_sha256": sha(SERVER),
        "CLI_path": str(CLI), "CLI_sha256": CLI_SHA256,
        "Python_path": str(BASE), "Python_sha256": BASE_SHA256,
        "model": "gpt-6.1-sol", "reasoning_effort": "medium", "service_tier": "default",
        "configuration": "Explicit strict CLI overrides with user configuration and rules ignored; original settings and environment filter retained.",
        "authentication": "Existing global ChatGPT login read by CLI; credential files stay outside the adapter and archive.",
        "business_tool_cap": 4,
        "business_tool_cap_enforcement": "Thin-server admission and root checks enforce four attempts/admissions; inherited twelve-call event-loop guard is preserved.",
        "model_calls_during_adapter_construction": 0,
    }
    return consume_turn, proof


def consume(slot_root, case, task_deadline_ns, lifecycle_deadline_ns, prompt):
    """Consume one bound case and return its original record with adapter proof.

    case contains input_file and input_sha256. Root supplies original absolute
    monotonic deadlines and serializes S1, S2 and S3. The inherited loop closes
    and archives within the 450-second task deadline. Root owns outer closure.
    """
    now = time.perf_counter_ns()
    if (type(task_deadline_ns) is not int or type(lifecycle_deadline_ns) is not int
            or not now < task_deadline_ns <= lifecycle_deadline_ns):
        raise ValueError("original_absolute_task_and_lifecycle_deadlines")
    if type(prompt) is str:
        prompt = prompt.encode("utf-8")
    if type(prompt) is not bytes:
        raise TypeError("prompt_UTF8_bytes_or_text_required")
    slot_root = Path(slot_root).resolve()
    input_file = Path(case["input_file"]).resolve()
    if sha(input_file) != case["input_sha256"]:
        raise ValueError("bound_sealed_input_changed")
    slot_root.mkdir(parents=True, exist_ok=True)
    endpoint = slot_root / "ENDPOINT.json"
    if endpoint.exists():
        endpoint_value = read(endpoint)
        if (set(endpoint_value) != {"chain_deadline_ns"}
                or not task_deadline_ns <= endpoint_value["chain_deadline_ns"] <= lifecycle_deadline_ns):
            raise ValueError("bound_original_endpoint_deadline")
    else:
        with endpoint.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump({"chain_deadline_ns": lifecycle_deadline_ns}, stream)
            stream.write("\n")
    owner = slot_root / "owner"
    owner.mkdir(exist_ok=True)
    consume_turn, proof = consumer_adapter()
    cell = {
        "endpoint": str(endpoint), "group": "C", "audit_dir": str(owner),
        "input_file": str(input_file), "input_sha256": case["input_sha256"],
        "task_deadline_ns": task_deadline_ns,
    }
    record = consume_turn(
        episode_id="M4-SOURCE-REGION-CONSUMPTION-001-" + slot_root.name,
        turn_index=1, folder=slot_root / "consumer", work=slot_root / "workspace",
        cell=cell, install={"python": str(BASE)}, plan={"model_consumer_enabled": True},
        prompt=prompt, episode_deadline_ns=task_deadline_ns,
        turn_deadline_ns=task_deadline_ns, expected_thread_id=None,
    )
    return {"proof": proof, "record": record}
