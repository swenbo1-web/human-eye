# 双路图片消费001：独立交付与回答复核

作者固定提交 `a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff`。本子任务只读源码和原始事件，自写 `audit_delivery.py` 解码图片并核对owner→stdio→CLI内容链；没有导入作者helper、评分器或validator，没有新模型、CLI试验、Blender、光栅或API调用。根另负责完整Git/冻结身份，生命周期与完整成本由其它分工复核。

**当前两路有限传图及图片回答资格通过。95项独立核查全部通过。** 这不是原生与插件的任务收益对照，也没有证明服务端内部模型版本或请求体。

## 本轮实际观察

| 项目 | N | P |
|---|---|---|
| 实际fresh线程 | 01a1d46e-929e-7370-b404-36c1089cf06c | 01a1d46e-edb6-7bd2-9bad-e246722a0cfe |
| 用户轮次 | 一个，无resume | 一个，无resume |
| 实际工具 | read_image(view-a)、read_image(view-b) | human_eye_image_observe([view-a,view-b]) |
| owner/stdio/CLI image content | 两张，逐字节原PNG | 两张，逐字节原PNG |
| 引用顺序 | view-a，view-b | view-a，view-b |
| 原PNG载荷 | 6699B | 6699B |
| 其它计算工具 | 无 | 无 |
| 最终回答 | view-b有浅灰菱形排列，view-a几乎空白仅微小亮点 | 相同且描述与像素一致 |

实际MCP started与completed事件、工具参数、owner原请求/响应、stdio TX/RX全部匹配。CLI对成功响应的envelope规范化为content与structured_content=null；content本身完整相同，没有因兼容性映射丢图片。两路展平后的四段label/image内容逐字节相同。原ZIP内events/final/PUBLIC_FINAL也与当前原件一致。

两路最终回答均在全部图片completed事件之后产生；实际调用没有execute_python、shell或其它可算像素的工具。最终公开回答、原始agent_message和final.txt一致。这个事实支持“图片内容参与了本轮回答”的有限判定，未把provider/model内部未公开层改成可直接观测。

独立PIL解码结果：view-a背景RGB为18/22/30，只有3个前景像素，范围x252–256、y254–255。view-b同背景，有12634个前景像素，范围x61–487、y117–364。直接目视两原图也显示前者几乎空白、后者为横向分布的浅灰菱形。PNG只有IHDR/IDAT/IEND，无文本元数据或隐藏路径标签。这里的计像素是管理员离线核验，未进入实验模型上下文。

## 可见上下文与设置

两路题面为相同378B，SHA256 `600f5b721edce87ca10c0e8832b66ffe39c8c74db56d4268a72399a2c7eb8fea`，与started/consumer的实际stdin绑定一致。它要求区分一张几乎空白和一张有轮廓，但没有给哪张对应哪个答案。

公开工具schema只含opaque refs、图片尺寸/MIME和调用能力。实际图像工具文本严格为 `view-a (512x512, image/png)`、`view-b (512x512, image/png)`；没有BACK/SCENE原名、owner/depth、ROI、目标数量、前景数或期待答案。公共Python namespace只提供opaque文件映射；实际两路均没有调用它。`actor.py:165–178` 调用同一image_content再生成标签，私有receipt没有进入public content。

实际命令均为冻结CLI0.152.1、gpt-6.1-sol请求、medium努力、default服务、ChatGPT登录方式；除路线工具和路径外，所有 `-c` 设置一致。原生共有execute_python/read_image，P另外暴露多ref observe。`--ignore-user-config --ignore-rules --strict-config` 与禁用项目文档、记忆、Hook、shell/内置图片入口等设置已记录。这里审的是捕获的配置、stdin、schema和工具响应，不宣称获得了服务端完整内部上下文。

两路均保留skip_host_skill_discovery开发特性警告，以及gpt-6.1-sol模型元数据缺失、fallback metadata警告；之后实际turn.completed与输出存在。可声称两路请求参数相同，不能声称已直接核实服务端resolved model、resolved effort或内部图像token。CONSUMER中的provider_delivery_confirmed、model_view_confirmed、resolved_effort、provider_requests均仍为null，与报告边界一致。

## 一项未触发的计量边界

当前成功的4张真实图片不存在计量差异。不过复用helper前应修正一处具体静态路径：`image_content.py:132` 已完成block构造，`:137` 再检查期限，`:138` 才写constructed=true。若恰在编码完成后期限到达，异常receipt保留base64/字节，但仍写constructed=false，`actor.py:173` 将其归入construction_failures，而`:140–143`的构造汇总只统计成功列表。

因此潜在“已构造但不可交付”的内容会漏出成功构造汇总。原失败receipt并未完全丢失，本批也没有发生此异常；它不推翻本轮4图传输资格。最小处理是在实际构造完成点就记录不可回退的构造成本，把交付状态另外记账，补一次本地编码后超时控制即可，无须新模型试验或安全层。此处仅静态审阅，没有运行作者helper/异常试验。

## 下一轮正式消费的公平边界

当前N每次只能read一个ref，P有多ref出口，且题面允许多ref优先；这种接线有意验证两个出口，都完成资格，但工具轮数与27.9s/16.0s差异不能作为引擎收益。

根拟定的三配对“有限六视角矩形覆盖证据”任务可以接在本资格之后，最低要求如下：

1. 两路拿同一完整几何与相机，公开相同任务定义：独立单面矩形、前向、完整无遮挡/不出画面以及16表面/4边界/24对比的可读性规则。不供目标ID/数量/推荐视序；让N知道应解决什么，不能只有P知道内部判据。
2. 两路共用批量render_views和图像出口。N可一次请求六图，也可自由写代码自行选图、算像素和缓存，不强制固定六图或必须用视觉推理。
3. raw geometry/cameras/RGB-owner-depth数组放在同等持久Python上下文，工具返回稳定handle及所需图片；不把所有NPZ展开喂给N模型制造传输劣势。两路拥有相同数据读取与缓存预算。
4. P额外主动覆盖入口必须实际使用已冻结index→choose→render→反馈的代码，从本轮输入重新算结果，不回放001/003预存答案。首次index、实际出图、编码发布、模型消费和回读均记完整成本。
5. 同6个unique相机上限、12工具/450秒原期限与3配对完整分母。失败和未运行保留、不补样刷过；质量先判真实覆盖证据与有限池unknown，再算完整时间/usage。

该试验只回答几何事实和观察规划能否被模型更省地消费。当前28对象/200顶点/276三角形、灰色面板、固定六相机不是通用复杂资产语义任务。无需新增材质、专家模型或新能力来完成这轮。

完整逐项检查、原始输入摘要、实际工具/回答和独立像素数据见RESULTS.json；95项有重叠，不是95个新模型测试。未测：provider内部收件与resolved配置、视觉泛化、正式消费性能、故障构造成本控制；stdio退出unknown交生命周期复核，不在这里回填正常EOF。
