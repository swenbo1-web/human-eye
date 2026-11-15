# 消费桥接实现

四个执行文件为 bridge.py、native_tools.py、bootstrap.py、launcher.py。产品源码与隔离安装沿固定 776b 版本，所有实际启动由根代理控制。

## 进程与调用

根代理持有普通 Python actor 的进程。bootstrap 校验既有共同依赖后进入 bridge。actor 调用 RootRuntime.start 建立本槽 owned Blender 和 P 的实际 MCP 连接，启动本地 MCP listener，发布 READY。根代理沿 launcher.consume_slot 调用既有 Pro CLI 消费循环。消费者的 thin stdio 连接原样复用，原始事件、usage、图片内容、统一结果匹配与归档保持既有结构。

actor 接收同一原始 owned 期限与 consumer 期限。根代理负责 actor、MCP 和 Blender 的外层保留句柄、超时终止及完整槽发布。Owner.close 关闭 listener 和线程，RootRuntime.close 完成内部宿主收尾。普通 Python 在 actor 的执行域中运行。

## 公共能力

两组均获得 execute_python、execute_blender_code、scene_data、render_views、read_images。P 另有 active_observation，实际转发当前安装 human_eye_scene_observe 的固定目标 active 请求，采用默认 brief 和所需图片。公开参数只提供 include_images，未提供 full 结果选项。后台生产者原件归档由运行代理完成。

启动时只提供六个相机设备的原始矩阵、名称、方向与尺寸。scene_data 按需读取本槽当前对象，原始 geometry 没有预置。Python 变量保留在本槽执行域中。普通 Blender 变量由同一 owned 宿主保留。

公共 render 和缓存只消费原始几何、设备与三角 buffer。frame 的 object_names 和 source_face_offsets 解释本帧自己的 owner 顺序。local triangle index 等于 global triangle ID 减去该 owner 的 offset。两组可以有不同的实际采集对象集合。公开 frame_ref 指向本槽当前帧，source_ref 指向本槽实际原始读取。

read_images 沿既有 PNG 校验与 ImageContent 编码出口交付实际图片。P 原 MCP content 保持字节内容。已取得的 P 原始三角帧可在共同 buffers 中复用。

## 预算与记录

Owner 对每个业务请求调用一次共同 Budget.reserve。execute_python 内的普通 Blender 或 render helper 计入该业务请求。每个实际 raster 构造由 RootRuntime 在构造前逐次准入，失败构造同样消耗额度。每槽限制为 12 次业务准入与 6 次 raster。

Owner 保存 tool_XX 的 REQUEST、RESPONSE、RECEIPT，保存每次 TCP 收发原字节及发送确认。消费者沿既有 CONSUMER.json、PUBLIC_FINAL.txt、stdout.raw.bin、events.jsonl、BUSINESS_SOURCE_BINDING.json、ARCHIVE.json 和 FINAL_TIMING.json。费用和 provider 内部图像 token 的缺失字段保留未知。

launcher.consume_slot 返回 slot_id、group、status、consumer_path、consumer_record、consumer、adapter_proof、source、owned。source 包含产品摘要、共同题面、共同 schema 和实际提示的摘要。根代理继续绑定 actual owned 身份与全槽时界。

## 输入边界

两组使用同一普通 Python 输入边界。公开属性、普通算法模块、NumPy、PIL、Fraction、Shapely 和 scratch 文件操作可用。内部属性反射、项目和管理员文件、产品实现入口、外部进程及网络入口受到拒绝并保留错误。getattr 与 hasattr 支持普通公开属性。

该边界的验收涵盖已登记的正常编程与泄漏反例。对任意恶意 Python 的安全隔离仍未验证。真正的执行时限依赖根代理持有 actor 进程并关闭 owned 链。

## 纯检查与准备修正

BRIDGE_PURE.json 初轮 18 项通过，覆盖普通 NumPy 和 Shapely、公开 getattr、私有反射与文件反例、lazy 来源、P 首入口、业务准入及既有消费循环复用。

补充 IMPORT_BOUNDARY_01.json 发现普通 import 的 fromlist 为 None 时触发 TypeError。native_tools_initial.py 保留修复前源码。public_import 规范化该参数后，IMPORT_BOUNDARY_R1.json 的两种 import 形式通过。BRIDGE_PURE_R1.json 在最终普通 import 路径上重复通过 18 项。此准备修正尚未触发真实消费者。

所有上述检查为合成接口检查，实际 Blender、CLI、模型、raster、图片构造计数均为零。真实来源、PNG 交付、缓存复用、预算前门和完整关闭仍由根代理的无模型资格槽验证。
