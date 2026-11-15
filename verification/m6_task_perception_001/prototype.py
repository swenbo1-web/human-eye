"""Run inspect/focus on a current NPZ, with versioned local caches and references."""

import argparse
import hashlib
from pathlib import Path
import sys
import time
BOOT_WALL=time.perf_counter()
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write
import numpy as np
from interfaces import TaskPerception


def run_current(input_path,entrypoint,target_ids=None,protected_ids=None,request=""):
    started,cpu=time.perf_counter(),time.process_time()
    path=Path(input_path).resolve()
    source_identity=identity(path)
    with np.load(path,allow_pickle=False) as source:
        vertices,faces=source["vertices"],source["faces"]
        F=source["F_source_ids"] if "F_source_ids" in source else source["F_ids"]
        target=source.get("target_ids",np.empty(0,dtype=np.int64)) if target_ids is None else np.asarray(target_ids,dtype=np.int64)
        protected=source.get("protected_ids",np.empty(0,dtype=np.int64)) if protected_ids is None else np.asarray(protected_ids,dtype=np.int64)
    key=hashlib.sha256((source_identity["sha256"]+"|v2|"+entrypoint).encode()).hexdigest()
    directory=HERE/"private/request_cache"/key[:16]
    directory.mkdir(parents=True,exist_ok=True)
    alias="q"+key[:16]
    case=dict(alias=alias,input=dict(path=str(path),sha256=source_identity["sha256"]))
    write(directory.relative_to(HERE)/"INPUT_INDEX.json",dict(cases=[case]))
    timings={}
    model_called=False
    preparation_cached=False
    if entrypoint=="inspect":
        feature_path=directory/"features.npz"
        prediction_path=directory/"prediction.npz"
        marker=directory/"CACHE_BINDING.json"
        model_record=read("MODEL_IDENTITY_v2.json")["final_checkpoint"]
        binding=dict(request_key_sha256=key,entrypoint=entrypoint,current_input_sha256=source_identity["sha256"],model_sha256=model_record["sha256"],
                     feature_source_sha256=identity(HERE/"features.py")["sha256"],model_source_sha256=identity(HERE/"model.py")["sha256"])
        if marker.exists():
            stored=__import__("json").loads(marker.read_bytes())
            if stored!=binding:
                raise ValueError("request_cache_binding_changed")
            preparation_cached=True
        else:
            from features import describe_current
            before=time.perf_counter()
            values=describe_current(vertices,faces,F.astype(np.int64))
            values.pop("neighbor_ids")
            stages=values.pop("timings")
            np.savez_compressed(feature_path,**values)
            timings["current_surface_preparation_and_cache_wall_s"]=time.perf_counter()-before
            timings["surface_preparation_stages"]=stages
            before=time.perf_counter()
            from model import load_model,predict_features
            model,_=load_model("v2")
            timings["first_Torch_import_and_model_load_wall_s"]=time.perf_counter()-before
            before=time.perf_counter()
            prediction=predict_features(model,values["features"],values["valid_mask"])
            np.savez_compressed(prediction_path,optimized_probability=prediction["scores"],source_ids=F.astype(np.int64))
            timings["inference_and_prediction_cache_wall_s"]=time.perf_counter()-before
            model_called=True
            write(directory.relative_to(HERE)/"CACHE_BINDING.json",binding)
        feature_record=dict(alias=alias,current_input_sha256=source_identity["sha256"],**identity(feature_path))
        prediction_record=dict(alias=alias,current_input_sha256=source_identity["sha256"],**identity(prediction_path))
        feature_record["path"]=feature_path.name
        prediction_record["path"]=prediction_path.name
        write(directory.relative_to(HERE)/"FEATURES.json",dict(cases=[feature_record]))
        write(directory.relative_to(HERE)/"PREDICTIONS.json",dict(cases=[prediction_record]))
        write(directory.relative_to(HERE)/"CALIBRATION.json",read("CALIBRATION.json"))
    prototype=TaskPerception(directory)
    if entrypoint=="inspect":
        result=prototype.inspect(alias,request=request)
    elif entrypoint=="focus":
        result=prototype.focus(alias,target,protected,request=request)
    else:
        raise ValueError("entrypoint_must_be_inspect_or_focus")
    result["runtime"]=dict(request_directory=str(directory),current_input=source_identity,model_called=model_called,
        preparation_cached=preparation_cached,timings=timings,wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,
        imports_and_call_wall_s=time.perf_counter()-BOOT_WALL,labels_or_reference_coordinates_read=0,
        adoption_status="research_candidate_failed_fixed_validation_gates")
    write(directory.relative_to(HERE)/"LAST_REPORT.json",result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path)
    parser.add_argument("--entrypoint",choices=("inspect","focus"))
    parser.add_argument("--target-ids",default="")
    parser.add_argument("--protected-ids",default="")
    parser.add_argument("--request",default="")
    parser.add_argument("--request-directory",type=Path)
    parser.add_argument("--resolve-reference")
    args=parser.parse_args()
    if args.resolve_reference:
        if args.request_directory is None:
            parser.error("--request-directory required to resolve a reference")
        result=TaskPerception(args.request_directory).resolve(args.resolve_reference)
    else:
        if args.input is None or args.entrypoint is None:
            parser.error("--input and --entrypoint required")
        target=None if not args.target_ids else np.array([int(x) for x in args.target_ids.split(",")],dtype=np.int64)
        protected=None if not args.protected_ids else np.array([int(x) for x in args.protected_ids.split(",")],dtype=np.int64)
        result=run_current(args.input,args.entrypoint,target,protected,args.request)
    print(__import__("json").dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=="__main__":
    main()
