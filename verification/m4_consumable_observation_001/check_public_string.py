"""Mock-only public-string protocol checks, with no observation or raster."""

import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import types


HERE = Path(__file__).resolve().parent


def load_bridge():
    specification = importlib.util.spec_from_file_location("_consumable_mock_bridge", HERE / "bridge.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def request(number=1, arguments=None):
    return {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": {
        "name": "active_observation", "arguments": {"include_images": True} if arguments is None else arguments}}


def wrap(response):
    return {"request_id": "mock-current-request", "ok": True, "result": response}


def main():
    bridge = load_bridge()
    text = '{ "schema": "active-observation-brief-v4", "public_mock": "同一原文", "values": [1, null] }\n'
    public_result = {"content": [{"type": "text", "text": text}], "isError": False}
    cases = []
    producer_calls = []
    with tempfile.TemporaryDirectory(prefix="human-eye-public-json-") as temporary:
        root = Path(temporary).resolve()

        def owner_for(name, response=public_result, failure=False):
            owner = bridge.Owner.__new__(bridge.Owner)
            owner.out = root / name
            owner.out.mkdir()
            owner.group, owner.calls, owner.deadline_ns = "P", 0, 2**63 - 1
            owner.namespace = {"last_observation_json": "previous-public-value"}
            owner.logs, owner.image_files = [], {}
            owner.save_metrics = lambda: None
            owner.record_constructed = lambda receipt: None

            def mock_public_response(include_images, callback):
                if owner.namespace["last_observation_json"] is not None:
                    raise AssertionError("observation_start_did_not_clear")
                producer_calls.append(name)
                if failure:
                    raise RuntimeError("mock_observation_failure")
                return response

            owner.session = types.SimpleNamespace(active_observation=mock_public_response,
                product_image_failures=[], by_ref={}, save=lambda: None)
            return owner

        owner = owner_for("success")
        message = request()
        response = owner.tool_call(message)
        assert owner.namespace["last_observation_json"] is None
        server, client = socket.socketpair()
        try:
            outbound = bridge.encoded(wrap(response))
            server.sendall(outbound)
            server.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = client.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            inbound = b"".join(chunks)
            assert inbound == outbound
            owner.complete_observation_delivery(message, wrap(response), True)
            delivered_text = json.loads(inbound)["result"]["result"]["content"][0]["text"]
            assert owner.namespace["last_observation_json"] is text
            assert delivered_text.encode("utf8") == text.encode("utf8")
            assert json.loads(owner.namespace["last_observation_json"])["public_mock"] == "同一原文"
        finally:
            server.close()
            client.close()
        cases.append("successful_socket_publication_same_string_and_wire_bytes")

        next_message = request(2)
        next_response = owner.tool_call(next_message)
        assert owner.namespace["last_observation_json"] is None
        owner.complete_observation_delivery(next_message, wrap(next_response), False)
        assert owner.namespace["last_observation_json"] is None
        cases.append("next_observation_clears_and_failed_send_does_not_publish")

        for name, arguments, calls, failure in (
            ("producer_failure", None, 0, True),
            ("invalid_arguments", {"unexpected": True}, 0, False),
            ("thirteenth_guard", None, 12, False),
        ):
            current = owner_for(name, failure=failure)
            current.calls = calls
            message = request(arguments=arguments)
            before = len(producer_calls)
            response = current.tool_call(message)
            assert response["result"]["isError"] is True
            assert current.namespace["last_observation_json"] is None
            current.complete_observation_delivery(message, wrap(response), True)
            assert current.namespace["last_observation_json"] is None
            if name != "producer_failure":
                assert len(producer_calls) == before
            cases.append(name + "_clears_without_old_value")

        error_result = {"content": [{"type": "text", "text": '{"public_mock_error":true}'}], "isError": True}
        current = owner_for("public_error", response=error_result)
        message = request()
        response = current.tool_call(message)
        current.complete_observation_delivery(message, wrap(response), True)
        assert current.namespace["last_observation_json"] is None
        cases.append("public_error_response_not_published")

        current.namespace["last_observation_json"] = text
        current.complete_observation_delivery({"method": "ping"}, {"ok": True, "result": {}}, True)
        assert current.namespace["last_observation_json"] is text
        cases.append("unrelated_protocol_response_preserves_last_public_observation")

        current.complete_observation_delivery(request(), {"ok": False, "error": "mock_transport_error"}, True)
        assert current.namespace["last_observation_json"] is None
        cases.append("outer_protocol_failure_clears")

        current.namespace["last_observation_json"] = text
        malformed = {"content": [{"type": "text", "text": None}], "isError": False}
        current.complete_observation_delivery(request(), wrap({"result": malformed}), True)
        assert current.namespace["last_observation_json"] is None
        cases.append("non_string_public_text_not_published")

    result = {"schema": "consumable-public-string-mock-check-v1", "passed": True, "cases": cases,
        "public_text_sha256": hashlib.sha256(text.encode("utf8")).hexdigest(),
        "mock_callback_invocations": len(producer_calls),
        "real_observation_calls": 0, "real_product_calls": 0, "real_rasters": 0,
        "model_calls": 0, "Blender_processes": 0,
        "scope": "Synthetic public-text response and local socket only. Actual Owner tool budget and publication methods are exercised; the real observation session constructor is never called.",
        "source_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ("bridge.py", "native_tools.py", "bootstrap.py", "check_public_string.py")}}
    output = HERE / "preparation/MOCK_PUBLIC_STRING.json"
    output.parent.mkdir(exist_ok=True)
    with output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": True, "mock_cases": len(cases), "real_rasters": 0}))


if __name__ == "__main__":
    main()
