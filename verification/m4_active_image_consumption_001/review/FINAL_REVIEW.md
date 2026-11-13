# M4-ACTIVE-IMAGE-CONSUMPTION-001 真实原件复核

两路均通过本批已观测的图片消费资格。共享 helper 构造、真实 CLI 工具 image content、最终回答三层证据对应一致。作者侧独立审查完成，管理员终审待完成。

## 实际分母

| 路径 | 新会话 / 用户轮次 | 实际工具 | CLI 图片 | 原 PNG 载荷 |
| --- | --- | --- | --- | --- |
| N | 1 / 1 | read_image 两次 | 2 | 6,699 字节 |
| P | 1 / 1 | human_eye_image_observe 一次 | 2 | 6,699 字节 |
| 合计 | 2 / 2 | 3 次 | 4 | 13,398 字节 |

两个线程 UUID 不同，各有一次 thread.started、turn.started 和 turn.completed，没有 resume。两路均在原始 450 秒期限内完成，工具次数各自低于四次上限。24 份冻结来源保持一致。

## 图片与回答

两路实际 owner 响应、stdio RX 和真实 CLI completed 工具事件中的 image 内容逐字一致。PNG 哈希、媒体类型及 view-a→view-b 顺序与共同封存输入一致。P 确实调用实验 observe 出口。两路均未调用 execute_python，也没有其它工具偏离记录。

审查方打开了两个原 PNG。view-a 为近乎均匀的深色背景，中心附近只有极小亮点。view-b 有横跨画面较大区域的浅灰色菱形排列。两条最终回答均正确描述这些差异，绑定的原始回答 SHA 保存在 JSON 中。按本批合同，已观测的真实图片交付和视觉消费资格通过。

## 生命周期与限制

- CLI 与 actor 的原持有句柄回收得到确认，actor CLOSE 完成。两路 thin client 均缺少 EXIT 回执，bridge_cleanup.confirmed 为 null，正常 stdio EOF 继续为 unknown。运行后 PID 不存在的快照无法补足此前的正常退出证明。
- 每路保留两条 item.type=error 警告，分别涉及 skip_host_skill_discovery 的不稳定功能和 gpt-6.1-sol 缺少模型元数据而使用 fallback metadata。实际事件没有顶层 error 或 turn.failed。这些警告继续列为已知限制。
- 请求模型设置为 gpt-6.1-sol、medium、现有 ChatGPT 登录服务。实际 resolved model、provider 内部请求和图像 token 归因未直接观测。CLI 原始终值 usage 按路保存，未推算费用。
- 本批结论范围限于两张已有图片的工程资格。模型质量收益和插件任务收益尚未评估。

## 可复放检查

`check_final.py` 只读取既有 JSON、PNG 字节和 ZIP 成员，不导入 consumer/runtime，不启动模型或渲染。实际执行 53 项检查全部通过，覆盖冻结来源、三层内容、真实调用顺序、原期限、归档成员 SHA、警告保留及 thin EOF 未知状态。完整原件绑定、逐路 usage 与完整耗时见 `FINAL_REVIEW.json`。

此次复核新增 Pro 会话、Blender、renderer 和付费 API 调用均为 0。
