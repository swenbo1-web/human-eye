# 初稿失败记录

review_saved_initial.py 首次离线执行失败，异常为 `SCENE all pixel foreground rays`。

初稿逆相机射线未限制 NDC 视锥。当前像素中心为 integer+0.5，屏幕映射使用 511，因此末行和末列的中心位于 [-1,1] 之外。原产品先作 NDC 裁剪，局部盖盒覆盖整幅时显现该差异。修订 checker 先按原公开 projection 限制 NDC X/Y，随后核对保存像素。

本次修订只更正离线检查器的视锥域，保持原始 PNG、NPZ、公开响应及产品代码。初稿源完整保存。
