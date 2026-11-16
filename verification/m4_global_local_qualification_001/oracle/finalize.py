"""Verify saved evidence pins and publish the independent qualification bytes."""
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def main():
    qualification = json.loads((HERE/"QUALIFICATION_R1.json").read_bytes())
    semantic = json.loads((HERE/"ACTUAL_SEMANTIC_REVIEW.json").read_bytes())
    pure = json.loads((HERE/"INTERFACE_SAVED_R1.json").read_bytes())
    assert qualification["passed"] and qualification["qualified_count"]==qualification["denominator"]==3
    assert semantic["passed_checked_scope"] and pure["passed"]
    records = qualification["records"]
    pins = {}
    for document in (qualification,semantic):
        for row in document["input_pins"]:
            current = pin(Path(row["path"]))
            if current!=row:
                raise ValueError("evidence_pin_changed/"+row["path"])
            pins[current["path"]] = current
    with (NS/"QUALIFICATION.json").open("xb") as stream:
        stream.write((HERE/"QUALIFICATION_R1.json").read_bytes())
    text = """# 独立资格审核

M4-GLOBAL-LOCAL-QUALIFICATION-001 的静态前提与三个真实资格会话均通过。固定场景有9对象、54顶点、56捕获三角，独立重建24个最大共边共面分量。其中22个矩形包含44个三角，方环与L形包含12个 unsupported 三角。合格任务集合恰为 Obj_02、Obj_06、Obj_09，各自源三角为0和1。

全场拟合的18个目标与方向组合，独立保守像素中心格上界均为1或2，包含5%相机边距、binary64区间及既有重心接受误差。真实全场构造六帧。两个开放小面保留 pixel_evidence_insufficient，盖下小面保留遮挡 unknown。

局部开放控制构造SCENE一帧，取得当前完整可读见证，实际50557个表面像素和926个对比边界像素。局部盖下控制构造SCENE一帧，目标表面像素为0，完整见证为空。盖下全六方向的几何正面积遮挡由独立Fraction射线证明及本槽精确附项共同核对，实际未构造方向单列 unrun。

三个scope分别核对原生求值点面顺序、固定资产SHA、当前 document_epoch、host_id、instance_id、局部三角号及有序几何。每个scope保存自身object_index和实际相机。跨scope对应依据是经过核验的同一固定资产几何。

静态oracle的12项纯接口反例与保存适配器的8项反例通过。保存适配器执行实际候选AST判定，覆盖比例法向、反向、偏轴、零向量及精确中心解析。帧检查器单独完成8帧的原图、数组、owner/source和像素核验。

## 保存接线修正

冻结脚本、首次失败报告和stdout/stderr均保留。独立R1按明确的最终 FRAMES_R2 文件名读取帧报告，将静态JSON中的有理中心解码为Fraction，并对公开有理比例方向核验精确正比例。原公开倾斜方向为[0,-1/3,1]，任务单位法向由独立几何得到[0,-1,3]/sqrt(10)。面积与nz门槛沿冻结几何核验。

盖下公开主字段 reason 为 finite_camera_pool_uncovered，精确 region_evidence.unobserved_reason 为 positive_area_occlusion_all_front_views，且view_reasons列出全六方向。两层原字段分别保留。该主字段的信息粒度应纳入后续消费设计。

本批验证了全场小目标取证不足和局部拟合恢复的条件。产品内全场到局部自动选择、父子见证回绑及模型任务收益由后续对应批次验证。资格后追加实际调用为0。
"""
    with (HERE/"INDEPENDENT_REVIEW.md").open("x",encoding="utf8") as stream:
        stream.write(text)
    owned_files = [path for path in sorted(HERE.iterdir()) if path.is_file()]
    owned_files.append(NS/"QUALIFICATION.json")
    delivery = dict(schema="global-local-independent-review-delivery-v1",ready=True,passed_checked_scope=True,
        qualification=pin(NS/"QUALIFICATION.json"),saved_qualification=pin(HERE/"QUALIFICATION_R1.json"),
        static=pin(HERE/"STATIC_QUALIFICATION.json"),semantic=pin(HERE/"ACTUAL_SEMANTIC_REVIEW.json"),
        source_derivation=pin(HERE/"SAVED_ADAPTER_CORRECTION_01.json"),
        qualification_denominator=3,qualified_count=3,static_interface_cases=12,saved_adapter_interface_cases=8,
        actual_rendered_frames=sum(len(row["rendered_views"]) for row in records),
        independently_rechecked_unique_input_files=len(pins),independently_rechecked_unique_input_bytes=sum(row["bytes"] for row in pins.values()),
        evidence_pins=list(pins.values()),owned_file_pins=[pin(path) for path in owned_files],
        additional_actual_operations=dict(Blender=0,MCP=0,raster=0,model=0,paid_API=0),
        final_write_state="After this delivery no further writes to these files are intended before root seal.")
    target = HERE/"DELIVERY.json"
    with target.open("x",encoding="utf8") as stream:
        json.dump(delivery,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print(json.dumps(dict(ready=True,qualification_sha256=pin(NS/"QUALIFICATION.json")["sha256"],
        delivery_sha256=pin(target)["sha256"],owned_files=len(owned_files),input_files=len(pins),check_count=qualification["check_count"])))


if __name__=="__main__":
    main()
