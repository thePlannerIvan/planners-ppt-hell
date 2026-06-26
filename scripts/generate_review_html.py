"""
Generate 02_visual_review.html from page_manifest.json, validation, and self-review data.

Reads pages from page_manifest.json (the single source of truth for page ordering and paths),
validation results from validation_summary.json, and self-review from self_review.json.
Fails loudly when validation is missing or PNG paths are broken. Non-blocking
validator warnings are internal evidence for model self-review; the user-facing
page shows model-synthesized design suggestions instead of raw warning actions.

Usage:
  python generate_review_html.py <project_dir> [--batch BATCH_ID] [--output <path>]
  python generate_review_html.py <project_dir> --batch BATCH_ID --debug-show-failures
"""

import argparse
import json
import sys
from pathlib import Path

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>视觉审阅 — {project} — {batch_label}</title>
<style>
  :root{{--ink:#17202A;--muted:#6B7480;--soft:#EEF2F6;--paper:#FFFFFF;--line:#DDE4EC;--navy:#051C2C;--accent:#D46A00;--ok:#007A53;--danger:#E60012;--blue:#006BA6;--wash:#F7F9FC}}
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;background:linear-gradient(180deg,#E9EEF4 0,#F5F7FA 320px);color:var(--ink);line-height:1.58;letter-spacing:0}}
  .header{{background:rgba(5,28,44,.96);color:#FFF;padding:16px 30px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;position:sticky;top:0;z-index:10;box-shadow:0 10px 26px rgba(5,28,44,.16)}}
  .header h1{{font-size:23px;font-weight:850}}
  .status-bar{{display:flex;gap:12px;font-size:14px}}
  .status-bar .pass{{color:#8BC34A}} .status-bar .warn{{color:#FFC107}} .status-bar .fail{{color:#FF5252}}
  .workspace{{max-width:1620px;margin:0 auto;padding:22px 24px;display:grid;grid-template-columns:176px minmax(0,1fr);gap:18px;align-items:start}}
  .side-nav{{position:sticky;top:92px;background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:8px;padding:10px;box-shadow:0 14px 36px rgba(5,28,44,.08);backdrop-filter:blur(10px)}}
  .side-nav-title{{font-size:13px;font-weight:850;color:var(--muted);margin-bottom:10px}}
  .nav-list{{display:flex;flex-direction:column;gap:7px;max-height:calc(100vh - 138px);overflow:auto;padding-right:2px}}
  .nav-item{{display:grid;grid-template-columns:8px 1fr;align-items:center;gap:7px;padding:8px 9px;border-radius:7px;color:#46515E;text-decoration:none;font-size:12px;font-weight:800;background:#F5F7FA;border:1px solid transparent;transition:.16s ease}}
  .nav-item:hover,.nav-item.active{{background:#FFF7EB;border-color:#F0C48C;color:#8A4700;transform:translateX(2px)}}
  .nav-dot{{width:8px;height:8px;border-radius:50%;background:#007A53;flex:0 0 auto}}
  .nav-dot.warning{{background:#D46A00}}
  .container{{min-width:0}}
  .global-alert{{padding:14px 20px;border-radius:8px;margin-bottom:20px;font-size:15px;font-weight:850}}
  .global-alert.error{{background:#FFEBEE;color:#C62828;border:2px solid #E60012}}
  .global-alert.warning{{background:#FFF3E0;color:#D46A00;border:2px solid #D46A00}}
  .page-review{{background:var(--paper);border-radius:8px;margin-bottom:26px;box-shadow:0 18px 44px rgba(5,28,44,.08);overflow:hidden;border:1px solid var(--line)}}
  .page-review.fail{{border-left:5px solid #E60012}}
  .page-review.warning{{border-left:5px solid #D46A00}}
  .page-review.pass{{border-left:5px solid #007A53}}
  .page-head{{padding:18px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);flex-wrap:wrap;gap:8px;background:linear-gradient(180deg,#FFFFFF,#FAFBFD)}}
  .page-head h2{{font-size:22px;line-height:1.35;font-weight:900;max-width:1040px}}
  .page-meta{{font-size:13px;color:#8A929C;font-weight:800}}
  .page-body{{padding:22px 24px 24px}}
  .review-grid{{display:grid;grid-template-columns:minmax(720px,1.55fr) minmax(380px,.75fr);gap:24px;align-items:start}}
  .preview-panel{{position:sticky;top:104px}}
  .qa-panel{{min-width:0}}
  .preview-row{{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}}
  .preview-box{{flex:1;min-width:340px;max-width:100%}}
  .preview-box img{{width:100%;border:1px solid var(--line);border-radius:8px;background:#FAFAFA;box-shadow:0 18px 44px rgba(5,28,44,.10)}}
  .preview-box .vlabel{{font-size:12px;color:#999;margin-bottom:4px;font-weight:bold}}
  .grid-2col{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
  @media(max-width:800px){{.grid-2col{{grid-template-columns:1fr}}}}
  .section-label{{font-size:13px;font-weight:900;color:#8A929C;margin-bottom:8px;letter-spacing:0;margin-top:14px}}
  .section-label:first-child{{margin-top:0}}
  .val-summary{{background:#F7F9FC;border-radius:8px;padding:13px 16px;margin-bottom:14px;font-size:15px;border:1px solid var(--line);font-weight:850}}
  .val-summary .status-pass{{color:#007A53}} .val-summary .status-warn{{color:#D46A00}} .val-summary .status-fail{{color:#E60012}}
  .required-fixes{{background:#FFEBEE;border:2px solid #E60012;border-radius:8px;padding:12px 16px;margin-bottom:16px}}
  .required-fixes .rf-title{{font-size:15px;font-weight:bold;color:#C62828;margin-bottom:6px}}
  .required-fixes .rf-subtitle{{font-size:12px;color:#999;margin-bottom:6px}}
  .required-fixes li{{font-size:14px;color:#C62828;margin-left:18px;margin-bottom:2px}}
  .self-review-status{{margin-bottom:16px;padding:10px 14px;border-radius:8px;font-size:14px}}
  .self-review-status.blocked{{background:#FFEBEE;color:#C62828;border:1px solid #E60012}}
  .self-review-status.revise{{background:#FFF3E0;color:#D46A00;border:1px solid #D46A00}}
  .self-review-status.pass{{background:#E8F5E9;color:#007A53;border:1px solid #007A53}}
  .self-review-status.human_review{{background:#E3F2FD;color:#006BA6;border:1px solid #006BA6}}
  .review-actions{{display:grid;gap:10px;margin-bottom:16px}}
  .review-action{{display:grid;grid-template-columns:22px 1fr;gap:12px;padding:14px 16px;background:#FFF;border:1px solid var(--line);border-radius:8px;cursor:pointer;transition:.16s ease}}
  .review-action:hover{{border-color:#007A53;background:#F2FBF7;transform:translateY(-1px)}}
  .review-action input{{width:22px;height:22px;accent-color:#007A53;margin-top:2px}}
  .action-title{{font-size:15px;font-weight:900;color:#26323F;margin-bottom:3px}}
  .action-desc{{font-size:13px;color:#66717E;line-height:1.45}}
  .action-meta{{font-size:12px;color:#9AA2AC;margin-top:5px;font-weight:800}}
  .action-source{{display:inline-block;border-radius:999px;padding:2px 8px;margin-right:6px;background:#EEF2F6;color:#66717E}}
  .accept-note{{background:#F7F9FC;border:1px solid var(--line);border-radius:8px;padding:10px 12px;color:#6B7480;font-size:13px;margin-bottom:14px}}
  .tech-details{{border:1px solid var(--line);border-radius:8px;background:#FFF;margin-bottom:14px}}
  .tech-details summary{{cursor:pointer;list-style:none;padding:13px 14px;font-weight:850;color:#66717E}}
  .tech-details summary::-webkit-details-marker{{display:none}}
  .tech-details ul{{padding:0 18px 14px 32px}}
  .tech-details li{{font-size:13px;color:#66717E;margin-bottom:4px}}
  .revision-notes{{margin-top:18px;background:#F7F9FC;border:1px solid var(--line);border-radius:8px;padding:14px 16px}}
  .revision-notes-title{{font-size:15px;font-weight:900;color:#26323F;margin-bottom:8px}}
  .revision-grid{{display:grid;gap:9px}}
  .revision-block{{background:#FFF;border:1px solid #E8ECF2;border-radius:8px;padding:10px 12px}}
  .revision-block strong{{display:block;font-size:13px;color:#7A8490;margin-bottom:4px}}
  .revision-block li{{font-size:13px;color:#46515E;margin-left:18px;margin-bottom:3px}}
  .suggestions{{display:grid;gap:10px;margin-bottom:18px}}
  .suggestions label{{display:flex;align-items:center;gap:12px;padding:15px 16px;font-size:16px;color:#39424E;cursor:pointer;background:#FFF;border:1px solid var(--line);border-radius:8px;min-height:58px;transition:.16s ease}}
  .suggestions label:hover{{border-color:#007A53;background:#F2FBF7;transform:translateY(-1px)}}
  .suggestions input,.approve-row input{{width:22px;height:22px;accent-color:#007A53;flex:0 0 auto}}
  .feedback-text textarea{{width:100%;min-height:92px;border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:16px;font-family:inherit;resize:vertical;background:#FFF}}
  .action-zone{{position:sticky;bottom:14px;background:rgba(255,255,255,.94);border:1px solid var(--line);box-shadow:0 14px 34px rgba(5,28,44,.10);border-radius:8px;padding:14px;margin-top:10px;backdrop-filter:blur(10px)}}
  .approve-row{{display:flex;align-items:center;gap:12px;padding:14px 16px;font-size:16px;background:#F7FBF8;border:1px solid #CFE8D8;border-radius:8px;font-weight:850}}
  .submit-area{{text-align:center;padding:16px 0 40px}}
  .submit-btn{{background:var(--danger);color:#FFF;border:none;padding:14px 40px;font-size:18px;font-weight:850;border-radius:8px;cursor:pointer;margin:0 6px;box-shadow:0 12px 28px rgba(230,0,18,.18)}}
  .submit-btn.green{{background:#007A53}}
  .toast{{position:fixed;top:20px;right:20px;background:#051C2C;color:#FFF;padding:14px 24px;border-radius:8px;font-size:15px;display:none;z-index:999}}
  .toast.show{{display:block}}
  .project-credit{{max-width:1620px;margin:0 auto 28px;padding:0 24px;text-align:center;color:#8A929C;font-size:13px;font-weight:800}}
  .project-credit a{{color:#59636F;text-decoration:none;border-bottom:1px solid #C8D0DA}}
  .missing-file{{background:#FFEBEE;color:#C62828;padding:8px 12px;border-radius:6px;font-size:13px;margin-bottom:8px;border:1px solid #E60012}}
  /* Compact visual review UI override. */
  body{{background:#EEF3F8;color:#182433}}
  .header{{background:#06131B;padding:20px 40px;display:grid;grid-template-columns:1fr auto;grid-template-areas:"title status" ". brand";align-items:center;gap:8px 18px;box-shadow:none;transition:padding .18s ease}}
  .header h1{{grid-area:title;font-size:24px}}
  .header .creator{{grid-area:brand;justify-self:end;font-size:15px;font-weight:900;color:#FFFFFF;margin-left:0;white-space:nowrap}}
  .status-bar{{grid-area:status;justify-self:end;align-self:center}}
  body.review-scrolled .header{{padding:10px 40px;grid-template-areas:"title status"}}
  body.review-scrolled .header .creator{{display:none}}
  body.review-scrolled .header h1{{font-size:21px}}
  .workspace{{max-width:none;padding:14px 18px 14px 0;grid-template-columns:104px minmax(0,1fr);gap:0}}
  .side-nav{{justify-self:center;top:92px;width:46px;padding:8px 5px;border-radius:9px;box-shadow:0 10px 28px rgba(5,28,44,.08)}}
  body.review-scrolled .side-nav{{top:58px}}
  .side-nav-title{{display:none}}
  .nav-list{{counter-reset:batchNav;align-items:center;gap:8px;max-height:calc(100vh - 120px);padding:0;overflow:visible}}
  .nav-item{{counter-increment:batchNav;display:grid;grid-template-columns:1fr;place-items:center;width:32px;height:32px;padding:0;border-radius:999px;background:#F4F7FA;font-size:0;line-height:1}}
  .nav-item::before{{content:counter(batchNav);display:block;width:100%;height:32px;font-size:13px;font-weight:950;line-height:32px;text-align:center;transform:translateY(1px);color:#66717E}}
  .nav-item:hover,.nav-item.active{{transform:none;background:#FFF4E3;border-color:#F0C48C}}
  .nav-item:hover::before,.nav-item.active::before{{color:#D46A00}}
  .nav-dot{{display:none}}
  .page-review{{border-radius:9px;margin-bottom:18px;box-shadow:0 10px 26px rgba(5,28,44,.05)}}
  .page-review.fail,.page-review.warning,.page-review.pass{{border-left:1px solid var(--line)}}
  .page-head{{padding:18px 28px}}
  .page-head h2{{font-size:22px}}
  .page-body{{padding:18px 28px}}
  .review-grid{{grid-template-columns:minmax(760px,1.65fr) minmax(330px,.62fr);gap:22px}}
  .preview-panel{{top:96px}}
  .preview-box img{{box-shadow:none;border-color:#E6ECF3}}
  .val-summary,.accept-note,.review-action,.feedback-text textarea,.approve-row,details.self-review-status{{border-color:#E6ECF3}}
  .page-meta,.section-label{{font-size:12px}}
  .review-action{{padding:12px 14px}}
  .action-title{{font-size:14px}}
  .action-desc,.action-meta,.accept-note{{font-size:12px}}
  details.self-review-status{{padding:0;overflow:hidden}}
  details.self-review-status summary{{list-style:none;cursor:pointer;padding:11px 14px;font-weight:900}}
  details.self-review-status summary::-webkit-details-marker{{display:none}}
  .self-review-body{{padding:0 14px 12px;line-height:1.7;color:inherit}}
  .approve-row{{cursor:pointer}}
  .action-zone{{box-shadow:0 10px 28px rgba(5,28,44,.08)}}
  .submit-area{{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:12px;padding:28px 0 34px;background:linear-gradient(180deg,#EEF3F8,#F7F9FC)}}
  .submit-btn{{min-width:210px;border-radius:10px;margin:0;padding:13px 28px;box-shadow:none}}
  .submit-area div,.submit-area p{{flex-basis:100%;text-align:center}}
  .project-credit{{font-size:14px;padding-bottom:22px}}
  @media(max-width:1100px){{.workspace{{grid-template-columns:1fr;padding-left:18px}}.side-nav{{position:static;width:auto}}.nav-list{{flex-direction:row;overflow:auto}}.review-grid{{grid-template-columns:1fr}}.preview-panel{{position:static}}.header{{grid-template-columns:1fr;grid-template-areas:"title" "brand" "status"}}.header .creator,.status-bar{{justify-self:start;white-space:normal}}}}
</style>
</head>
<body>
<div class="header">
  <h1>视觉审阅: {project} — {batch_label}</h1>
  <div class="creator">小红书 @阿祖不看 TVC</div>
  <div class="status-bar">
    <span class="pass">页面: {count_pass}</span>
    <span class="warn">设计建议: {count_warn}</span>
    <span class="fail">阻断: {count_fail}</span>
  </div>
</div>
<div class="workspace">
  <aside class="side-nav">
    <div class="side-nav-title">批次导航</div>
    <nav class="nav-list" id="pageNav"></nav>
  </aside>
  <main class="container" id="container">{global_alerts}</main>
</div>
<div class="submit-area">
  <button class="submit-btn green" onclick="submitFeedback()">提交批次反馈</button>
  <button class="submit-btn" onclick="approveAll()">全部通过并继续</button>
  <div style="margin-top:12px">
    <input id="approvalKey" type="password" autocomplete="off" placeholder="人工审批口令（批准时必填）" style="width:min(420px,90%);padding:12px 14px;border:1px solid #D6DEE8;border-radius:8px;font-size:16px">
  </div>
  <p style="margin-top:12px;font-size:14px;color:#999">请使用本地审阅服务器提交反馈，不要直接打开 file:// HTML。</p>
</div>
<div class="toast" id="toast"></div>
<footer class="project-credit">
  Planner's PPT Hell © 2026 · 小红书 @阿祖不看 TVC · 网站 <a href="https://demyth.info" target="_blank" rel="noreferrer">demyth.info</a>
</footer>
<script>
var pages = {pages_json};
var validation = {validation_json};
var selfReview = {self_review_json};
var versions = {versions_json};
var revisionNotes = {revision_notes_json};
var batchId = "{batch_id}";
var hasSelfReview = {has_self_review};
var visionAvailable = {vision_available};
var visionUnavailableReason = {vision_unavailable_reason_json};
var hasValidation = {has_validation};

function escapeHtml(s) {{
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function assetUrl(path) {{
  if (!path) return '';
  if (location.protocol === 'file:' && path.indexOf('/_internal/') === 0) {{
    return path.slice(1);
  }}
  return path;
}}

var pageActionCache = {{}};

function warningActionSpec(issue) {{
  var code = issue.code || '';
  var msg = issue.message || '';
  var text = code + ' ' + msg;
  if (/FONT_TOO_SMALL|FONT_SIZE|MISSING_FONT|font-size/i.test(text)) {{
    return {{
      id:'font_readability',
      title:'小字或字体风险',
      desc:'提高小字号、减少次级说明，优先保证投影和 PPT 编辑后的可读性。'
    }};
  }}
  if (/TEXT_OVERFLOW_MAJOR/i.test(text)) {{
    return {{
      id:'text_overflow_major',
      title:'文字明显放不下',
      desc:'优先拆行、扩大容器或减少上屏文字；这是进入审阅前最值得修的文字容量问题。'
    }};
  }}
  if (/TEXT_CONTAINER_TIGHT|TEXT_BASELINE_ESTIMATE_DRIFT|OVERFLOW|贴边|overflow/i.test(text)) {{
    return {{
      id:'text_fit',
      title:'文字贴边或估算偏差',
      desc:'先看左侧 PNG 是否真的拥挤；若肉眼可接受，可不修，若显得紧再拆行或扩大容器。'
    }};
  }}
  if (/HIGH_TEXT_DENSITY|density|text elements/i.test(text)) {{
    return {{
      id:'reduce_density',
      title:'信息密度偏高',
      desc:'合并重复标签，删除非关键注释，保留主判断和关键证据。'
    }};
  }}
  if (/PALETTE|COLOR|Colors outside/i.test(text)) {{
    return {{
      id:'color_consistency',
      title:'颜色可能偏离规范',
      desc:'检查是否需要统一色板；如果这是品牌色覆盖，请在反馈中确认接受。'
    }};
  }}
  if (/SAFE_MARGIN|UNSAFE_MARGIN|bounds|outside/i.test(text)) {{
    return {{
      id:'safe_margin',
      title:'元素靠近边界',
      desc:'调整元素位置，避免导出或投影时显得拥挤、被裁切。'
    }};
  }}
  if (/TEXT_ANCHOR_MIDDLE_LONG|text-anchor/i.test(text)) {{
    return {{
      id:'long_center_text',
      title:'居中文本过长',
      desc:'改成左对齐或拆行，降低 PPT 编辑后跑版风险。'
    }};
  }}
  if (/same page_mode|same visual_density|rhythm/i.test(text)) {{
    return {{
      id:'deck_rhythm',
      title:'页面节奏重复',
      desc:'调整页面信息密度或视觉模式，避免连续页面观感过于相似。'
    }};
  }}
  if (/LARGE_EMPTY_REGION|LOW_MODULE_UTILIZATION|TABLE_READABILITY_RISK|VISUAL_WEIGHT|DENSITY_IMBALANCE/i.test(text)) {{
    return {{
      id:'layout_quality',
      title:'版面空间利用或视觉重心不稳',
      desc:'检查是否存在大块无功能空白、表格占位低效或上下左右重量失衡；优先改模块结构，不要只微调坐标。'
    }};
  }}
  return {{
    id:'review_warning',
    title:'其他可检查风险',
    desc:'存在非阻断质量提示，可人工检查页面细节后决定是否优化。'
  }};
}}

function buildReviewActions(suggestions) {{
  var actions = [];
  (suggestions || []).slice(0,3).forEach(function(sug, si) {{
    actions.push({{
      action_id: 'self_' + (sug.id || si),
      label: sug.text || '模型建议优化',
      description: sug.basis
        ? ('设计建议：' + String(sug.type || 'visual').toUpperCase() + ' · ' + String(sug.basis))
        : (sug.type ? ('设计建议：' + String(sug.type).toUpperCase()) : '设计建议'),
      source: 'self_review',
      source_index: si,
      source_codes: [],
      messages: [sug.text || '']
    }});
  }});
  return actions;
}}

function renderReviewActions(pageKey, idx, actions) {{
  pageActionCache[pageKey] = actions || [];
  if (!actions || !actions.length) {{
    return '<div class="accept-note">没有建议修改项。若页面效果可接受，可直接确认通过。</div>';
  }}
  var html = '<div class="review-actions">';
  actions.forEach(function(a, ai) {{
    var meta = '来源：模型综合视觉判断';
    html += '<label class="review-action">';
    html += '<input type="checkbox" name="action_'+idx+'" value="'+ai+'">';
    html += '<div><div class="action-title">'+escapeHtml(a.label)+'</div>';
    html += '<div class="action-desc">'+escapeHtml(a.description || '')+'</div>';
    html += '<div class="action-meta"><span class="action-source">'+escapeHtml(a.source || '')+'</span>'+escapeHtml(meta)+'</div>';
    html += '</div></label>';
  }});
  html += '</div><div class="accept-note">勾选表示“下一轮请修”。不勾选的设计建议视为本轮人工接受或暂不处理。</div>';
  return html;
}}

function renderRevisionNotes(pageKey) {{
  var notesRoot = revisionNotes || {{}};
  var pagesNotes = notesRoot.pages || notesRoot;
  var n = pagesNotes[pageKey];
  if (!n) return '';
  function block(title, arr) {{
    if (!arr || !arr.length) return '';
    var html = '<div class="revision-block"><strong>'+escapeHtml(title)+'</strong><ul>';
    arr.forEach(function(item) {{ html += '<li>'+escapeHtml(item)+'</li>'; }});
    html += '</ul></div>';
    return html;
  }}
  var body = '';
  body += block('上一轮用户要求', n.previous_feedback || n.user_requests);
  body += block('本轮已修改', n.changes_made);
  body += block('未改 / 保留原因', n.not_changed);
  body += block('仍需确认', n.remaining_risks);
  if (!body) return '';
  return '<div class="revision-notes"><div class="revision-notes-title">上一轮反馈与本轮修改</div><div class="revision-grid">'+body+'</div></div>';
}}

function pageHasBlockingIssues(pageKey) {{
  var v = (validation||{{}})[pageKey]||{{}};
  var issues = v.issues || [];
  var hasError = v.status === 'fail' || issues.some(function(i) {{ return i.severity === 'error'; }});
  var s = (selfReview||{{}})[pageKey]||{{}};
  var fixes = (s.required_fixes || []);
  return hasError || s.visual_status === 'blocked' || s.status === 'blocked' || fixes.length > 0;
}}

function statusLabel(v) {{
  return {{pass:'通过', warning:'警告', fail:'失败', unknown:'未知'}}[v] || v || '未知';
}}

function modeLabel(v) {{
  return {{rational:'理性页', emotional:'情绪页'}}[v] || v || '';
}}

function densityLabel(v) {{
  return {{dense:'高密度', balanced:'均衡', airy:'留白'}}[v] || v || '';
}}

function renderPages() {{
  var container = document.getElementById('container');
  var nav = document.getElementById('pageNav');

  if (!hasValidation) {{
    var alertDiv = document.createElement('div');
    alertDiv.className = 'global-alert error';
    alertDiv.textContent = '警告：validation_summary.json 缺失。所有页面校验结果未知，请先运行 validate_svg_layout.py。';
    container.appendChild(alertDiv);
  }}

  if (!hasSelfReview) {{
    var alertDiv2 = document.createElement('div');
    alertDiv2.className = 'global-alert warning';
    alertDiv2.textContent = '注意：self_review.json 缺失。模型视觉自检尚未完成，所有视觉检查已推迟到人工审阅。请仔细检查每页。';
    container.appendChild(alertDiv2);
  }} else if (!visionAvailable) {{
    var alertDiv3 = document.createElement('div');
    alertDiv3.className = 'global-alert warning';
    alertDiv3.textContent = '人工视觉审阅模式：模型视觉能力不可用，PNG 画面判断交由人工完成。原因：' + (visionUnavailableReason || '未提供');
    container.appendChild(alertDiv3);
  }}

  pages.forEach(function(p, idx) {{
    var pageKey = p.page_key || ('page_' + String(idx+1).padStart(2,'0'));
    var v = (validation||{{}})[pageKey]||{{}};
    var s = (selfReview||{{}})[pageKey]||{{}};
    var vers = (versions||{{}})[pageKey]||[];

    var vStatus = v.status||'unknown';
    var srStatus = s.visual_status||s.status||'not_reviewed';
    var hasDesignSuggestions = ((s||{{}}).suggestions||[]).length > 0;
    var hasRequiredFixes = ((s||{{}}).required_fixes||[]).length > 0;
    var borderClass = (vStatus === 'fail' || hasRequiredFixes || srStatus === 'blocked') ? 'fail' : (hasDesignSuggestions ? 'warning' : 'pass');

    var card = document.createElement('div');
    card.id = 'page-' + pageKey;
    card.className = 'page-review ' + borderClass;

    if (nav) {{
      var link = document.createElement('a');
      link.className = 'nav-item';
      link.href = '#page-' + pageKey;
      link.innerHTML = '<span class="nav-dot '+borderClass+'"></span><span>第'+(idx+1)+'页</span>';
      nav.appendChild(link);
    }}

    var html = '<div class="page-head"><h2>第'+(idx+1)+'页: '+escapeHtml(p.page_title||pageKey)+'</h2>';
    html += '<span class="page-meta">'+escapeHtml(pageKey);

    // Layout info from layout plan if available
    if (p.layout_id) html += ' | ' + escapeHtml(p.layout_id);
    if (p.page_mode) html += ' | ' + escapeHtml(modeLabel(p.page_mode));
    if (p.visual_density) html += ' | ' + escapeHtml(densityLabel(p.visual_density));
    html += '</span></div>';
    html += '<div class="page-body"><div class="review-grid">';

    // Preview first
    html += '<section class="preview-panel">';
    var pngPath = p.png_path;
    if (!pngPath) {{
      html += '<div class="missing-file">PNG 预览路径未在 page_manifest.json 中设置</div>';
    }} else {{
      if (vers.length >= 2) {{
        var latest = vers[vers.length-1];
        var prev = vers[vers.length-2];
        var versionBase = '_internal/05_review/versions/' + pageKey + '/';
        html += '<div class="section-label">版本对比</div><div class="grid-2col">';
        html += '<div class="preview-box"><div class="vlabel">v'+prev.version+' ('+prev.created_at+')</div><img src="'+assetUrl(versionBase+prev.png)+'" alt="v'+prev.version+'"></div>';
        html += '<div class="preview-box"><div class="vlabel">v'+latest.version+' ('+latest.created_at+') — 当前版本</div><img src="'+assetUrl(versionBase+latest.png)+'" alt="v'+latest.version+'"></div>';
        html += '</div>';
      }} else {{
        html += '<div class="section-label">预览</div><div class="preview-row"><div class="preview-box"><img src="'+assetUrl(pngPath)+'" alt="页面预览"></div></div>';
      }}
    }}
    html += '</section><section class="qa-panel">';

    // Internal check status. Non-blocking validator warnings are intentionally
    // not exposed as user-facing actions; the model should synthesize them into
    // design suggestions only when the PNG confirms a real issue.
    html += '<div class="section-label">内部检查</div>';
    if (vStatus === 'unknown') {{
      html += '<div class="missing-file">内部检查结果未知 — validation_summary.json 中未找到此页</div>';
    }} else {{
      html += '<div class="val-summary">';
      var visibleStatus = vStatus === 'fail' ? '发现阻断项' : '已完成';
      html += '<span class="status-'+(vStatus === 'fail' ? 'fail' : 'pass')+'">状态: '+escapeHtml(visibleStatus)+'</span>';
      var es = (v.summary||{{}}).errors||0;
      if (es) html += ' | 阻断: '+es;
      html += '</div>';
      var issues = v.issues || [];
      var errIssues = issues.filter(function(i) {{ return i.severity === 'error'; }});
      if (errIssues.length) {{
        html += '<div class="required-fixes"><div class="rf-title">必须修复项</div><ul>';
        errIssues.forEach(function(i) {{ html += '<li>'+escapeHtml(i.message)+'</li>'; }});
        html += '</ul></div>';
      }}
    }}

    // Self-review status
    html += '<div class="section-label">模型自检</div>';
    if (!visionAvailable) {{
      html += '<div class="self-review-status human_review">人工视觉审阅模式：请以左侧 PNG 预览为准，脚本检查仍然有效。原因：'+escapeHtml(visionUnavailableReason || '未提供')+'</div>';
    }} else if (srStatus === 'not_reviewed') {{
      html += '<div class="self-review-status" style="background:#F5F7FA;color:#999;border:1px solid #E0E0E0">自检状态: 未完成</div>';
    }} else {{
      html += '<details class="self-review-status '+srStatus+'"><summary>自检状态: ' + srStatus.toUpperCase();
      if (s.confidence != null) html += ' | 置信度: ' + (s.confidence*100).toFixed(0) + '%';
      html += '</summary><div class="self-review-body">';
      if (s.layout_feedback) html += '<div>版式: ' + escapeHtml(s.layout_feedback) + '</div>';
      if (s.copy_feedback) html += '<div>文案: ' + escapeHtml(s.copy_feedback) + '</div>';
      if (s.visual_feedback) html += '<div>视觉: ' + escapeHtml(s.visual_feedback) + '</div>';
      html += '</div></details>';
    }}

    // Required fixes (blocking — shown BEFORE feedback controls)
    var fixes = (s||{{}}).required_fixes||[];
    if (fixes.length) {{
      html += '<div class="required-fixes"><div class="rf-title">阻断性问题（必须在PPT转换前解决）</div>';
      html += '<div class="rf-subtitle">以下问题不解决，pipeline_gate.py 将阻止导出</div><ul>';
      fixes.forEach(function(f) {{ html += '<li>'+escapeHtml(f)+'</li>'; }});
      html += '</ul></div>';
    }}

    // User-facing design suggestions from model self-review only.
    var suggestions = (s||{{}}).suggestions||[];
    var reviewActions = buildReviewActions(suggestions);
    html += '<div class="section-label">设计建议（勾选表示下一轮请修改）</div>';
    html += renderReviewActions(pageKey, idx, reviewActions);

    // Free-text feedback
    html += '<div class="action-zone"><div class="section-label">您的反馈</div><div class="feedback-text">';
    html += '<textarea name="feedback_'+idx+'" placeholder="对此页的反馈意见..."></textarea></div>';

    // Approve
    html += '<label class="approve-row"><input type="checkbox" name="approve_'+idx+'" value="1"> <strong>确认此页通过审阅</strong></label>';
    html += '</div>';
    html += '</section></div></div>'; // qa-panel, review-grid, page-body
    html += renderRevisionNotes(pageKey);
    card.innerHTML = html;
    container.appendChild(card);
  }});
}}

function submitFeedback() {{
  var payload = {{batch_id: batchId, pages:{{}}, all_approved: false}};
  pages.forEach(function(p, idx) {{
    var pageKey = p.page_key || ('page_' + String(idx+1).padStart(2,'0'));
    var selectedActions = [];
    var selectedSuggestionIndexes = [];
    var actionCbs = document.getElementsByName('action_'+idx);
    actionCbs.forEach(function(cb) {{
      if (!cb.checked) return;
      var ai = parseInt(cb.value);
      var action = (pageActionCache[pageKey] || [])[ai];
      if (action) {{
        selectedActions.push(action);
        if (action.source === 'self_review' && action.source_index != null) {{
          selectedSuggestionIndexes.push(action.source_index);
        }}
      }}
    }});
    var approved = (document.getElementsByName('approve_'+idx)[0]||{{}}).checked||false;
    payload.pages[pageKey] = {{
      approved: approved,
      selected_suggestions: selectedSuggestionIndexes,
      selected_review_actions: selectedActions,
      custom_feedback: (document.getElementsByName('feedback_'+idx)[0]||{{}}).value||''
    }};
  }});
  payload.all_approved = Object.values(payload.pages).every(function(p) {{ return p.approved; }});
  payload.approval_key = (document.getElementById('approvalKey')||{{}}).value || '';
  var toast = document.getElementById('toast');
  for (var pk in payload.pages) {{
    if (!Object.prototype.hasOwnProperty.call(payload.pages, pk)) continue;
    var pagePayload = payload.pages[pk];
    if (pagePayload.approved && pageHasBlockingIssues(pk)) {{
      toast.textContent = pk + ' 仍有阻断项，不能批准。请先修复。';
      toast.className = 'toast show';
      setTimeout(function(){{ toast.className='toast'; }}, 5000);
      return;
    }}
    if (pagePayload.approved && pagePayload.selected_review_actions && pagePayload.selected_review_actions.length) {{
      toast.textContent = pk + ' 已勾选修改建议。请先提交反馈，或取消勾选后再批准。';
      toast.className = 'toast show';
      setTimeout(function(){{ toast.className='toast'; }}, 5000);
      return;
    }}
  }}
  if (payload.all_approved && !payload.approval_key.trim()) {{
    toast.textContent = '全部通过需要输入人工审批口令。';
    toast.className = 'toast show';
    setTimeout(function(){{ toast.className='toast'; }}, 5000);
    return;
  }}
  postPayload(payload);
}}

function approveAll() {{
  pages.forEach(function(p, idx) {{
    var cb = document.getElementsByName('approve_'+idx)[0];
    if(cb) cb.checked = true;
  }});
  submitFeedback();
}}

function postPayload(payload) {{
  var toast = document.getElementById('toast');
  fetch('/review-feedback', {{
    method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)
  }}).then(function(r) {{
    toast.textContent = r.ok ? '反馈已提交。' : '提交失败。审阅服务器是否在运行？';
    toast.className = 'toast show';
    setTimeout(function(){{ toast.className='toast'; }}, 4000);
  }}).catch(function() {{
    toast.textContent = '无法连接服务器。请先启动 review_server.py。';
    toast.className = 'toast show';
    setTimeout(function(){{ toast.className='toast'; }}, 5000);
  }});
}}

renderPages();

function updateHeaderCompactState() {{
  document.body.classList.toggle('review-scrolled', window.scrollY > 24);
}}
updateHeaderCompactState();
window.addEventListener('scroll', updateHeaderCompactState, {{passive:true}});

var observer = new IntersectionObserver(function(entries) {{
  entries.forEach(function(entry) {{
    if (!entry.isIntersecting) return;
    document.querySelectorAll('.nav-item').forEach(function(a) {{ a.classList.remove('active'); }});
    var active = document.querySelector('.nav-item[href="#'+entry.target.id+'"]');
    if (active) active.classList.add('active');
  }});
}}, {{rootMargin:'-35% 0px -55% 0px', threshold:0}});
document.querySelectorAll('.page-review').forEach(function(card) {{ observer.observe(card); }});
</script>
</body>
</html>"""


def load_json(path):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return None
    return None


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def to_url_path(path):
    if not path:
        return ""
    return "/" + str(path).lstrip("/")


def get_batch_pages(manifest, batch_id):
    batch_config = manifest.get("batch_config", {})
    if not isinstance(batch_config, dict):
        fail("page_manifest.json batch_config must be an object")
    if batch_id not in batch_config:
        fail(f"batch '{batch_id}' not found in page_manifest.json")

    batch = batch_config.get(batch_id)
    if not isinstance(batch, dict):
        fail(
            f"page_manifest.json batch_config.{batch_id} must be an object with "
            "'status' and 'pages'. List-style batches are not supported."
        )

    pages = batch.get("pages")
    if not isinstance(pages, list) or not pages:
        fail(f"page_manifest.json batch_config.{batch_id}.pages must be a non-empty list")
    return pages


def report_page_key(report, page_keys):
    filename = Path(report.get("file", "")).stem
    for pk in page_keys:
        if filename == pk or filename.startswith(pk):
            return pk
    return ""


def report_has_error(report):
    if report.get("status") == "fail":
        return True
    summary = report.get("summary", {})
    if isinstance(summary, dict) and summary.get("errors", 0):
        return True
    for issue in report.get("issues", []):
        if isinstance(issue, dict) and issue.get("severity") == "error":
            return True
    return False


BLOCKING_WARNING_CODES = {
    "TEXT_OVERFLOW_MAJOR",
    "FOOTER_ZONE_INVASION",
}


def report_has_blocking_warning(report):
    for issue in report.get("issues", []):
        if not isinstance(issue, dict):
            continue
        if issue.get("severity") == "warning" and issue.get("code") in BLOCKING_WARNING_CODES:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate 02_visual_review.html from page_manifest, validation, and self-review data."
    )
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--batch", default="batch_01", help="Batch ID to render, e.g. batch_01")
    parser.add_argument("--output", default="", help="Output HTML path (default: project root)")
    parser.add_argument("--allow-missing-validation", action="store_true",
                        help="Generate HTML even if validation_summary.json is missing (for debugging)")
    parser.add_argument("--debug-show-failures", action="store_true",
                        help="Generate HTML even when validation reports contain FAIL pages. Internal debugging only.")
    args = parser.parse_args()

    root = Path(args.project_dir)
    internal = root / "_internal"

    # Load manifest (the single source of truth for page ordering)
    manifest_data = load_json(internal / "00_project" / "page_manifest.json")
    if not manifest_data:
        fail("page_manifest.json not found or invalid")
    validation_data = load_json(internal / "04_validation" / "validation_summary.json")
    self_review_data = load_json(internal / "04_validation" / "self_review.json") or {}
    revision_notes_data = load_json(internal / "05_review" / "revision_notes.json") or {}

    has_validation = validation_data is not None
    has_self_review = bool(self_review_data)
    vision_available = self_review_data.get("vision_available", False) if has_self_review else False
    batch_page_keys = get_batch_pages(manifest_data, args.batch)

    # Validation is REQUIRED
    if not has_validation and not args.allow_missing_validation:
        print("ERROR: validation_summary.json not found at _internal/04_validation/validation_summary.json", file=sys.stderr)
        print("Run validate_svg_layout.py first, or use --allow-missing-validation for debugging.", file=sys.stderr)
        sys.exit(1)

    # Build page list from manifest
    manifest_pages = manifest_data.get("pages", [])
    if not manifest_pages:
        fail("page_manifest.json has no pages.")

    manifest_by_key = {
        p.get("page_key"): p
        for p in manifest_pages
        if isinstance(p, dict) and p.get("page_key")
    }
    unknown_batch_pages = [pk for pk in batch_page_keys if pk not in manifest_by_key]
    if unknown_batch_pages:
        fail(f"Batch {args.batch} references page(s) not present in manifest pages: {unknown_batch_pages}")

    layout_data = load_json(internal / "01_layout_plan" / "layout_plan.json") or {}
    layout_by_key = {
        p.get("page_key"): p
        for p in layout_data.get("pages", [])
        if isinstance(p, dict) and p.get("page_key")
    }
    content_data = load_json(internal / "01_content" / "page_content.json") or {}
    content_by_key = {
        p.get("page_key"): p
        for p in content_data.get("pages", [])
        if isinstance(p, dict) and p.get("page_key")
    }

    pages = []
    missing_pngs = []
    for pk in batch_page_keys:
        p = manifest_by_key[pk]
        layout = layout_by_key.get(pk, {})
        content = content_by_key.get(pk, {})

        entry = {
            "page_key": pk,
            "page_title": content.get("action_title") or layout.get("page_title") or pk,
            "svg_path": to_url_path(p.get("svg_path", "")),
            "png_path": to_url_path(p.get("png_path", "")),
            "layout_id": layout.get("layout_id", ""),
            "page_mode": layout.get("page_mode", ""),
            "visual_density": layout.get("visual_density", ""),
        }

        # Check PNG path
        png_path = p.get("png_path", "")
        if not png_path:
            missing_pngs.append(f"{pk}: png_path not set in manifest")
        elif not (root / png_path).exists():
            missing_pngs.append(f"{pk}: PNG not found at {png_path}")

        pages.append(entry)

    if missing_pngs and not args.allow_missing_validation:
        print("ERROR: Missing PNG files:\n  " + "\n  ".join(missing_pngs), file=sys.stderr)
        print("Run render_svg_png.py first.", file=sys.stderr)
        sys.exit(1)

    # Build validation lookup by page_key from reports
    val_lookup = {}
    missing_validation_pages = []
    if has_validation:
        reports = validation_data.get("reports", [])
        for r in reports:
            pk = report_page_key(r, batch_page_keys)
            if pk:
                val_lookup[pk] = r
        missing_validation_pages = [pk for pk in batch_page_keys if pk not in val_lookup]

    if missing_validation_pages and not args.allow_missing_validation:
        fail("Missing validation report for page(s): " + ", ".join(missing_validation_pages))

    failed_validation_pages = [
        f"{pk}: {val_lookup[pk].get('summary', {}).get('errors', '?')} error(s)"
        for pk in batch_page_keys
        if pk in val_lookup and report_has_error(val_lookup[pk])
    ]
    if failed_validation_pages and not args.debug_show_failures:
        fail(
            "Validation failed for batch pages; fix SVG and rerun static validation "
            "before generating user review HTML. Failed page(s): "
            + "; ".join(failed_validation_pages)
            + ". Use --debug-show-failures only for internal QA."
        )

    blocking_warning_pages = [
        pk for pk in batch_page_keys
        if pk in val_lookup and report_has_blocking_warning(val_lookup[pk])
    ]
    if blocking_warning_pages and not args.debug_show_failures:
        fail(
            "Validation has blocking warning(s); fix SVG and rerun static validation "
            "before generating user review HTML. Blocked page(s): "
            + ", ".join(blocking_warning_pages)
            + ". Use --debug-show-failures only for internal QA."
        )

    # Build self-review lookup
    sr_lookup = self_review_data.get("pages", {}) if has_self_review else {}
    missing_self_review = [pk for pk in batch_page_keys if pk not in sr_lookup]
    if vision_available and missing_self_review and not args.allow_missing_validation:
        fail("Missing self_review entry for page(s): " + ", ".join(missing_self_review))

    # Build versions index
    versions_dir = internal / "05_review" / "versions"
    versions_index = {}
    if versions_dir.exists():
        for page_dir in sorted(versions_dir.iterdir()):
            if page_dir.is_dir():
                history_path = page_dir / "history.json"
                if history_path.exists():
                    try:
                        versions_index[page_dir.name] = json.loads(history_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass

    # Compute user-facing counts. Validator warnings are internal; the header
    # shows page count, design-suggestion count, and hard blockers only.
    count_pass = len(batch_page_keys)
    count_warn = sum(
        len((sr_lookup.get(pk, {}) or {}).get("suggestions", []) or [])
        for pk in batch_page_keys
    )
    count_fail = sum(1 for v in val_lookup.values() if v.get("status") == "fail")
    count_fail += sum(
        1
        for pk in batch_page_keys
        if (sr_lookup.get(pk, {}) or {}).get("visual_status") == "blocked"
        or (sr_lookup.get(pk, {}) or {}).get("required_fixes")
    )

    # Global alerts
    global_alerts = ""
    if not has_validation:
        global_alerts = '<div class="global-alert error">validation_summary.json 缺失 — 所有页面校验结果未知。请先运行 validate_svg_layout.py。</div>'
    if not has_self_review:
        global_alerts += '<div class="global-alert warning">self_review.json 缺失 — 模型视觉自检尚未完成。请仔细检查每页。</div>'
    elif not vision_available:
        reason = str(self_review_data.get("vision_unavailable_reason", "") or "未提供")
        global_alerts += '<div class="global-alert warning">人工视觉审阅模式：模型视觉能力不可用，PNG 画面判断交由人工完成。原因：' + reason.replace("&", "&amp;").replace("<", "&lt;") + '</div>'

    project = manifest_data.get("project", root.name) if manifest_data else root.name
    html = HTML_TEMPLATE.format(
        project=str(project).replace("&", "&amp;").replace("<", "&lt;"),
        batch_label=str(args.batch).replace("&", "&amp;").replace("<", "&lt;"),
        batch_id=str(args.batch),
        count_pass=count_pass,
        count_warn=count_warn,
        count_fail=count_fail,
        pages_json=json.dumps(pages, ensure_ascii=False),
        validation_json=json.dumps(val_lookup, ensure_ascii=False),
        self_review_json=json.dumps(sr_lookup, ensure_ascii=False),
        versions_json=json.dumps(versions_index, ensure_ascii=False),
        revision_notes_json=json.dumps(revision_notes_data, ensure_ascii=False),
        has_self_review="true" if has_self_review else "false",
        vision_available="true" if vision_available else "false",
        vision_unavailable_reason_json=json.dumps(self_review_data.get("vision_unavailable_reason", ""), ensure_ascii=False),
        has_validation="true" if has_validation else "false",
        global_alerts=global_alerts,
    )

    output_path = Path(args.output) if args.output else root / "02_visual_review.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Generated {output_path} ({len(pages)} pages)")

    # Report issues found
    if not has_validation:
        print("WARNING: Generated without validation data.", file=sys.stderr)
    if missing_pngs:
        print(f"WARNING: {len(missing_pngs)} missing PNG(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
