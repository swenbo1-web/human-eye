# M4 工具错误结果绑定候选 001

## 验收结果

唯一离线矩阵47/47通过，失败0、未运行0。六个原slot的真实归档和共同核查路径覆盖全部15条实际工具交易，分类为13个success、2个tool_error。另有4项owner式包络正常控制、35项实际调用链负例及2项纯matcher负例。

真实CLI fixture直接取自原stdout的item.completed原行，保存原流SHA、行号、byte offset、原行SHA及owner REQUEST/RESPONSE/RECEIPT来源。派生包络控制单独标记。原始请求中的Python代码字符串仅作为JSON数据读取与复制。

## 修复内容

consumer.archive_turn和driver共同结果核查均使用同一bind_tool_result。成功对应CLI completed，业务错误对应failed，CLI error须明确为null。owner式content/isError和已观测CLI式content/structured_content=null共享完整内容比较。未知包络、顶层JSON-RPC error、状态矛盾、非bool标记和非null结构化数据均拒绝。

即使结果包络原样相等，状态和error检查也会执行。原工具名、完整参数、请求/响应ID、attempt顺序和数量继续绑定。文本内容与图片data、MIME、content顺序保持同一canonical JSON比较路径。

两条此前误拒的真实结果在候选重放中分别识别为SyntaxError业务错误与ValueError业务错误，原951字节及1201字节正文保持一致。

## 真实调用接线

新consumer仅派生archive_turn，新driver仅派生共同核查。原consume_turn、run_route与run_batch复用原code/defaults/closure，创建私有globals副本连接新归档与核查。15项运行时指针与原模块保护断言在回放前后全部成立。正常调用所需consume_turn、packer、safe_environment三项导出已静态核对。

原图片构造账本、完成门、原始stdout及stdio持有句柄代码继续复用。旧176项执行来源与722项已发布原件保持原字节。

## 负例覆盖

| 预期原因 | 案例数 |
| --- | --- |
| CLI_request_differs_from_owner | 3 |
| cli_error_missing | 1 |
| cli_error_non_null | 1 |
| cli_is_error_mismatch | 1 |
| cli_is_error_not_boolean | 1 |
| cli_item_not_tool | 1 |
| cli_result_envelope | 1 |
| cli_status_mismatch | 6 |
| cli_structured_content_non_null | 1 |
| content_mismatch | 5 |
| content_not_json_array | 2 |
| owner_and_CLI_attempt_count | 3 |
| owner_attempt_identity | 1 |
| owner_attempt_order | 1 |
| owner_is_error_not_boolean | 1 |
| owner_jsonrpc_error | 1 |
| owner_original_unreadable | 1 |
| owner_response_envelope | 3 |
| owner_result_envelope | 1 |
| request_response_id_mismatch | 2 |

各负例由登记基线进行一个命名变更，归档与共同核查的首个拒绝原因必须符合预登记原因。正文相等但成功/失败状态错配也会拒绝，缺owner或CLI项由数量绑定拒绝。body字段bool/int的完整JSON类型区分已作源码检查，本轮未新增该字段的派生案例。

## 历史记录与范围

旧六份答案、usage数值与原4completed/2failed状态保持。N1候选协议绑定成功单独记录。N3原顶层stream/reconnect事件仍使事件摘要不合格，旧完整资格继续失败；终止usage数值保留，中断前覆盖与内部provider请求范围仍为unknown。原三配对收益门保持未通过。

本批完成离线原件回放。新增Pro、provider、Codex CLI、actor服务器、Blender及光栅均为0，禁止操作审计尝试为0。用户文件和旧工具动作执行为0。产品与默认安装保持原版本。

本地控制窗口为4.535146秒，覆盖STARTED之后的候选模块加载、47项回放、状态与末尾冻结核对，首次输入核对及最终RESULTS发布单列范围。该时间独立于旧398.8027189秒真实消费批次。

准备阶段的生成脚本语法错误及静态漏导出safe_environment已修正并留存PREPARATION_ERRORS。正式离线矩阵只运行一次，源码与案例清单在开始前固定。

## 固定来源

FROZEN包含996项来源与原件SHA256，SHA256为76a163b53771564a86ac95460e89f986468c58bd36f0527f236b44e3b1e06083。本批基线Git为52d9a838fd52074f3df157aba97e29a5c0cde924。候选源码、原件映射、47项清单、结果及原件归档均在本目录。最终Git与交付清单在回报中提供。

## 管理员复核

候选源码与真实调用接线、原件映射及全部离线结果提交管理员独立复核。在线行为和后续真实消费验收范围由该复核决定。

## 最小离线使用例

输出选择新的目录，读取已固定的源码与原件。当前验收结果位于offline/a01。

```powershell
& 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -I -B -X utf8 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001/replay.py' --run --frozen 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001/FROZEN.json' --output 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001/offline/manual_01'
```

当前候选绑定CLI0.152.1已观测的两种结果包络，未知结构返回protocol_mismatch。matched表示业务状态与完整内容的对应成立，失败工具继续保留tool_error分类。

## 独立复核记录

只读结果复核3107项通过，45份ZIP及560个成员核对一致。实际接线检查确认原模块及三个继承函数的登记globals变动范围，矩阵、旧工具代码及线上服务重跑次数为0。

[离线结果独立复核](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001/review/REPLAY_INDEPENDENT.md)

[实际接线独立复核](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001/review/CONNECTION_REPLAY_REVIEW.md)

[作者最终原件核对](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001/FINAL_AUDIT.json)

