# M5 模型消费薄桥

桥复用已接受的 Pro CLI 事件循环、归档和图像传输，普通 Python、Blender Python、原始几何、低层图像及缓存接口共同开放。A 和 B 的公共产品工具均直接采用各自隔离安装纯导出的 human_eye_scene_observe schema，runtime 还会与真实 tools/list 整体比对。

Python observe(query=None, include_image=True) 和 task(query) 只发送真实产品请求并返回原始公开 JSON。图片采用原 MCP 图片块，进入同次外层回复。A 可以在一次 execute_python 中调用 observe 与 task，B 可以发送 task_query 联合请求。桥保留实际内部调用序号、ID、原参数和公开文本摘要，外层业务准入独立计数。

共同路由说明先取得产品事实，允许合理批量。完整 prompt 固定在 inputs/PROMPT_A.txt 与 PROMPT_B.txt，共同题面和输出约定字节一致，能力说明仅描述各自 schema 的入口差异。消费者工作区不会接收私有答案、旧轨迹或回放数据。

新 guard 放行 type(value).__name__ 和类型上的同等 getattr。其余私有属性、模块、反射与文件边界保持。旧 N3 原始代码经原 guard 重现拒绝，再经新普通 Python 执行通过。历史归档含 owner 原件与 consumer 镜像两份同字节请求，准备脚本首次按文件要求唯一的失败及修正已保留。

纯检查 42 项通过，覆盖单次外层批量、联合请求、原 JSON 保真、图片共同交付、last_observation_json 与 last_task_json 分开保留、类型名、普通依赖和私有输入反例。单元图片仅为传输载荷，实际 PNG、来源及当前安装验证由根执行一次 A/B 资格完成。

CLI 仅核验固定二进制版本和登录状态，敏感登录输出仅存摘要。共享依赖直接核验旧有 146 份文件，未下载或安装。此代理尚未启动 Blender、MCP 进程、场景 raster 或模型。
