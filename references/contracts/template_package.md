# 模板包契约

四件套位于 _internal/00_project/template_pack，发布后库条目根等于完整包内容：

- tokens.css：语义化颜色、字体、字号与间距变量。
- skyline_shell.svg 与 assets：该主题底壳及可解析资产。
- primitives/*.svg：完整可渲染的布局原语。
- SPEC.md 与 anchors/*.png：主题标尺、原语用途与实际参考证据。

validate_pack_dir 当前要求至少 5 个原语与 1 张 PNG 锚点；这些是包完整性约束，不是通用画面设计法。原语的画幅、坐标、配色、比例和横幅由主题决定。
SVG 合法性、图片路径和转换能力按 svg_rules / svg_to_ppt_rules 校验，结构齐全不等于视觉正确。

## 审阅版本

四件套审阅面展示底壳、每个原语、tokens、SPEC 与锚点；snapshot.layouts 是页面与收件的同一集合。legacy fidelity 保留源页与 canvas 对照、候选审计和原视觉检查。
批准必须绑定当前 review_id、HTML、template_version 与包文件哈希。consume 对陈旧或有错误的反馈不赋予 approved。改包、预览或源参考后重新审阅。
模板与普通页面分开：当次参考不需入库；publish 一定消费真实当前包确认。
manifest 默认 candidate。只有通过批准检查的 publish 才产生 approved 库条目。
同 ID 替换用 --replace 并保留旧包 .history；发布先复制到 staging，核对批准的字节，再切换。不能无确认删除或覆盖原条目。
