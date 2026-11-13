# 连续观察工程资格的冻结准备

2026-11-13。依据管理员 c3e323b7 的连续观察合同，准备两个工程 episode，顺序 N 后 C，各三轮 BASE、REPEAT、EDIT。实际工程结果随后单独发布。本准备新增模型和推理 API 调用均为零。

产品固定 452b44d2，138 源摘要 4067c864…a9f6，使用既有隔离安装。原生工具声明沿用旧入口，C 另外暴露既有普通 observe。原有几何、展示和缓存实现作为被测固定输入。

## 最小生命周期差异

旧薄客户端已将后台生命周期交给外层 owner。新 actor 沿用这个 broker 和 stdin 所有权，只增加固定三轮归属、原期限、登记 pose barrier、跨轮状态和当前终态保护。登记 EDIT 使用既有 pose_native_metered 与固定 POSE_PATCH，外层读回完整几何并核对冻结 EDIT。终末记录保留实际 geometry_unchanged=false，以登记后的完整形状和 worker accepted fingerprint 判断清理。

工程 runner 每轮独立启动原始 stdio_attach，发送 initialize、initialized 通知、tools/list 和唯一业务，然后关闭 stdin、等待 EXIT。两个 metadata RPC 和一个通知单列。只有三轮结束或异常收尾才由外层调用 finish。每个 episode 从启动前起算绝对 590 秒，单工具 30 秒，失败原位保留。

N 三业务只创建一次内存标记并读取当前身份与姿态。REPEAT 与 EDIT 必须读取该标记，不能重新创建。C 三业务使用同一 session 的 ordinary default surface_scan。预期 71/71/72 匹配、112/0/10 新 kernel、每次一次捕获，完整数值对原真值核验。工程实例结束即清理，未来消费从新实例开始。

## 离线结果与来源

根离线复核 59 个方法通过，分为 owner 16、CLI 30、资格 10、runner 3。owner 测试使用合成 broker 和真实薄客户端进程，资格测试回放旧原件及合成反例，均未启动 Blender 或模型。各原日志保留于 offline/ 及对应子目录，方法数量不代表实际业务样本。

冻结本机 CLI 0.152.1 的摘要及 help。首轮去除 ephemeral，后轮显式使用原 thread UUID resume，同一 cwd 和 MCP 配置。参数 help 和合成解析已通过。cli/ 提供可调用 argv、状态解析及三轮匿名信封。真实 consume 进程循环仍需参数化逐轮输出目录、共享 workdir、thread ID 和期限，并接入原始事件及归档。这一集成差异已明确，未来正式消费前完成并复核。

模型真实续接、记忆保持和 usage 的本轮量或累计量定义尚未实测。逐轮 usage 应先原样保留，跨轮求和与差分等待证据。费用、provider 内部呈现、弃流 token 覆盖和准备协调总成本保留未知。AL 当前无绑定，host_epoch 为 5，任务同步尚不可用。

PREPARATION.json 冻结本批代码、输入、离线材料及复用外部文件摘要。必须先提交准备，再通过排他 ENGINEERING_STARTED 预留唯一两次工程运行。结束后交管理员审核，未来正式消费的样本数、顺序及收益门另行冻结。
