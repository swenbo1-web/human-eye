"""Fresh bounded Python execution over the supplied current geometry only."""

import ast
import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
DEPS = HERE.parent / "m6_shape_pretrain_001/private/deps"
ALLOWED_MODULES = {"numpy", "numpy.linalg", "math", "statistics", "json", "collections", "itertools",
                   "functools", "scipy", "scipy.spatial", "scipy.sparse", "scipy.sparse.csgraph", "scipy.sparse.linalg", "scipy.linalg", "scipy.ndimage"}
DENIED_ATTRIBUTES = {"load", "save", "savez", "savez_compressed", "loadtxt", "savetxt", "genfromtxt",
                     "fromfile", "tofile", "memmap", "open_memmap", "DataSource", "ctypes", "ctypeslib",
                     "f2py", "test", "dump", "read", "write", "open", "io"}


def validate_code(code):
    tree = ast.parse(code, filename="<consumer-python>", mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and ((node.attr.startswith("_") and node.attr not in {"__name__", "__version__"}) or node.attr in DENIED_ATTRIBUTES):
            raise ValueError("attribute_outside_geometry_execution_scope")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("private_introspection_outside_geometry_execution_scope")
        if isinstance(node, ast.Import):
            if any(alias.name not in ALLOWED_MODULES for alias in node.names):
                raise ValueError("import_outside_geometry_execution_scope")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in ALLOWED_MODULES or any(alias.name.startswith("_") or alias.name in DENIED_ATTRIBUTES for alias in node.names):
                raise ValueError("import_outside_geometry_execution_scope")
            if node.module == "scipy" and any(alias.name not in {"spatial", "sparse", "ndimage"} for alias in node.names):
                raise ValueError("scipy_submodule_outside_geometry_execution_scope")
    return tree


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or (name not in ALLOWED_MODULES and not name.startswith(("numpy.", "scipy."))):
        raise ImportError("module_outside_geometry_execution_scope(" + name + ")")
    return __import__(name, globals, locals, fromlist, 0)


def lifetime_metrics():
    if os.name != "nt":
        return {"CPU_s": time.process_time(), "peak_working_set_bytes": None}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
    ctypes.windll.psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    return {"CPU_s": time.process_time(), "peak_working_set_bytes": int(counters.PeakWorkingSetSize) if ok else None}


def worker():
    started = time.perf_counter()
    payload = json.loads(sys.stdin.buffer.read())
    sys.path.insert(0, str(DEPS))
    import numpy as np
    arrays = payload["arrays"]
    vertices = np.asarray(arrays["vertices"], dtype=np.float64)
    faces = np.asarray(arrays["faces"], dtype=np.int64)
    F_ids = np.asarray(arrays["F_ids"], dtype=np.int64)
    target_ids = np.asarray(arrays["target_ids"], dtype=np.int64)
    protected_ids = np.asarray(arrays["protected_ids"], dtype=np.int64)
    for value in (vertices, faces, F_ids, target_ids, protected_ids):
        value.flags.writeable = False
    names = ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len", "list", "type",
             "map", "max", "min", "next", "print", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip",
             "Exception", "ValueError", "TypeError", "RuntimeError", "IndexError", "KeyError", "ZeroDivisionError", "AssertionError", "AttributeError")
    import builtins
    safe_builtins = {name: getattr(builtins, name) for name in names}
    safe_builtins["__import__"] = safe_import
    namespace = dict(__builtins__=safe_builtins, np=np, V=vertices, vertices=vertices, faces=faces,
                     F_ids=F_ids, target_ids=target_ids, protected_ids=protected_ids,
                     geometry=dict(vertices=vertices, faces=faces, F_ids=F_ids, target_ids=target_ids, protected_ids=protected_ids),
                     task=payload["task"])
    stdout, stderr = io.StringIO(), io.StringIO()
    error = None
    try:
        tree = validate_code(payload["code"])
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compile(tree, "<consumer-python>", "exec"), namespace, namespace)
    except BaseException as exception:
        error = {"type": type(exception).__name__, "message": str(exception)}
    result = dict(stdout=stdout.getvalue(), stderr=stderr.getvalue(), error=error,
                  worker_wall_s_before_write=time.perf_counter()-started, process=lifetime_metrics())
    sys.stdout.write(json.dumps(result, ensure_ascii=True, allow_nan=False) + "\n")


def execute(code, case_path, audit_path, python=None, timeout_s=20, output_chars=12000):
    """Run one fresh process and retain complete output before public truncation."""
    started = time.perf_counter()
    import numpy as np
    case_path, audit_path = Path(case_path), Path(audit_path)
    audit_path.mkdir(parents=True, exist_ok=False)
    task = json.loads((case_path / "task.json").read_bytes())
    if task.get("input_file") != "input.npz":
        raise ValueError("fixed_current_input_filename_required")
    with np.load(case_path / "input.npz", allow_pickle=False) as source:
        arrays = {key: source[key].tolist() for key in ("vertices", "faces", "F_ids", "target_ids", "protected_ids")}
    payload = dict(code=code, arrays=arrays, task=task)
    raw = (json.dumps(payload, ensure_ascii=True, allow_nan=False) + "\n").encode("utf8")
    (audit_path / "CODE.py").write_text(code, encoding="utf8", newline="\n")
    env = dict(os.environ)
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    python = str(python or sys.executable)
    command = [python, "-I", "-B", "-X", "utf8", str(HERE / "python_sandbox.py"), "--worker"]
    record = dict(command=command, input_JSON_bytes=len(raw), code_UTF8_bytes=len(code.encode("utf8")),
                  timeout_s=timeout_s, status="running", returncode=None, error=None)
    process = None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=audit_path, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record["pid"] = process.pid
        stdout, stderr = process.communicate(raw, timeout=timeout_s)
        (audit_path / "STDOUT.bin").write_bytes(stdout)
        (audit_path / "STDERR.bin").write_bytes(stderr)
        record["returncode"] = process.returncode
        if process.returncode:
            raise RuntimeError("python_worker_nonzero")
        complete = json.loads(stdout)
        public = {key: complete[key] for key in ("stdout", "stderr", "error")}
        record.update(status="completed", worker=complete)
        for field in ("stdout", "stderr"):
            text = public[field]
            if len(text) > output_chars:
                public[field] = text[:output_chars] + "\n[output truncated]"
        record["public_truncated"] = any(len(complete[key]) > output_chars for key in ("stdout", "stderr"))
        record["complete_stdout_UTF8_bytes"] = len(complete["stdout"].encode("utf8"))
        record["complete_stderr_UTF8_bytes"] = len(complete["stderr"].encode("utf8"))
    except subprocess.TimeoutExpired as exception:
        if process is not None and process.poll() is None:
            if os.name == "nt":
                try:
                    cleanup = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],capture_output=True,timeout=5,
                                             creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                    record["timeout_tree_kill_returncode"] = cleanup.returncode
                except (OSError,subprocess.TimeoutExpired) as cleanup_error:
                    record["timeout_tree_kill_error"] = type(cleanup_error).__name__
            if process.poll() is None:
                process.kill()
        stdout, stderr = process.communicate(timeout=3) if process is not None else (exception.stdout or b"", exception.stderr or b"")
        (audit_path / "STDOUT.bin").write_bytes(stdout)
        (audit_path / "STDERR.bin").write_bytes(stderr)
        record.update(status="timeout", error={"type": "TimeoutExpired", "message": "bounded_python_execution_deadline"})
        record["returncode"] = process.returncode if process is not None else None
        public = dict(stdout="", stderr="", error=record["error"])
    except BaseException as exception:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        record.update(status="failed", error={"type": type(exception).__name__, "message": str(exception)})
        public = dict(stdout="", stderr="", error={"type": type(exception).__name__, "message": "python_execution_failed_see_private_audit"})
    record["wall_s"] = time.perf_counter()-started
    (audit_path / "EXECUTION.json").write_text(json.dumps(record, ensure_ascii=True, indent=2, allow_nan=False)+"\n",encoding="utf8",newline="\n")
    return public, record


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("use_as_module_or_with_worker_protocol")
    worker()
