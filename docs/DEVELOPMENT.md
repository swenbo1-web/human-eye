# 开发与复现

从当前 checkout 安装依赖后运行 `python -B verification/run_portable_tests.py`。此脚本列明公共可移植模块及历史依赖排除理由；不连接 Blender，不发起模型/API 请求。

顶层 verification 保留历史测试源码。依赖旧 sealed evidence、机器安装状态或真实 Blender RNA 的测试不等于可移植测试；历史本地报告数字与公共测试脚本的实际计数分别记录。

所有运行时 `.py` 的原始字节参与身份摘要，Blender host 还固定依赖源的 SHA。`.gitattributes` 禁止自动换行转换，请保留此配置。换行或格式化也是源码变更，需更新依赖 pin、重新验证并构建新身份；不能通过忽略漂移来消除错误。

包基础版本为9.7.2；发行构建另有完整版本及源码摘要。源码checkout、SDK安装与固定入口发布身份不同，不能混称。`human_eye_plugin/runtime_identity.py` 定义摘要规则。使用 `python -B` 避免写入字节码，但不能据此认为任意 loader 不读取旧缓存；只读关键加载链另有同份已校验源字节编译规则。

本地 `.human-eye`、`.codex` 与发布包不进入仓库。安装配置使用当前机器绝对路径；提交配置示例前移除令牌、用户路径和运行状态。默认入口的通用模板、实际固定包以及宿主Bridge应按兼容合同核对，不复制其他机器的状态文件。

本项目未添加新的LICENSE声明。当前仓库中的历史生物机制类比与性能目标是设计方向，完成程度以实际代码及可复现测试为准。没有正式模型收益试验，不应声称已普遍提升所有Agent。

固定候选构建使用Python 3.11+的`verification/build_candidate_release.py --version <唯一发行号> --output <不存在的新目录>`，只收运行身份清单和两项包JSON，不扫描本机测试证据。工具不安装依赖或激活配置；wheel和源码ZIP的运行源字节保持，并校验RECORD及确定性重建。旧build_release/build_release_bundle保留为历史脚本，不作为当前M1候选入口。隔离目录复用依赖环境与全新依赖环境须分别报告；候选功能通过也不能覆盖历史成本失败或变成正式发布。
