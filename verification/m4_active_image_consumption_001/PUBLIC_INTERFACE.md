# 已有图片的两路 MCP 接口

两路共同提供 `execute_python(code)` 和 `read_image(ref)`。普通 Python 使用持久变量、正常 Python 语句和文本 stdout/stderr，`image_files` 提供两个 opaque 图片引用对应的输入文件。`read_image` 返回引用文字及原始 PNG 的 MCP image content。

P 另有只读实验出口 `human_eye_image_observe(refs)`，将请求引用按 `view-a`、`view-b` 的顺序返回。每个引用紧接相应图片。两个出口调用同一个 `image_content` 函数。

图片均为 512×512、`image/png`。实验出口传递已有 PNG。默认产品安装及其尺寸配置继续使用现有版本。

## 纯函数调用示例

```python
import json
from pathlib import Path
import time

from image_content import image_content

manifest_path = Path("inputs/IMAGES.json")
manifest = json.loads(manifest_path.read_bytes())
specification = next(row for row in manifest["images"] if row["ref"] == "view-a")

# 集成时传入上层路由已经登记的绝对期限。
route_deadline_ns = time.perf_counter_ns() + 450 * 1_000_000_000
image_block, private_receipt = image_content(
    specification, manifest_path.parent, route_deadline_ns
)
content = [{"type": "text", "text": "view-a (512x512, image/png)"}, image_block]
```

私有回执保留读取、PNG 流验证、编码时界、原始哈希和字节。MCP 的公有结果只包含引用标签及实际 image block。

## 持有服务的启动

```text
python -I -B -X utf8 actor.py --config CONFIG.json
```

CONFIG 使用以下键。`output` 必须是新的目录，`endpoint` 是父控制器分配的路径，`worker_deadline_ns` 直接继承该路原始绝对期限。

```json
{
  "group": "N",
  "output": "ABSOLUTE_NEW_OUTPUT_DIRECTORY",
  "endpoint": "ABSOLUTE_ENDPOINT_FILE",
  "images_manifest": "ABSOLUTE_INPUTS_IMAGES_JSON",
  "worker_deadline_ns": 123456789,
  "max_tool_calls": 4
}
```

服务发布 `host`、`port`、`chain_deadline_ns`、`actor_pid`。原 `stdio_attach.py` 使用这些键发送 attached_mcp 请求并完整转发 JSON。父控制器在 stdin 写入一行或关闭 stdin 后，服务关闭监听器并等待处理线程停止，CLOSE.json 记录结果。父控制器继续负责持有的原始进程句柄回收。

服务端的 sendall 确认、CLI 收到的工具 content、模型回答分别保存验收。METRICS.json 中的服务端计数只描述服务端实际观测层。
