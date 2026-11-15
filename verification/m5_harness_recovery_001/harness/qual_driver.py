"""Zero-model qualification of an already held actor. Root owns all startups."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import socket
import struct
import time


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()


def rpc(endpoint, message, output, deadline_ns):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    envelope = {"operation": "attached_mcp", "request_id": str(message.get("id", "notification")),
                "args": {"kind": "native", "message": message}}
    tx = encoded(envelope)
    (output / "TCP_TX.bin").write_bytes(tx)
    with socket.create_connection((endpoint["host"], endpoint["port"]), timeout=max(.001, (deadline_ns - started) / 1e9)) as connection:
        connection.settimeout(max(.001, (deadline_ns - time.perf_counter_ns()) / 1e9))
        connection.sendall(tx)
        sent = time.perf_counter_ns()
        connection.shutdown(socket.SHUT_WR)
        chunks = []
        total = 0
        while True:
            if time.perf_counter_ns() >= deadline_ns:
                raise TimeoutError("original_qualification_deadline")
            value = connection.recv(65536)
            if not value:
                break
            chunks.append(value)
            total += len(value)
            if total > 32 * 1024 * 1024:
                raise ValueError("qualification_response_byte_limit")
        completed = time.perf_counter_ns()
    rx = b"".join(chunks)
    (output / "TCP_RX.bin").write_bytes(rx)
    outer = json.loads(rx)
    if outer.get("ok") is not True or outer.get("request_id") != envelope["request_id"]:
        raise ValueError("qualification_MCP_envelope_failure")
    response = outer["result"]
    if response.get("id") != message["id"]:
        raise ValueError("qualification_MCP_response_id")
    images = []
    for block in response.get("result", {}).get("content", []):
        if block.get("type") != "image":
            continue
        raw = base64.b64decode(block["data"], validate=True)
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", raw[16:24]) != (512, 512):
            raise ValueError("qualification_original_PNG_dimensions")
        path = output / ("image_" + str(len(images) + 1) + ".png")
        path.write_bytes(raw)
        images.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    record = {"started_ns": started, "socket_send_completed_ns": sent,
              "received_complete_ns": completed, "client_socket_ns": completed - sent,
              "closed_ns": time.perf_counter_ns(), "TX_bytes": len(tx), "RX_bytes": len(rx),
              "TX_sha256": hashlib.sha256(tx).hexdigest(), "RX_sha256": hashlib.sha256(rx).hexdigest(),
              "response": response, "images": images, "model_calls": 0}
    with (output / "RECEIPT.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
    return record


OBSERVATION = {"mode":"active_observation","objects":[{"name":"M4_Far_00"}]}
INVALID = {"mode":"task","target":{"name":"M4_Far_00"},"candidates":[{"name":"M4_Near"}],
           "requested_facts":["surface_proximity"]}
SURFACE = {"mode":"task","objects":[{"name":"M4_Far_00"},{"name":"M4_Near"}],
           "requested_facts":["surface_proximity"]}
PARTIAL = dict(SURFACE,requested_facts=["surface_proximity","closed_solid_relation"])
MARKER = "M5_RECOVERY_PUBLIC:"


def statement(step, expression):
    return ("value = " + expression + "\nprint(" + repr(MARKER)
            + " + json.dumps({'step':" + repr(step)
            + ", 'isError':last_product_is_error, 'public_result':value}, sort_keys=True, allow_nan=False))\n")


def recovery_messages(group):
    if group not in ('A','B'):
        raise ValueError('recovery_group')
    final = OBSERVATION if group=='A' else dict(OBSERVATION,task_query=SURFACE)
    programs = [
        "import json\n" + statement('observation_initial',"observe(query=" + repr(OBSERVATION) + ", include_image=True)")
        + statement('invalid_task',"task(" + repr(INVALID) + ")"),
        "import json\n" + statement('valid_surface',"task(" + repr(SURFACE) + ")"),
        "import json\n" + statement('valid_surface_closed',"task(" + repr(PARTIAL) + ")"),
        "import json\n" + statement('final_observation_or_joint',"observe(query=" + repr(final) + ", include_image=True)"),
    ]
    return [{"jsonrpc":"2.0","id":"recovery-step-"+str(index),"method":"tools/call",
             "params":{"name":"execute_python","arguments":{"code":code}}}
            for index,code in enumerate(programs,1)]


def qualify(endpoint, output, group, deadline_ns):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    messages = [{"jsonrpc":"2.0","id":"recovery-initialize","method":"initialize",
                 "params":{"protocolVersion":"2025-03-26","capabilities":{}}},
                {"jsonrpc":"2.0","id":"recovery-tools","method":"tools/list"}]
    messages += recovery_messages(group)
    results=[]
    errors=[]
    for index,message in enumerate(messages,1):
        record=rpc(endpoint,message,output/('rpc_'+str(index).zfill(2)),deadline_ns)
        results.append(record)
        if message['method']=='tools/call' and record['response'].get('result',{}).get('isError') is not False:
            errors.append(dict(id=message['id'],response=record['response']))
    value=dict(schema='m5-harness-recovery-outer-sequence-v1',group=group,
        passed_transport_scope=not errors,errors=errors,requests=results,
        expected_internal_public_requests=5,expected_service_indices=[1,None,2,3,4],
        expected_internal_isError=[False,True,False,False,False],actual_model_calls=0,new_owned_starts_by_driver=0,
        scope='Four ordinary Python Owner calls. First call executes observation then original invalid task, each with immediate original JSON/isError snapshot. Subsequent actual public requests prove recovery.')
    with (output/'RECOVERY_CALLS.json').open('x',encoding='utf8') as stream:
        json.dump(value,stream,sort_keys=True,ensure_ascii=False,indent=2)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--group", choices=("A", "B"), required=True)
    parser.add_argument("--deadline-ns", type=int, required=True)
    args = parser.parse_args()
    result = qualify(json.loads(args.endpoint.read_bytes()), args.output, args.group, args.deadline_ns)
    print(json.dumps({"passed": result["passed_transport_scope"], "errors": result["errors"]}))
    if not result["passed_transport_scope"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
