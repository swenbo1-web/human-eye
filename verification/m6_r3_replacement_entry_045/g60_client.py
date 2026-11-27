"""Keep the 036/043 transport and the 043 order of startup, close and archival."""
from __future__ import annotations

from pathlib import Path
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback

from g60_windows import NOW, OwnedProcess, mark, verify_clock, PARENT_CLOCK, SURVIVAL_CLOCK


def client_class(svc):
    class Client(svc.Client):
        def __init__(self, folder, owner, install):
            # Allocate the controller before any child can exist so failures still have an owner.
            self.folder,self.owner,self.install=folder,owner,install
            self.events=[]
            self.lifecycle_errors=[]
            self.processes={}
            self.exit_at_wrapper_wait={}
            self.worker=self.reader=None
            self.read_bytes={}
            self.files_written={}
            self.archive_files=[]
            self.mark("client_begin")

        def mark(self,name,at_ns=None):
            self.events.append(mark(name) if at_ns is None else {"name":name,"at_ns":at_ns})

        def launch(self):
            folder=self.folder
            owner=self.owner
            install=self.install
            folder.mkdir(exist_ok=False)
            self.audit=folder/"AUDIT.jsonl"
            self.config=folder/"CONFIG.json"
            self.source=install["source_sha256"]
            self.version=install["version"]
            self.role=install["role"]
            package=install["site_packages"]
            prefix=install["command_prefix"]
            self.mark("config_begin")
            svc.save(self.config,{"schema_version":"1.0","enabled":True,"observe_on_prompt":False,
                "project_root":package,"state_file":str(folder/"STATE.json"),
                "audit_file":str(self.audit),"quad_size":128,"max_sessions":4,"request_budget_s":30.0,
                "expected_identity":{"source_sha256":self.source},
                "blender":{"host":owner.host,"port":owner.port,"timeout_s":30.0}})
            self.mark("config_end")
            self.files_written["config"]=[self.config]
            args=[*prefix,"serve","--config",str(self.config)]
            env={key:value for key,value in os.environ.items() if not key.upper().startswith(("HUMAN_EYE_","PYTHON"))}
            env.update({k:"1" for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")})
            self.stderr=(folder/"STDIO.stderr").open("xb")
            self.seq,self.wire,self.responses=0,[],queue.Queue()
            self.started=NOW()
            self.mark("popen_begin")
            self.worker=subprocess.Popen(args,cwd=folder,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                         stderr=self.stderr,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            self.mark("popen_end")
            self.mark("launch_receipt_begin")
            launch=folder/"LAUNCH.json"
            python_ref, entry_ref, config_ref = [svc.pin(path) for path in (Path(prefix[0]),Path(prefix[-1]),self.config)]
            svc.save(launch,{"command":args,"python":python_ref,"entry":entry_ref,
                             "config":config_ref,"popen_pid":self.worker.pid,
                             "identity_role":self.role,"source_instrumentation":install is not None})
            self.mark("launch_receipt_end")
            self.files_written["launch_receipt"]=[launch]
            self.read_bytes["launch_receipt"]=[int(ref["bytes"]) for ref in (python_ref,entry_ref,config_ref)]
            self.reader=threading.Thread(target=self.receive,daemon=True)
            self.mark("reader_start_begin")
            self.reader.start()
            self.mark("reader_start_end")

        def receive(self):
            try:
                return super().receive()
            finally:
                self.mark("reader_receive_return")

        def call(self,method,params=None,*,notify=False):
            result=super().call(method,params,notify=notify)
            if method in ("initialize","tools/list"):
                timing=result[1]
                stage="initialize" if method=="initialize" else "catalog"
                self.mark(stage+"_write",timing["started_ns"])
                self.mark(stage+"_wire_decode",timing["closed_ns"])
            return result

        def open(self,name):
            assert name=="G60"
            hello,timing=self.call("initialize",{"protocolVersion":"2025-03-26","capabilities":{},
                                                  "clientInfo":{"name":svc.CYCLE,"version":"1"}})
            ident=hello["result"]["_meta"]["human_eye"]
            assert ident["source_sha256"]==self.source and ident["source_file_count"]==143
            assert ident["distribution_version"]==self.version and ident["production_mode"] is True
            self.call("notifications/initialized",notify=True)
            catalog,tools_time=self.call("tools/list")
            tool,=[t for t in catalog["result"]["tools"] if t["name"]=="human_eye_scene_observe"]
            announced="source_region_measurement" in json.dumps(tool,ensure_ascii=False)
            assert not announced
            self.mark("constructor_audit_begin")
            raw=self.audit.read_bytes()
            events=[json.loads(line) for line in raw.splitlines() if line]
            event,=[row for row in events if row.get("measurement_scope")=="service_constructor_only"]
            self.server_pid=event["pid"]
            assert event["runtime_identity"]["build_id"]=="sha256:"+self.source
            assert event["identity_check"]["compatible"] and event["identity_check"]["actual"]["source_sha256"]==self.source
            self.read_bytes["constructor_audit"]=[len(raw)]
            self.mark("constructor_audit_end")
            self.mark("handle_bind_begin")
            try:
                wrapper=self.worker.pid
                self.processes["wrapper"]=OwnedProcess(wrapper,os.getpid(),self.install["command_prefix"][0])
                self.processes["service"]=(self.processes["wrapper"] if wrapper==self.server_pid
                    else OwnedProcess(self.server_pid,wrapper,sys._base_executable))
            except Exception:
                self.lifecycle_errors.append(traceback.format_exc())
            self.mark("handle_bind_end")
            self.mark("startup_receipt_begin")
            startup=self.folder/"STARTUP.json"
            svc.save(startup,{"hello":hello,"timing":timing,"catalog":catalog,"tools_time":tools_time,
                             "actual_pid":self.server_pid,"startup_trace":event,"scoped_mode_advertised":announced})
            self.mark("startup_receipt_end")
            self.files_written["startup_receipt"]=[startup]

        def close(self):
            # Follow the frozen 027 close used in 043, with memory-only time marks.
            start=NOW()
            shutdown="eof"
            self.mark("stdin_close_begin")
            try:
                self.worker.stdin.close()
            except (BrokenPipeError,OSError):
                shutdown="already_closed"
            self.mark("stdin_close_end")
            self.mark("wrapper_wait_begin")
            try:
                code=self.worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.worker.terminate()
                code=self.worker.wait(timeout=10)
                shutdown="terminated_after_eof_timeout"
            self.mark("wrapper_wait_end")
            for role,process in self.processes.items():
                try:
                    self.exit_at_wrapper_wait[role]=process.wait_zero()
                except Exception:
                    self.lifecycle_errors.append(traceback.format_exc())
            self.mark("reader_join_begin")
            if self.reader is not None:
                self.reader.join(timeout=2)
            self.mark("reader_join_end")
            self.reader_joined=self.reader is not None and not self.reader.is_alive()
            self.mark("stderr_close_begin")
            self.stderr.close()
            self.mark("stderr_close_end")
            self.mark("archive_begin")
            for key,sent,received in self.wire:
                tx=self.folder/(key+".TX.bin")
                tx.write_bytes(sent)
                self.archive_files.append((tx,len(sent)))
                if received is not None:
                    rx=self.folder/(key+".RX.bin")
                    rx.write_bytes(received)
                    self.archive_files.append((rx,len(received)))
            self.mark("archive_end")
            self.mark("close_receipt_begin")
            p=self.folder/"CLOSE.json"
            svc.save(p,{"pid":self.worker.pid,"exit_code":code,"method":shutdown,"wall_ns":NOW()-start})
            self.mark("close_receipt_end")
            self.files_written["close_receipt"]=[p]
            return code

        def lifecycle(self):
            errors=self.lifecycle_errors
            processes={}
            final_all=NOW()
            try:
                for role,process in self.processes.items():
                    processes[role]=process.final()
                if set(processes)!={"wrapper","service"}:
                    raise ValueError("Both actual launcher and audited interpreter handles are required")
                os_survival=verify_clock(self.events,processes,os.getpid(),self.exit_at_wrapper_wait)
            except Exception:
                errors.append(traceback.format_exc())
                os_survival=None
            finally:
                for process in self.processes.values():
                    try:
                        process.release()
                    except Exception:
                        errors.append(traceback.format_exc())
            by={e["name"]:e["at_ns"] for e in self.events}

            def span(name, written, read_bytes):
                begin,end=name+"_begin",name+"_end"
                if begin not in by or end not in by:
                    return None
                sizes=[p.stat().st_size for p in written]+read_bytes
                return dict(name=name,started_ns=by[begin],closed_ns=by[end],files=len(sizes),
                            bytes=sum(sizes),wrote_files=len(written),read_files=len(read_bytes))

            names=("config","launch_receipt","constructor_audit","startup_receipt","close_receipt","close_readback")
            ios=[v for n in names if (v:=span(n,self.files_written.get(n,[]),self.read_bytes.get(n,[]))) is not None]
            archive=None
            if "archive_begin" in by and "archive_end" in by:
                files=[{"path":p.name,"bytes":length} for p,length in self.archive_files]
                archive={"name":"archive","started_ns":by["archive_begin"],"closed_ns":by["archive_end"],
                         "files":len(files),"bytes":sum(f["bytes"] for f in files),"entries":files}
            return {"valid":not errors and os_survival is not None,"errors":errors,
                    "clock":{"kind":PARENT_CLOCK,"process_clock":SURVIVAL_CLOCK},
                    "events":sorted(self.events,key=lambda e:e["at_ns"]),"experiment_io":ios,"archive":archive,
                    "processes":processes,"os_survival_ns":os_survival,
                    "controller_pid":os.getpid(),"exit_at_wrapper_wait":self.exit_at_wrapper_wait,
                    "reader":{"pid":os.getpid(),"native_tid":self.reader.native_id if self.reader else None,
                              "receive_return_observed": "reader_receive_return" in by,
                              "joined_and_inactive":getattr(self,"reader_joined",False),
                              "meaning":"receive target return stamp plus original join and is_alive; no inferred thread FILETIME"},
                    "post_workflow_handle_report_ns":NOW()-final_all}

    return Client
