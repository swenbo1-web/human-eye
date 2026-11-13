# 错误结果合同001原件与离线验收准备

15个真实交易已快照提取，分别为13个success和2个tool_error。CLI原件逐条来自旧批 `stdout.raw.bin` 的真实 item.completed 行，保存原行字节、行SHA、整流SHA、行号和字节偏移，并与原consumer工具事件对应。owner REQUEST、RESPONSE、RECEIPT、TOOLS、METRICS和六份答案/CONSUMER/运行状态保持原字节。

六槽public event日志另按原字节保存，供既有事件摘要器复核。N3原usage数值对象保留，断流usage覆盖与scope继续unknown。原4completed、2failed和0not_run不会被候选绑定结果改写。

## 有限清单

CASES.json预登记47项。6个真实完整slot的实际archive/common调用覆盖全部15个原工具交易。4个owner-style正形态从真实CLI content派生，单独标明为表示形态控制。另有35个pipeline负例和2个direct-matcher非法ID负例。每个负例采用一个登记变更，核对具体matcher原因及实际归档/共享检查的首拒绝原因。正文或原result相等时，状态和error条件仍须通过。

replay.py调用新driver实际持有的consumer.archive_turn和driver.common_image_faults，并核code/defaults/closure/kwdefaults及globals指针连接。旧module原指针保持不变。没有调用consume_turn、run_route、原execute_python或任何请求代码。

未变owner响应和TOOLS在staging中保持原字节。候选CLI表示与变更记录另存，真实CLI原行继续保存。N3事件摘要沿用原完整public event日志，其顶层错误必须继续拒绝；N1候选工具绑定匹配只作为协议结果保存。

## 执行边界

目前只执行快照提取和AST解析。候选import、matcher调用与矩阵运行均为0。正式启动由根在冻结候选、fixture manifest和47项清单后进行。harness要求新输出目录，并在运行前后核冻结与旧原件SHA。离线audit禁止Popen、os.system、socket.connect和socket.bind，正常Python模块import保持可用。

候选输出、每项归档、精确拒绝原因、连接检查、13/2分类、原slot状态和局部运行时间会写入本批新目录。矩阵通过前不宣布修复验收通过，也不改写历史收益门。

建议调用形式如下。

```text
python -I -B -X utf8 replay.py --run --frozen FROZEN.json --output r/a01
```

冻结文件采用files_sha256或runtime_sources的绝对路径到SHA映射。根控制唯一离线执行、失败原件和后续明确修订。此准备没有新增Pro、provider、CLI、actor服务器、Blender或光栅。
