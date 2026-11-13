# 主动覆盖002启动绑定与最小修复复核

结论：当前失败确实发生在控制器把启动器PID等同于解释器PID的假设处。首A的渲染成功不改变冻结槽failed。实际现场父子谱系没有留证，本审不补写这段历史。应复用项目已有的**直接基础解释器＋显式原venv包路径**路线，保留严格PID相等，而不删除绑定或扩建进程树管理层。

固定作者交付为`35e9321121e5ca8e9a8414dab859cd6361da4d9c`。本子审查仅读取作者原件、本机Python源码/版本资源和项目历史恢复原件；没有启动新Python探针、渲染、正式样本、Blender、模型或API。输出仅当前launch目录。AL按自身句柄20b4c626246449bb9663051f0e2c49e5读取，父任务08404590-ee8d-4b97-83c3-9e765e9177aa revision1/write638，assignment current=true，未覆盖父任务。

## 本次失败与异常清理边界

作者目录为`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_002/`。

- `runner.py:124`由`sys.executable`构造子命令；`:133–137`只保存Popen.pid并等待该句柄退出。
- `runner.py:150`先完成validate_run，`:152–153`才比较RESULT.process_id与Popen.pid。原失败异常及行号明确是`child_process_or_output_binding`。本次父PID23456，RESULT与TRACE使用20368，输出目录一致。
- `runtime.py:75` TRACE写os.getpid，`:250` RESULT同样写os.getpid；它不是作者手填另一个角色字段。静态行为和原件只能证明两个角色PID不相等，不能证明本次的真实父子关系。
- `runner.py:138–142`在Popen仍存活时只对该句柄kill/wait；没有记录或持有实际解释器的独立进程句柄。本次Popen正常exit0，故该异常清理分支没有执行，不能声称它能终止另一个解释器进程。最后wait还没有timeout。
- 失败后原分母正确保留：12主槽0completed/1failed/11not_run，2控制均not_run；首A光栅6次返回。收益仍null。本审不复用作者validate_run再给旧槽改判。

## 本机证据与已有同类恢复

本机`D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/pyvenv.cfg`明确基础解释器为`C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。本地`Lib/venv/__init__.py:282–301`说明Windows把相应入口复制为venvlauncher。当前venv入口277808字节，PE OriginalFilename为py.exe；base解释器107312字节，OriginalFilename为python.exe；两者版本都为3.12.14，SHA与作者诊断一致。

项目已经有更直接的同类证据，而不必从头设计：

1. `D:/hefe/verification/fixes/20261104_visual_benefit004a_r2/qualification/minimal_calibration_r1/RESULT.json`保留原venv入口启动后`broker_owner_binding`和`OwnerDidNotExit`失败，两condition均失败。
2. 同目录`run_minimal_calibration_r2.py:29–34`固定`sys._base_executable`并用小型runpy bootstrap插入原venv site-packages；`:71–72`直接启动base；`:81–88`核NumPy/PIL实际路径、版本和初始化源码摘要。
3. `minimal_calibration_r2/RESULT.json`记录实际两condition成功：N owner/broker PID均35548，P均33356，owner exit0/wait completed，lifecycle_ok=true。命令使用base解释器＋显式venv路径。这是此前正常启动/读取/关闭的实证，不能替代新003的异常清理资格。
4. 更早的`D:/hefe/verification/fixes/20261028_audit_rotation/retired_runtime_v20/verification/test_audit_log_independent.py:162`选择base解释器；`:185`的断言信息明确警示不能把venv启动器当worker。当前问题属于没有复用已知启动条件。

O4/O5a的`harness/qa_resources.py:270`起已有launcher/service的现场OS身份、父PID、创建时间及持有句柄方案，`lifecycle.py`也在产品bootstrap前完成绑定。不过本批是单个Python计算进程，无需搬入该整套三角色生命周期框架。直接消除redirector更小。

## 唯一建议路线

从本机已核验pyvenv.cfg取固定base绝对路径及摘要，用与历史R2同类的极小bootstrap为child显式加入原venv的依赖site-packages，再运行新runtime脚本。固定产品安装路径优先级仍由001 adapter保持，首次依赖验证必须确认NumPy/PIL来自指定venv、Human Eye来自当前固定产品。不要依赖PYTHONPATH绕过-I，也不要伪造sys.prefix去声称完整venv激活；直接base的prefix变化如实记录，验收所需实际包环境一致。

新manifest必须同时记录实际child base exe与bootstrap；002 `source_files()`只封存`sys.executable`、`environment()`只记录控制器入口，换child命令后不能继续只封存旧venv控制器。基础exe的路径/摘要、child os.getpid、Popen.pid、输出目录和同一run标识保持严格核对。固定源码和导入实际路径沿用现有轻量检查，不在每个观察步骤再加一层。

单个直接解释器由原Popen句柄管理。异常时kill后有界wait并核实际退出，不按陈旧裸PID搜索杀进程。使用与正式相同的launch函数、bootstrap和命令参数接受四个无光栅资格，然后在根允许的新批分母执行正式对照：

| 资格 | 必须证明的结果 |
| --- | --- |
| 正常 | 实际依赖import与固定路径/版本一致，Popen PID等于子PID；目录/run一致；正常退出回读。不能只打印PID作为替代。 |
| 非零异常 | 同入口异常结束，真实非零退出被记录，不误标成功、不自动重试。 |
| 超时 | 先握手确认实际runtime已经开始并等待，再触发期限；持有的单解释器句柄kill/wait至退出，记录实际终态。 |
| 回执失败 | 模拟已执行后缺失/无效回执，结果不明或失败保留，不重新执行；既有进程退出/回收完成。 |

若4项通过，根提出同批冻结新入口并自动执行原6配对12主＋2控制新分母的安排可行，无需再增加一次“准备待批”。它们不是002剩余槽续跑，002失败和未知原封保留。图像/几何算法、阈值、主场景与BACK64控制不变。

## 限制与本轮方法

本轮没有实际复现新启动路线，推荐依据为源码、当前PE/配置和此前真实R2原件。新正常/异常/超时/回执失败四资格尚未执行。历史R2两个成功运行不是003成功的预先判定。当前002的launcher-runtime谱系、异常杀启动器能否清理实际解释器，继续unknown。

读取一次大量单行历史JSON产生工具输出截断，之后以只读PowerShell结构化提取关键字段并记录摘要；没有执行其中脚本或修改封存。静态证据与精确路径/摘要保存在`EVIDENCE.json`，抽取脚本为`collect_evidence.ps1`。
