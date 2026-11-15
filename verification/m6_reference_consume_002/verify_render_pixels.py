"""Compare decoded display pixels independently of PNG render metadata."""

import argparse
import hashlib
import json
from pathlib import Path
import time
from PIL import Image,ImageChops

HERE=Path(__file__).resolve().parent


def absolute(value):
    path=Path(value)
    return path if path.is_absolute() else HERE/path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=("v1","v2","all"),required=True)
    args=parser.parse_args()
    started,cpu=time.perf_counter(),time.process_time()
    index=json.loads((HERE/"VIEWABLES.json").read_bytes())
    rows=[]
    for session in index["sessions"]:
        if args.stage!="all" and session["stage"]!=args.stage:
            continue
        same_model=session["before_blend"]["sha256"]==session["after_blend"]["sha256"]
        for before,after in zip(session["before_images"],session["after_images"]):
            before_path,after_path=absolute(before["image"]["path"]),absolute(after["image"]["path"])
            with Image.open(before_path) as first,Image.open(after_path) as second:
                same_dimensions=first.size==second.size
                left,right=first.convert("RGBA"),second.convert("RGBA")
                identical=left.tobytes()==right.tobytes() if same_dimensions else False
                extrema=ImageChops.difference(left,right).getextrema() if same_dimensions else None
                changed_metadata=sorted(key for key in first.info.keys()|second.info.keys() if first.info.get(key)!=second.info.get(key))
            rows.append(dict(session=session["session"],view=before["role"],same_saved_model_SHA=same_model,
                same_dimensions=same_dimensions,RGBA_pixels_identical=identical,channel_absolute_difference_extrema=extrema,
                metadata_changed_keys=changed_metadata,
                before_file_sha256=hashlib.sha256(before_path.read_bytes()).hexdigest(),after_file_sha256=hashlib.sha256(after_path.read_bytes()).hexdigest(),
                preservation_pass=same_dimensions and (identical if same_model else True)))
    report=dict(status="pass" if rows and all(row["preservation_pass"] for row in rows) else "fail",stage=args.stage,views=rows,
        wall_s=time.perf_counter()-started,CPU_s=time.process_time()-cpu,
        interpretation="File, Date and RenderTime metadata can differ between actual renders. Geometry-preserving display is checked against decoded RGBA pixels when saved-model SHA is identical.")
    destination=HERE/"private/results"/("render_"+args.stage+"_PIXEL_VERIFICATION.json")
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8",newline="\n")
    print(report["status"],len(rows),"decoded image pairs",report["wall_s"],flush=True)
    if report["status"]!="pass":
        raise SystemExit(1)


if __name__=="__main__":
    main()
