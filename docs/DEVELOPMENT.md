# 开发、测试与构建

在仓库根目录执行下列命令。运行库要求 Python 3.10 或更新版本，确定性构建脚本使用 Python 3.11 起提供的 `tomllib`。桌面验收使用 NumPy 2.3.5 和 Pillow 12.3.0。

```powershell
python -m pip install -e .
python -B verification/run_portable_tests.py
```

公共测试清单包括几何、采集、MCP、Hook 和本地进程生命周期。测试使用临时工作目录与合成场景。依赖历史私有原件或真实 Blender 的项目按各自入口单列。[测试清单](../verification/portable_modules.json)

## 复现桌面 wheel

选用尚不存在的输出目录。构建器从运行身份清单读取源文件，另收录包内两份 JSON，校验 wheel 的 RECORD，并在同一轮检查重复构建的字节。以下命令从源码生成 wheel、源码包和 `BUILD.json`。

```powershell
python -B verification/build_candidate_release.py --version 9.7.2+k049final --output ../human-eye-k049-build
Get-FileHash ../human-eye-k049-build/human_eye_spatial_plugin-9.7.2+k049final-py3-none-any.whl -Algorithm SHA256
```

期望 wheel 的 SHA-256 为 `308dd624cb4916b28bbe2decae87ac0a80d05dfad793da5afecebc65ac698964`。源码文件的原始换行也是身份的一部分。常规编辑安装用于开发；核对桌面二进制产物使用上述构建入口。[构建脚本](../verification/build_candidate_release.py)

## 在实验完成后提交

将发布所需的源码、兼容性测试和操作说明提交给主线。实验输入、私有模型和运行环境使用批次目录，文档通过固定提交引用已公开的验收报告。[工作目录](HUMAN_EYE_WORKSPACE.md)
