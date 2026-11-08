# CONSUMPTION-CHILD-RECEIPT-001

唯一代码改动：将HE_CHILD_STARTED.json的写入移进已有reader初始化try块。写失败仍调用原close并抛出；正常路径、收据结构、预算与算法不变。不扩展close自身故障矩阵，不加管理层。

三项定向mock对冻结bridge字节直接compile，均通过：STARTED写失败、reader失败控制、正常初始化/close。每例owned fake child均wait1次、kill0次、returncode0，退出收据reaped=true；写失败例没有STARTED收据，仍有EXIT收据。原始TESTS.raw.txt、RESULTS.json及EXECUTED_BYTES.zip在check_01。真实分母3，3通过，0失败/错误/skip；0真实进程、消费者、模型评委、Blender、MCP服务、RPC、API、产品导入。没有重跑旧32或历史矩阵。

runner.py和he_bootstrap.py与34e5aa1逐字节相同；BASE仍指consumption_run_001。旧两个封存目录、267份Git证据/产品字节保持；固定产品仍17db41c/131/01c296b5，题面/真值/四资产/neutral helper及模型/provider/effort/tier、180秒/8答/8会话/1032RPC、非盲数值合同均不改。依赖按固定SHA引用旧目录，没有复制历史。

PREP_PLAN.json为false，PLAN.json为true，二者只有execution_ready不同。true只表示待审执行候选，绝不构成授权：原runner的精确approval文件、PLAN SHA、根STATE独占窗口/cycle/token/granted/截止仍必须全部匹配。本批没有该授权，也没有试运行。17个runtime_components解析路径及SHA已静态逐项核对；未执行旧freeze/测试器。

来源：D:/hefe/verification/fixes/20261107_nearest_contract/CONSUMPTION_CHILD_RECEIPT_ASSIGNMENT.md及review_consumption_run_fix/bridge/REVIEW.md、INDEPENDENT_CHECK.json。MINIMAL.diff只包含该write的保护区移动。INDEPENDENT_REVIEW.md为无执行静态核对。提交并一次回报后结束，等根核最终PLAN SHA并授唯一窗口，不自行消费。
