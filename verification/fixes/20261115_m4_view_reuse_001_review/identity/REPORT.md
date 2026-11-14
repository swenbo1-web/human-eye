# VIEW-REUSE-001 身份与验收覆盖独立复核

结论：固定交付 `a9dd9490d1817630e090975362591ce232d881ae` 的身份和已完成验收链可接受，未发现需因混版撤回或机械重跑全矩阵的问题。本项独立重算6966个字节/身份断言、81个保存数据/回执断言，均通过。它们是审查断言，不是新运行的产品功能测试数量。

复核者 `/root/viewreuse001_identity_acceptance`，当前子Agent句柄 `537d095d9074458f9c1d2cdb3cf976b6`。仅写入根的本证据目录；作者源码、安装、原件和封存未写入。新增产品、模型、Blender、raster和作者验收生成器执行均为0。脚本使用Python标准库解析Git、哈希、NPY/NPZ及原回执，不导入候选产品。

## 固定身份

| 项目 | 独立结果 |
|---|---|
| 起点/候选/冻结/最终 | 6e1e65c6 / d12c7ab2 / 7965c89c / a9dd9490；前三者均为最终祖先 |
| 新旧工作树 | 新树为a9dd9490，旧m4-single-pass-acquisition仍为6e1e65c6，均clean |
| 变更集 | 恰932路径，等于931内容项加manifest自身；全部Git blob与磁盘相同 |
| 产品改动 | 仅active_observation_images.py、active_observation_host.py、live_spatial_mcp.py |
| 执行来源 | 新2162项冻结与旧1796项冻结全部当前哈希相同 |
| 产品141源 | 重新枚举无增漏；候选Git、源码、安装逐字节相同 |
| 源摘要 | 依实际runtime_identity常量/排序manifest独立重算为d8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02 |
| wheel | 整体b9fd0be946230088aa05577b7bbc42a52cd8a820f1d5d6f4d86309b72174dd1a，141运行源成员与候选相同 |
| 原件归档 | 840文件，14,984,596字节；原件、归档、副本登记哈希一致 |

详细输入在 `INPUTS.json`；分组结果在 `RESULT.json`。复核没有用作者的INDEPENDENT标签替代自己的字节计算。

## 最终补丁和验收版本链

首轮19个真实raster、351断言和31个mock单测绑定images `22414d9e74e39c012988a638d50f72e43551a447d4ee747cef8a99ee3947b113`。最终images为 `c66ac2ae5ac0c147990763973fc6bc13cbf4162f7ba4770cceb0fe858cebe697`。

本轮实际删除最终源码中新增的missing-image_ref fallback块，并恢复旧receipt赋值表达式，所得完整源字节SHA恰等于22414d。host/MCP另外两产品源的focused pin与最终源一致。这证明首轮后改动确实限于这条引用路径，未另改raw/patch推导、raster、缓存发布或像素判断。不能将19次旧版矩阵说成在最终版重新执行；也没有必要仅因这6行分支补丁全量重渲染。

修前保存回放实际复现raw/legacy fallback碰撞。修后同一PNG/NPZ/legacy字节、最终source pin下两引用分开，legacy公式稳定；最终31/31 mock通过。首次修后记录保留30通过/1error，错误来自禁止raster的MagicMock隐藏公共签名；该次实际新引用已正确。修guard后的第二次通过不改变产品源。上述三次保存回放均为0新增raster，原受保护文件当前哈希仍一致。

最终安装验收和5配对运行均使用d8ad安装源，2162执行来源仍同字节。安装覆盖正常提供image_ref的新帧，saved-byte补充专门覆盖missing-image_ref，因此最终版本的受影响分支有直接证据。

## 保存数组与原始回执的独立复核

`check_saved_acceptance.py` 对5个64px focused帧及3个最终安装512px产品帧共806,912像素重新读取NPY payload，逐像素验证raw/patch/object/offset/background/depth关系：

- 单patch确有8种真实raw winner，不能用patch编号充数。
- 三对象近远样本保留unsupported面的raw编号，patch仍为-1。
- 等深和裁剪样本的保存winner为原面0，全背景保持三类owner为-1及正无穷深度。
- SCENE/BACK/LEFT的RGB、depth、object和patch数组与旧产品逐字节相同；SCENE原三角形数组另与此前独立native SCENE原件相同。

focused测试代码的direct raw oracle自行从源三角形数量建立全局ID，不从产品patch反推；旧patch oracle独立调用既有内核。原oracle完整数组未另保存，本轮对其逐元素比较只核测试源码与原执行回执，没有再次跑内核。这一oracle独立性限于ID准备/传递，光栅像素算法仍共用原内核。

最终安装4个Owner的实际请求序列和账本核对：

| 路径 | 各次请求后的实际构造数 | 结果 |
|---|---|---|
| 产品观察后三次SCENE | 3,3,3,3 | 三帧总数3，SCENE仅1，后续读取无新增 |
| 原生复用/混合/fresh/变绑定 | 1,1,1,2,3,4,5,6，后续拒绝均6 | 正常命中、批内去重、fresh和真实绑定miss分别计数 |
| 旧帧缺raw能力 | 1,1 | 能力miss后构造一次，随后命中 |
| 好帧→fresh发布失败→旧好帧→恢复→新命中 | 1,2,2,3,3 | 仅第二请求is_error，失败attempt为postprocess_failed，仅两个完整帧注册 |

四Owner原worker结果SHA、错误数组、父进程exit0/关闭均核对。验收代码不仅检查cached布尔，还检查原数组对象别名、旧引用未重定向、文件/摘要未重写和failed构造不退款。重复附图成本由成本复核单独计量。

## 覆盖边界

64px focused为真实raster；128px只用于绑定失效和旧帧拒绝，没有128px新渲染。安装消费域明确固定六个512px相机，256px请求拒绝；不能把拒绝包装成新尺寸支持。固定外部样本只有一个对象，逆序是no-op；真实多对象顺序变更由focused产品重绑与旧帧拒绝覆盖。schema token仅验证失效，camera/projection/map token具有真实miss构造证据。

本项接受上述有界覆盖，不代表通用实时Blender读取缓存、任意尺寸或跨场景采集已测试。没有发现需为本轮missing-image_ref修复重跑旧19矩阵的实质原因。后续模块是否接受整体性能/内存取舍，应结合根的独立源码和成本结果。

## 本轮审查脚本修正

身份脚本首轮6966项中仅fallback完整字节重建失败：我预写了错误变量名 `view_name/image_sha`，且把旧多行表达式写成单行。其余6965项已通过。保留 `check_identity_R1.py` 和 `RESULT_R1.json`，按实际当前源码与旧Git表达式修正重建片段后6966/6966通过。该错误属于审查文本，不是产品缺陷，也没有修改任何作者原件。保存数组复核81项首轮全过。
