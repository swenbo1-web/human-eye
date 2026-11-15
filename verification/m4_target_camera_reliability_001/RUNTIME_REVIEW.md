# 相机可靠性运行证据复核

`passed_checked_scope=true`，567项运行检查。覆盖保存来源、真实wire、producer摘要、持有进程退出、预算及成本时界。相机几何与像素质量由独立验收处理。

## 实际执行与退出

共7次owned启动，包含1个资产builder和6个旧新控制槽。实际raster为7，最终上界为7，无pending。新增numeric极值明确数值不足，未恢复为完整目标。

六槽均有主观察后的ping、之后独立task/aabb读回及第二次ping。MCP持有进程均exit0，reader、管道及runtime句柄关闭。Blender owned Popen均exit0并完成wait/reap，场景指纹与资产原件保持一致。Blender单独Win32句柄关闭状态未记录。worker事件的unknown状态不用于推断cleanup。

## 成本原窗

| 槽 | 主请求至回复 ms | 完整生命周期 ms | 后续读回 ms | actual raster |
|---|---:|---:|---:|---:|
| OLD_extreme | 198.5008 | 2266.3591 | 19.8674 | 1 |
| NEW_extreme | 145.4195 | 2240.6310 | 11.2614 | 0 |
| OLD_origin | 339.5054 | 2471.4940 | 10.1989 | 2 |
| NEW_origin | 315.9316 | 2297.2753 | 10.2544 | 2 |
| OLD_peripheral | 993.2967 | 3301.3959 | 56.3831 | 1 |
| NEW_peripheral | 905.4573 | 2885.1837 | 56.1890 | 1 |

主业务仅第一条请求。完整生命周期包含启动、主请求、两个ping、后续读回、预算结算和清理。事后保存证据核查另记，嵌套时钟不相加。这里没有完整任务提速或模型收益结论。

## Producer与来源

实际7份frame直接由同一次主full回复提供producer NPZ摘要和frame身份，逐份与保存文件及交付PNG核对。pose仍从同次真实camera_plan绑定。NEW extreme主捕获缺失，之后READBACK_CAPTURE仅证明后来的同宿主求值，未冒充主请求交付。

旧新141源分别钉安装及真实TCP bootstrap，只有宿主相机与MCP错误映射两文件不同。源/实例和局部面顺序沿实际capture绑定，原资产及origin量化尺寸保持。实际MCP字节取RX.bin，I/O的RX_text_UTF8_LF字段保留文本编码口径。

## 预算与历史状态

6个主请求共预留36次，实际7次，释放29个已证未构造预留。NEW extreme的0次由已钉camera阶段token、精确typed错误完整回包及零render事件共同核对。其他未知应保留上界。

旧A01附加runtime退出仍unknown，原thin launcher退出另列。旧缓存删除拒绝保留，未另行删除。新实例没有补证历史进程。本复核编写者同时是harness/资产/预算作者，实际执行由根完成。

本复核新增Blender、产品、raster、evaluator和模型调用均为0。所有输入SHA、实际wire边界、成本、检查及限制见JSON。
