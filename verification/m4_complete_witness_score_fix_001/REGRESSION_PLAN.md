# 离线回归与人工控制

本批沿已保存的一个模型样本，产品、题面、原归一化答案、helpers、真值、阈值、原自动失败和原质量 seal 保持原字节。原生产者 RUN_RESULT 与 CONSUMER 的完整字节仅复制到 fixtures，两份合计125372字节，其原路径、SHA、大小见 PROVENANCE.json。

## 固定分母与顺序

先由根对真实原件执行派生完整评分，输出新目录的 SUPPLEMENTARY_QUALITY.json。它需要从真实终态读取继续到原内容判定。此结果存在且通过后，harness 才开始。

主矩阵固定21个逻辑案例。

- P00 为真实生产者字节回归，纯 reader 与完整 scorer 均使用原终态和原答案。真实 held-handle exit 的 confirmed 为 true，原 exit_code 为1，测试不新增 exit0 条件。
- T01–T18 分别改动一个终态条件，覆盖缺失/失败顶层state、launcher失败、独立postcheck错误、缺失/空/多条记录、错误slot/group/schema、三个计数为0、外层retry为1、原row无效、consumer无效及绑定/退出未确认。
- W01 将目标见证改为实际当前 SCENE 的第一条 readable 行，使用该行的真实ref、37917/924计数和actual-owned anchor。原公共完整见证index2保持。要求完整性拒绝，并允许同时产生与该替换直接关联的index/frame一致性拒绝。保存的独立测量必须再次确认该行 complete=false、readable=true，计数与引用完全相同。
- W02 只将目标ref改为不存在的人工控制ref，原TOP、计数、像素、身份和原文支持全部保留。要求实际ref不存在，并精确得到目标见证和index/frame关联的拒绝。

每个案例都先运行真实 terminal_binding，再走真实派生 score(arguments) 输出路径。终态反例应在新reader拒绝处退出，failed_fields及完整scorer errors须与预注册的具体字段完全一致。两个内容负例必须通过终态检查，errors集合只能包含注册的两项目标见证错误，其他输入错误不能代替所需拒绝。

另有1个独立输出保护辅助检查。它在新测试目录的实际完整评分输出路径预置小型sentinel，再以真实正例调用score。必须在该路径收到FileExistsError并保持sentinel SHA不变。辅助分母1单独记录，主矩阵仍为21。

如全部运行，根独立首评分1次，harness主矩阵21次完整score入口，加输出保护辅助1次，共23次离线score入口。18终态负例在新reader处早退。所有入口使用同一份原模型证据，不增加模型样本。

## 注入范围与保护

暂时包装派生模块的load，仅在它读取原saved_evidence模块后，为该模块的oracle.read提供三个精确路径的内存深拷贝覆盖，分别是RUN_RESULT、CONSUMER、NORMALIZED。每次case从fixtures和原NORMALIZED重新深拷贝，只应用注册的人工变更。其他JSON读取、SHA函数、原文、PNG/NPZ、产品事实和原helpers继续使用原件。

这属于离线控制注入，人工NORMALIZED变更不会写入原文件，也不会当作模型输出。原来源SHA保持原始含义，READ_OVERLAY记录明确指出哪些读被控制。测试不重新分类tool2/tool3，真实正例必须继续判direct=false且保留原生补核。

测试前后对原namespace与整个原runtime目录逐文件SHA比较。harness禁止进程启动、网络连接、产品模块执行和结果目录外写入，关闭bytecode生成。结果目录独占创建，遇意外异常保留当前原件并停止余下矩阵，未运行项保留在分母。

## 冻结与执行

REGISTRY.json注册21个主案例、1个辅助检查、20项源/输入SHA、人工注入方式和精确拒绝字段。regression.py已仅做AST解析，尚未运行reader、score、产品或模型。

准备闭包经根冻结后，先执行独立首评分，然后运行以下命令。

```powershell
& 'C:/Users/Administrator/.codex/worktrees/2c7d/hefe/verification/fixes/surface_facts_001/engineering_b/venv/Scripts/python.exe' -I -B -X utf8 'verification/m4_complete_witness_score_fix_001/regression.py' --output 'C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_complete_witness_score_fix_001/regression_01'
```

输出为每case的CONTROL、TERMINAL、FULL_SCORE、READ_OVERLAY、stdout/stderr、RESULT，以及整批before/after哈希与未运行记录。原自动失败0/1、原人工语义支持1/1和本次派生结果分别呈现。
