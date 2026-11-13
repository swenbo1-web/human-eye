# 两路本地错误恢复检查的独立回读

只读复核通过 876 项，188份冻结来源保持一致。N1、P1均在第一次实际本地调用通过，未发生本地复测。本次复核仅查看已存本地资料，正式答案、质量和成本未在本复核读取。

两路实际使用最终修正后的 launcher，SHA256均为 `e417a231f7db68d552a56db3f0b94527514c49afdee56a629bbb2f4056ca750c`。该来源同时存在于每路执行来源记录、当前文件和正式冻结清单。末尾局部静态修正已纳入这两次实际控制。

每路实际提交两条新写的普通Python。第一条raise带newlocal消息的ValueError，owner真实返回isError=true，CLI原行status=failed、error=null，content完整保留并附structured_content=null。第二条print(6*7)真实得到42，owner返回isError=false，CLI完成状态正确。候选archive分类依次为tool_error与success，业务绑定、共同故障和outer记录全部通过。

四次实际MCP RPC为initialize、tools/list及两次工具请求。stdio TX/RX、fake RPC记录、owner请求/响应、CLI原stdout、business副本和两级ZIP逐份核对。最终LOCAL_RECOVERED_42由真实工具stdout产生，两路原始usage均为合成0。

两路均在真实STARTED与Windows运行时绑定证明之后正常关闭stdio stdin。正常EXIT回执存在，thin exit0，fixture持有的thin Popen、consumer持有的fake CLI Popen、launcher持有的actor Popen均以原句柄回收，kill_requested=false，三管道与句柄关闭。consumer另持有的只读thin句柄也确认exit0并关闭。原450秒绝对期限贯穿，未重置。

本地共有2个fake CLI、2个stdio和2个actor进程，实际工具4次。真实Pro、光栅、图片构造与交付均为0。owner完整账本、空render_attempts/frames和TRACE再次核对了零尝试。该记录验证接线与恢复，后续正式六槽依原冻结任务单独验收。
