"""Recalculate public geometry, paths and paired costs directly from the original GUI sessions."""
import itertools
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from fractions import Fraction

RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")
read = lambda path: json.loads(path.read_bytes())
median = statistics.median


def wire(client, index):
    tx, rx = (read(client/f"{index:03}.{d}.bin") for d in ("TX", "RX"))
    assert tx["method"]=="tools/call" and tx["id"]==rx["id"] and not rx["result"]["isError"]
    return tx["params"],json.loads(rx["result"]["content"][0]["text"])


def changes(ref, candidate):
    delta = [b-a for a,b in zip(ref,candidate,strict=True)]
    pct = [100*(b/a-1) for a,b in zip(ref,candidate,strict=True)]
    return dict(base_ms=median(ref), candidate_ms=median(candidate), paired_ms=median(delta),
                paired_pct=median(pct), faster=sum(d<0 for d in delta), per_pair_pct=pct)


def public(body, identity):
    """Remove only per-request traces and the independently verified differing build identity."""
    clean = dict(body)
    clean.pop("trace_id",None)
    clean.pop("request_trace",None)
    if "runtime_identity" in clean:
        assert clean.pop("runtime_identity")["source_sha256"]==identity
    if "binding" in clean:
        binding = clean["binding"].copy()
        assert binding.pop("runtime_source_sha256")==identity
        clean["binding"]=binding
    return clean


def counters(e):
    work=e["task_work"]
    pairs=work.get("pairs",{})
    return Counter(row["surface_work"]["solver_path"] for row in pairs.values()
                   if row.get("surface_work",{}).get("solver_path")) if isinstance(pairs,dict) else Counter()


def group_data(family):
    paths=sorted((RAW/"g60_b02"/family).glob("*/G??-*/GROUP.json"),key=lambda p:p.parent.name)
    expected_orders=(["".join(c) for c in itertools.permutations("ABF")] if family=="G60"
                     else ["AF","FA"]*3)
    assert len(paths)==len(expected_orders)==6
    rows=[];total=Counter();bodies=0;missing_after=[];generations=set()
    for file,order in zip(paths,expected_orders,strict=True):
        g=file.parent;receipt=read(file)
        assert receipt["order"]==order and receipt["gui_close"]["process_reaped"] and receipt["gui_close"]["exit_code"]==0
        before=read(g/"BEFORE.json")
        assert before["background"] is False
        if (g/"AFTER.json").is_file():
            after=read(g/"AFTER.json")
            assert all(before[k]==after[k] for k in ("geometry","pid","frame","subframe","scale"))
        else:
            assert family=="G60" and g.name=="G01-ABF"
            recovery=read(g.parents[1]/"resume_001/G01_REQUALIFIED.json")
            assert recovery["metadata_requalification"] and "not_acquired" in recovery["after_snapshot_status"]
            missing_after.append(g.name)
        base=None;slots={};previous=0
        for arm in order:
            folder=g/arm;client=folder/"client"
            cell=read(folder/"CELL.json")
            assert not cell["errors"] and cell["started_ns"]>=previous
            previous=cell["ended_ns"]
            hello=read(client/"001.RX.bin")["result"]["_meta"]["human_eye"]
            identity=hello["source_sha256"]
            assert hello["source_file_count"]==(145 if arm=="F" else 143)
            if arm=="F":assert identity=="7075c79b8aff6821e3cb37882b7123be2728cbf38972f34b93e05ef8afa8e50c"
            ev=[json.loads(line) for line in (client/"AUDIT.jsonl").read_text("utf8").splitlines()]
            results=[]
            for idx,row in enumerate(cell["rows"],4):
                request,body=wire(client,idx)
                assert body==row["result"]
                results.append((request,public(body,identity)))
                bodies+=1
                if row["step"]!="overview":
                    [event]=[e for e in ev if e["event"]=="observe" and e.get("trace_id")==body["trace_id"]]
                    assert event["pid"]==cell["product_pid"] and event["identity_check"]["actual"]["source_sha256"]==identity
                    if row["step"]=="nearest":
                        assert [x["name"] for x in body["nearest_objects"]]==(["Peer_000"] if family=="G60" else ["Obj_002"])
                    else:
                        cc=body["coverage"]
                        assert (cc["total_pairs"],cc["measured_match"],cc["measured_nonmatch"],cc["bound_excluded"])==(
                            (66,57,9,0) if family=="G60" else (276,71,41,164))
                        assert cc["unknown"]==cc["deferred"]==0
                    if arm=="F":
                        counts=counters(event)
                        assert sum(counts.values())==event["task_work"]["kernel_calls"]
                        total.update(counts)
            assert base is None or results==base,(family,g.name,arm)
            base=results
            life=cell["lifecycle"];processes=life["processes"]
            wrapper,service=(processes[k] for k in ("wrapper","service"))
            assert wrapper["pid"]==cell["wrapper_pid"]==service["parent_pid"] and service["pid"]==cell["product_pid"]
            for proc in (wrapper,service):
                gen=(proc["pid"],proc["creation_time_100ns"])
                assert gen not in generations and proc["owned_held_handle"] and proc["exit_code"]==0
                assert proc["bind_times"]["creation_time_100ns"]==gen[1]
                generations.add(gen)
            last=max(q["exit_time_100ns"] for q in (wrapper,service))
            assert last<=next(e["filetime_100ns"] for e in life["events"] if e["name"]=="archive_begin")
            assert life["reader"]["joined_and_inactive"] and read(client/"CLOSE.json")["exit_code"]==0
            t=cell["last_reply_ns"]-cell["rows"][0]["timing"]["started_ns"]
            lifespan=(last-wrapper["creation_time_100ns"])*100
            full=cell["workflow_end_ns"]-cell["workflow_start_ns"]
            assert (t,lifespan,full)==(cell["business_ns"],life["os_survival_ns"],cell["workflow_ns"])
            slots[arm]={"business":t/1e6,"process":lifespan/1e6,"client":full/1e6,
                        "business_product_cpu_s":cell["product_after"]["cpu_s"]-cell["product_before"]["cpu_s"],
                        "observed_product_peak_mib":cell["product_after"]["peak_working_set_bytes"]/2**20}
        rows.append(slots)
    comps={}
    for base in ("AB" if family=="G60" else "A"):
        comps[base]={k:changes([g[base][k] for g in rows],[g["F"][k] for g in rows])
                     for k in ("business","process","client")}
    assert total==(dict(r3=462) if family=="G60" else {"r3":714,"032":18})
    gate=comps["A"]["business"]
    if family=="G60":
        assert gate["paired_pct"]<=-10 and gate["faster"]>=5 and comps["B"]["business"]["paired_pct"]<=5
        assert comps["A"]["process"]["paired_pct"]<0 and comps["B"]["process"]["paired_pct"]<=5
    else:
        assert gate["paired_pct"]<=5
    return dict(groups=rows,orders=expected_orders,comparison=comps,wire_replies=bodies,
                F_actual_solvers=total,after_snapshot_not_taken=missing_after)


def yanyite():
    root=RAW/"yanyite";hostrows=[];first=[];warm=[]
    orders=(("AF","FA","AF","FA"),("FA","AF","FA","AF"),("FA","AF","AF","FA"))
    for i in range(1,4):
        host=root/f"main_001/H{i}"
        before,after=read(host/"BEFORE.json"),read(host/"AFTER_TIMED.json")
        assert before["geometry"]==after["geometry"] and before["pid"]==after["pid"] and before["background"] is False
        assert read(host/"HOST.json")["GUI_close"]["exit_code"]==0
        ht=[]
        for j,order in enumerate(orders[i-1],1):
            pair={};prev=0;ref=None
            for arm in order:
                path=host/f"P{j}-{arm}";cell=read(path/"CELL.json")
                assert cell["valid"] and prev<=cell["started_ns"]
                prev=cell["ended_ns"]
                times=[]
                for idx,row in enumerate(cell["rows"],4):
                    req,body=wire(path/"client",idx)
                    assert ref is None or ref==(req,body)
                    ref=req,body
                    assert body["selected_triangle_count"]==262 and (body["source_triangle_a"],body["source_triangle_b"])==(49114,0)
                    assert body["distance_m"]==0.14501953294680436
                    t=row["body_decoded_ns"]-row["timing"]["started_ns"]
                    assert t==row["business_ns"]>0
                    times.append(t/1e6)
                pair[arm]=times
            first.append((pair["A"][0],pair["F"][0]))
            ht.append((pair["A"][1],pair["F"][1]))
        warm.extend(ht)
        hostrows.append(changes(*zip(*ht)))
    delta=changes(*zip(*warm))
    assert not(delta["paired_ms"]>5 and delta["paired_pct"]>5 and sum(h["paired_ms"]>0 for h in hostrows)>=2)
    h=read(root/"main_001/H3/HOST.json")["functional"]
    move=h["actual_edit"]["actual"];step=move["after_z"]-move["before_z"]
    assert Fraction(step)==Fraction(1,64) and h["only_private_reference_transform_changed"] and h["same_F_service_edit_invalidation"]
    vals={}
    for row in h["arms"]["F"]["rows"]:
        _,b=wire(Path(row["request"]["path"]).parent,int(row["timing"]["id"]))
        assert b==row["result"]
        vals[row["step"]]=b["distance_m"]
    for name in ("high","low"):
        assert vals[name+"_first"]==vals[name+"_repeat"] and vals[name+"_after"]==vals[name+"_after_repeat"]
        assert vals[name+"_after"]-vals[name+"_first"]==step
    replay=read(root/"H3_replay_001/RESULTS.json")["calls"]
    for c in replay:
        receipt=Path(c["receipt"]["path"])
        assert hashlib.sha256(receipt.read_bytes()).hexdigest()==c["receipt"]["sha256"] and c["returncode"]==0
        data=read(receipt)
        region=c["region"]
        index=data["result"]["witness_triangle_indices"][0]
        assert data["source_geometry"]["original_region_rows"][index]==data["native_pair"][0]
        assert data["native_pair"]==[49114 if region=="high" else 46767,0]
        target=vals[region+("_first" if c["state"]=="before" else "_after")]
        assert data["result"]["distance_m"]==target
        pts=[tuple(map(Fraction,v)) for v in data["exact_world_points"]]
        assert sum((a-b)**2 for a,b in zip(*pts))==Fraction(data["exact_squared"])
    assert {(v["arm"],v["region"],v["state"]) for v in replay}==set(itertools.product("AF",("high","low"),("before","after")))
    remainder={}
    for arm in "AF":
        raw=read(root/f"prep_{arm}_remainder_001/one_precharge.json")["result"]
        assert not raw["measurement_valid"]
        remainder[arm]=raw["reason"]
    assert remainder["A"]==remainder["F"]
    return dict(first=changes(*zip(*first)), warm=delta, host_warm=hostrows, business_replies=48,
                motion_z_m=step, same_process_edit_readbacks=vals, remaining_8356=remainder,
                H3_replay_cells=len(replay))


def spots():
    out={}
    for name in ("D48","G508"):
        slots={};refs={}
        for arm in "AF":
            folder=RAW/f"spots/attempt_001/{name}_{arm}"
            cell=read(folder/"CELL.json")
            assert cell["geometry_preserved"] and cell["cleanup"]
            audit=[json.loads(l) for l in (folder/"client/AUDIT.jsonl").read_text("utf8").splitlines()]
            slot={}
            for i,row in enumerate(cell["rows"],4):
                req,body=wire(folder/"client",i)
                assert body==row["body"]
                step=row["label"]
                fields={k:v for k,v in body.items() if k not in ("binding","trace_id")}
                if arm=="A":refs[step]=(req,fields)
                else:assert (req,fields)==refs[step]
                counts={}
                if step!="relation":
                    event=next(e for e in audit if e["event"]=="observe" and e["trace_id"]==body["trace_id"])
                    if event["task_work"].get("result_cache_hit"):
                        counts={"result_cache_hit":1}
                    elif arm=="F":
                        counts=counters(event)
                    else:
                        counts={"032_baseline":event["task_work"]["kernel_calls"]}
                    assert counts==row["actual_path_counts"]
                if step=="relation":
                    assert body["pairs"][0]["facts"]["closed_solid_relation"]["reason"]=="closed_solid_work_budget"
                    assert body["pairs"][0]["facts"]["surface_proximity"]["status"]=="measured"
                slot[step]=dict(ms=row["business_ns"]/1e6, paths=counts, status=body["status"])
            slots[arm]=slot
        out[name]=slots
    return out


if __name__=="__main__":
    result={f:group_data(f) for f in ("G60","B02")}
    result.update(Yanyite=yanyite(), spots=spots())
    print(json.dumps(result,indent=2))
