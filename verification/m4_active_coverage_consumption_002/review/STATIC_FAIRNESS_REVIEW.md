# 覆盖消费002静态公平与评分审查

新入口、计划和评分接线未发现静态阻塞。审查方只进行文件读取、字节复制和AST检查，没有导入候选或评分器，没有运行本地会话、协议矩阵、模型、Blender或renderer。实际两个本地检查由根记录，随后按固定合同进入唯一正式批。

## 新来源与路径

launcher显式加载已验candidate driver，并直接向候选run_route/run_batch传入新plan及严格的新002/r绝对输出路径。输入使用旧001 prompt与SOURCES的只读绝对路径，题面SHA固定为 `a063914f32409ef33015c50751ea96a5d7646a672d5570d5eb5c725154c62583`。

新冻结函数显式收集旧176依赖、候选consumer/driver/result_contract三文件、新launcher/PLAN/fake、新评分文件及旧评分源码、两份来源冻结清单和实际CLI/base。其检查使用新FROZEN的完整映射。旧main和旧check_frozen没有承担新入口准入。

运行前后的指针断言覆盖run_batch→run_route→consume_turn→archive_turn，以及统一shared result核查。继承的代码对象继续使用，旧模块原指针保持一致。

## 公共能力和预算

geometry、相机、题面、公共工具、Python/数组、批量渲染、同次调用附图、缓存和主动覆盖算法均沿旧176固定源。旧actor的读审计继续限制管理员文件、旧报告和其它槽。P额外主动入口保持原语义，N可自由计算、选图、批量生成并使用raw数组。N未把图片附给CLI时，可追溯的本会话PNG/数组仍可作为质量证据。

固定顺序为N1、P1、P2、N2、N3、P3，各fresh单轮，原绝对450秒、12工具、六个唯一视图尝试。正式总光栅上限36，准备0。普通业务错误可以恢复，原严格顶层流错误、来源、预算和实际运行状态门继续适用。

new fake只提交自己定义的ValueError和print(6*7)，两路都使用正常EOF。它保留真实failed/error:null/content+structured_content:null投影，依次核业务错误与42恢复，原请求代码不会被执行。已通过的本地组禁止重复，真实失败组最多保留两次尝试，合计最多四次。47项协议矩阵和旧49项准备检查无需重跑。

## 冻结评分

新admin/TRUTH.json与SCORING_SCHEMA.json分别与001原字节相同。新score_answers.py固定旧评分源码SHA `76f0157254f54425e9354f7dbf292f00e5bb719fecdbd2252eaa84608ee06a9e`，复用原Grader类及main代码对象，只在独立globals中将HERE、BATCH和__file__绑定到新批。

AST核查确认旧Grader方法没有HERE/BATCH/ROOT路径依赖。评分器默认读取新002/r权威答案，当前会话frame/meta/pixel绑定继续适用。旧评分模块保持原样。规则schema版本继续使用active-coverage-consumption-001-normalized-v1，新批身份由路径、PLAN和FROZEN绑定。

预注册字段、name/index/ROI别名、任意正确视图组合、unknown边界及执行门均保持。六个原答案全部保存后才独立规范化评分，再解封成本。完整三对资格不足时保留实际分母，不自行开启第三批或修网络凑样。

## 时间和限制

每槽窗口沿原合同覆盖启动、模型工具、CLI/actor/持有stdio句柄退出、归档、回读及发布。新增LAUNCH_TIMING覆盖launcher.main到最终来源/指针回读和发布，解释器启动及main之前模块导入在该窗口之外，应另列。

请求模型仍为CLI0.152.1、gpt-6.1-sol/medium/default和现有ChatGPT登录。fallback警告、服务端resolved设置、provider内部次数及重连前usage覆盖按实际记录。此静态结论没有判断正式质量或收益。
