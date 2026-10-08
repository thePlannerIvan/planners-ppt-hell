# 视觉来源与模板入库

只用于幻灯片视觉身份；视频见 [视频路线](03_video_route.md)。一次确认自主设计、库模板、当次参考或提炼入库。已点名的执行，不静默默认。

## 复用或当次参考

库模板：python scripts/template/template_library.py list，然后 apply <project> --template-id <id>。
外部参考预处理：python scripts/template/extract_template_pack.py <source> --project <project>。
实际查看源页和提取事实，制作 tokens.css、skyline_shell.svg、primitives/*.svg、SPEC.md 与 anchors，格式见 references/contracts/template_package.md。具体数值继承参考与已确认方向，不强套通用色盘。
渲染并查看原语。仅用于本次制作的参考无需先入库，继续 checkout 候选画页。

## 人工审阅与发布

四件套与 legacy fidelity 各按当前格式审阅，不用旧 registry 协议假装四件套已通过。

```bash
python scripts/orchestrate/ppt_pipeline.py <project> template-review
python scripts/template/template_library.py publish <project> --template-id <id> --name '<名称>'
```

作者在当前审阅面逐底壳/原语（legacy 是 layout）决定通过、舍弃或返修，全部通过填写模板名。发布消费同一 review_id、HTML 与包版本；修改任何包文件后重新审阅。
同 ID 更新要显式 --replace；旧包保留在库 .history/<id>，不盲删。技术校验不能绕过人工确认。build_manifest 仅生成候选元数据，不赋予入库批准。
