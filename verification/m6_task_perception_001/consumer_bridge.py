"""Per-consumer stdio MCP with equal current-geometry Python access."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from python_sandbox import execute


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False)+"\n",encoding="utf8",newline="\n")


def tool(name, description, properties, required=()):
    return dict(name=name, description=description, inputSchema=dict(type="object",properties=properties,
                required=list(required),additionalProperties=False))


class Bridge:
    def __init__(self, options):
        self.options = options
        self.case = options.case.resolve()
        self.audit = options.audit.resolve()
        self.audit.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.calls = []
        self.interfaces = None
        self.task = json.loads((self.case/"task.json").read_bytes())
        self.identities = {name: hashlib.sha256((self.case/name).read_bytes()).hexdigest() for name in ("task.json","input.npz")}
        self.tools = [tool("execute_python", "Execute ordinary Python in a fresh bounded process over supplied current geometry. "
            "np, V/vertices float64[N,3], faces int64[M,3], F_ids, target_ids, protected_ids, geometry and task are already available. "
            "Current vertices use original full-mesh source indices. numpy, scipy.spatial, scipy.sparse and scipy.sparse.csgraph imports are available. "
            "Each call is fresh. Print compact calculations, use your own algorithms, keep current input unchanged. No local file access.",
            dict(code=dict(type="string")),("code",))]
        if options.route in ("facts", "learned"):
            self.tools += [tool("read_facts", "Read task-facing current geometry facts and region references for this task.", {}),
                           tool("resolve_region", "Read the exact current source-point mapping and geometry for a returned stable region reference.",
                                dict(reference=dict(type="string")),("reference",))]

    def load_interfaces(self):
        if self.interfaces is None:
            spec = importlib.util.spec_from_file_location("_consumer_task_interfaces",HERE/"interfaces.py")
            self.interfaces = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.interfaces)
        return self.interfaces

    def call(self, params):
        mark = time.perf_counter()
        index = len(self.calls)+1
        folder = self.audit / ("tool_"+str(index).zfill(2))
        folder.mkdir(exist_ok=False)
        write(folder/"REQUEST.json",params)
        name, arguments = params.get("name"), params.get("arguments",{})
        record = dict(index=index,name=name,wall_s=None,status="running",public_text_UTF8_bytes=None)
        error = False
        try:
            if index > self.options.max_tool_calls:
                raise RuntimeError("fixed_tool_round_budget_exhausted")
            if name == "execute_python":
                if set(arguments) != {"code"} or type(arguments["code"]) is not str:
                    raise ValueError("code_string_required")
                payload, execution = execute(arguments["code"],self.case,folder/"python",timeout_s=self.options.python_timeout_s,
                                             output_chars=self.options.python_output_chars)
                record["execution"] = execution
                error = payload["error"] is not None
            elif name == "read_facts" and self.options.route in ("facts","learned"):
                if arguments:
                    raise ValueError("read_facts_empty_arguments")
                payload = self.load_interfaces().report(self.case,self.options.route)
            elif name == "resolve_region" and self.options.route in ("facts","learned"):
                if set(arguments) != {"reference"} or type(arguments["reference"]) is not str:
                    raise ValueError("reference_string_required")
                payload = self.load_interfaces().resolve_region(self.case,self.options.route,arguments["reference"],include_geometry=True)
            else:
                raise ValueError("tool_not_available_in_route")
            complete = json.dumps(payload,ensure_ascii=True,allow_nan=False)
            write(folder/"COMPLETE_RESULT.json",payload)
            limit = self.options.fact_output_chars if name != "execute_python" else self.options.python_output_chars*2+2000
            record["complete_text_UTF8_bytes"] = len(complete.encode("utf8"))
            record["truncated"] = len(complete)>limit
            if record["truncated"]:
                complete = json.dumps(dict(truncated=True,original_text_UTF8_bytes=record["complete_text_UTF8_bytes"],preview=complete[:limit]),ensure_ascii=True)
            result = dict(content=[dict(type="text",text=complete)],isError=error)
            record["status"] = "tool_error" if error else "completed"
        except BaseException as exception:
            write(folder/"PRIVATE_ERROR.json",dict(type=type(exception).__name__,message=str(exception)))
            message="fixed_tool_round_budget_exhausted_finish_with_current_evidence" if index>self.options.max_tool_calls else "tool_execution_failed_see_private_audit"
            result = dict(content=[dict(type="text",text=json.dumps(dict(error=type(exception).__name__,message=message)))],isError=True)
            record["status"] = "failed"
        record["wall_s"] = time.perf_counter()-mark
        record["public_text_UTF8_bytes"] = sum(len(block["text"].encode("utf8")) for block in result["content"])
        self.calls.append(record)
        write(folder/"RESPONSE.json",result)
        write(folder/"COST.json",record)
        self.save(False)
        return result

    def save(self, closed):
        current = {name:hashlib.sha256((self.case/name).read_bytes()).hexdigest() for name in self.identities}
        write(self.audit/"BRIDGE_RESULT.json",dict(route=self.options.route,task_id=self.task["task_id"],closed=closed,
            calls=self.calls,input_identities_before=self.identities,input_identities_after=current,
            source_unchanged=current==self.identities,wall_s=time.perf_counter()-self.started,
            isolation_scope="fresh bounded Python process, restricted imports/attributes and immutable supplied arrays, no OS security certification"))

    def serve(self):
        try:
            for raw in sys.stdin.buffer:
                request = json.loads(raw)
                method, ident = request.get("method"), request.get("id")
                if ident is None:
                    continue
                if method == "initialize":
                    result = dict(protocolVersion=request.get("params",{}).get("protocolVersion","2024-11-05"),
                                  capabilities=dict(tools=dict(listChanged=False)),serverInfo=dict(name="task_geometry",version="1"))
                elif method == "tools/list":
                    result = dict(tools=self.tools)
                elif method == "tools/call":
                    result = self.call(request.get("params",{}))
                elif method == "ping":
                    result = {}
                else:
                    reply = dict(jsonrpc="2.0",id=ident,error=dict(code=-32601,message="method_unavailable"))
                    sys.stdout.buffer.write((json.dumps(reply,ensure_ascii=True)+"\n").encode("utf8"))
                    sys.stdout.buffer.flush()
                    continue
                reply = dict(jsonrpc="2.0",id=ident,result=result)
                sys.stdout.buffer.write((json.dumps(reply,ensure_ascii=True,allow_nan=False)+"\n").encode("utf8"))
                sys.stdout.buffer.flush()
        finally:
            self.save(True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",type=Path,required=True)
    parser.add_argument("--route",choices=("native","facts","learned"),required=True)
    parser.add_argument("--audit",type=Path,required=True)
    parser.add_argument("--max-tool-calls",type=int,default=6)
    parser.add_argument("--python-timeout-s",type=float,default=20)
    parser.add_argument("--python-output-chars",type=int,default=12000)
    parser.add_argument("--fact-output-chars",type=int,default=40000)
    Bridge(parser.parse_args()).serve()


if __name__=="__main__":
    main()
