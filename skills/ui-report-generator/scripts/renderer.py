"""renderer.py — 单文件 HTML 报告渲染

风格对齐 api-report-generator：
    - 主色 tech-blue #1a73e8，success/fail/skip 标准色
    - Chart.js 4.4 via CDN，离线降级到数据表
    - 4-card 总览 + 3-chart 行 + 模块表 + 用例明细 + 失败详情 + 风险/建议 + 页脚

UI 增强：
    - 浏览器矩阵（chromium/firefox/webkit 通过率）
    - 失败用例 inline 截图/视频/Trace 打开按钮
    - 诊断根因聚合（基于 ui_repair_report.md）
"""
from __future__ import annotations

import base64
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from parsers import ReportDocument


# ============ 主入口 ============


def render_html(
    doc: ReportDocument,
    *,
    title: str = "UI 自动化测试报告",
    artifact_base: Path | None = None,
    trace_launch_cmd_template: str | None = None,
    allure_url: str | None = None,
    report_output_path: Path | None = None,
) -> str:
    """渲染单文件 HTML 报告。

    Args:
        doc: ReportDocument 数据
        title: 报告标题
        artifact_base: 截图/视频相对路径基准目录（生成 <img src=...> 相对路径）
        trace_launch_cmd_template: Trace 打开按钮的命令模板（含 {trace_path} 占位）
        allure_url: Allure 报告 URL；None 则按钮渲染为灰色 disabled
        report_output_path: 报告 HTML 输出路径；指定时 artifact 路径相对该路径计算，
            避免浏览器从子目录打开时路径多一层
    """
    payload = _build_payload(doc, artifact_base, trace_launch_cmd_template, report_output_path)
    allure_btn = _render_allure_btn(allure_url)
    return _TEMPLATE.format(
        title=html.escape(title),
        payload_json=payload,
        generated_at=html.escape(doc.generated_at),
        allure_btn=allure_btn,
    )


def _render_allure_btn(allure_url: str | None) -> str:
    """Allure 入口按钮 HTML：有 URL 渲染为蓝色可点击链接，无则灰色 disabled。"""
    if allure_url:
        return (
            f'<a class="allure-btn" href="{html.escape(allure_url)}" '
            f'target="_blank" rel="noopener noreferrer">打开 Allure 报告</a>'
        )
    return (
        '<span class="allure-btn disabled" '
        'title="未配置 Allure 报告（--allure-url 或自动探测 localhost:8088 失败）">'
        "Allure 未就绪</span>"
    )


# ============ payload 构造 ============


def _build_payload(
    doc: ReportDocument,
    artifact_base: Path | None,
    trace_cmd_template: str | None,
    report_output_path: Path | None = None,
) -> str:
    """构造嵌入 HTML 的 JSON payload。"""
    data = {
        "generated_at": doc.generated_at,
        "suite": _suite_dict(doc),
        "by_module": doc.by_module,
        "by_priority": doc.by_priority,
        "by_browser": doc.by_browser,
        "by_category": doc.by_category,
        "by_root_cause": doc.by_root_cause,
        "diagnose_overview": doc.diagnose_overview,
        "risk_modules": [
            r for r in (
                _risk_modules(doc)
            ) if r
        ],
        "suggestions": _suggestions(doc),
        "failures": [_failure_dict(f, doc, artifact_base, trace_cmd_template, report_output_path) for f in doc.failures],
        "tests": [_test_dict(t) for t in doc.tests],
        "diagnose_records": [_diagnose_dict(r) for r in doc.diagnose_records],
        "history": doc.history,
        "browser_env": doc.browser_env,
        "meta": doc.meta,
    }
    return json.dumps(data, ensure_ascii=False, default=str)


def _suite_dict(doc: ReportDocument) -> dict:
    s = doc.suite
    return {
        "total": s.total,
        "passed": s.passed,
        "failed": s.failed + s.errors,
        "errors": s.errors,
        "skipped": s.skipped,
        "pass_rate": s.pass_rate,
        "total_duration": round(s.total_duration, 2),
        "slowest_test": s.slowest_test,
        "slowest_duration": round(s.slowest_duration, 2),
    }


def _risk_modules(doc: ReportDocument) -> list[dict]:
    """重做一遍，因为 analyzer.analyze_risk 接的是 by_module。"""
    from analyzer import analyze_risk
    return analyze_risk(doc.by_module)


def _suggestions(doc: ReportDocument) -> list[dict]:
    from analyzer import generate_suggestions
    return generate_suggestions(
        doc.by_module, doc.by_category, doc.by_root_cause, doc.diagnose_records
    )


def _test_dict(t) -> dict:
    return {
        "nodeid": t.nodeid,
        "file": t.file,
        "classname": t.classname,
        "name": t.testname,
        "status": t.status,
        "duration": round(t.duration, 2),
        "browser": t.browser,
        "markers": t.markers,
        "failure_stage": t.failure_stage,
        "message": t.message,
    }


def _failure_dict(f, doc, artifact_base, trace_cmd_template, report_output_path=None) -> dict:
    """失败用例完整详情，含 artifacts + 诊断记录。

    Artifact 字段说明（差异化展示）：
        - screenshots: base64 内联数组（最多 5 张），前端 grid + lightbox 渲染
        - video_url: 失败录屏相对路径（前端 <video> 内联播放，无则 None）
        - trace_launch_cmd: trace.zip 打开命令字符串（按钮触发，无则 None）
        - page_source_url / console_logs_url: 失败现场 HTML / 5 段日志（外链）
    通过用例无需此函数（_test_dict 已不含 artifact 字段）。
    """
    diag = next((r for r in doc.diagnose_records if r.nodeid == f.nodeid), None)
    artifacts = _attach_artifact_urls(f.artifacts, artifact_base, report_output_path)

    # 截图转 base64 内联（最多 5 张；HTML 移动后仍可见）
    screenshots_b64 = []
    for p in f.artifacts.get("screenshots", [])[:5]:
        path = Path(p)
        if path.exists():
            try:
                data = path.read_bytes()
                screenshots_b64.append(
                    "data:image/png;base64," + base64.b64encode(data).decode("ascii")
                )
            except Exception:
                pass

    # 录屏相对 URL（前端用 <video> 内联播放）
    video_url = artifacts.get("videos", [None])[0] if artifacts.get("videos") else None
    page_source_url = artifacts.get("page_source", [None])[0] if artifacts.get("page_source") else None
    console_logs_url = artifacts.get("console_logs", [None])[0] if artifacts.get("console_logs") else None
    trace_url = artifacts.get("traces", [None])[0] if artifacts.get("traces") else None

    return {
        "nodeid": f.nodeid,
        "file": f.file,
        "line": f.line,
        "status": f.status,
        "duration": round(f.duration, 2),
        "browser": f.browser,
        "failure_stage": f.failure_stage,
        "message": f.message,
        "traceback": (f.traceback or "")[:4000],
        "diagnose": _diagnose_dict(diag) if diag else None,
        "screenshots": screenshots_b64,
        "video_url": video_url,
        "page_source_url": page_source_url,
        "console_logs_url": console_logs_url,
        "trace_url": trace_url,
        "trace_launch_cmd": (
            trace_cmd_template.format(trace_path=f.artifacts["traces"][0])
            if trace_cmd_template and f.artifacts.get("traces")
            else None
        ),
    }


def _attach_artifact_urls(arts: dict[str, list[str]], base: Path | None, report_output_path: Path | None = None) -> dict[str, list[str]]:
    """把绝对路径转成 HTML 友好的相对路径。

    优先级：
        1. report_output_path 给定时：相对 HTML 文件所在目录（避免浏览器从子目录打开时路径多一层）
        2. base 给定时：相对 base 目录（旧逻辑）
        3. 否则原样返回
    """
    if not arts:
        return arts
    if not base and not report_output_path:
        return arts

    out: dict[str, list[str]] = {}
    if report_output_path:
        rel_base = Path(report_output_path).resolve().parent
    else:
        rel_base = Path(base).resolve()

    for k, paths in arts.items():
        rels = []
        for p in paths:
            try:
                abs_p = Path(p).resolve()
                rel = abs_p.relative_to(rel_base)
                # POSIX 风格（浏览器 URL 用 / 不用 \）
                rels.append(rel.as_posix())
            except Exception:
                rels.append(p)
        out[k] = rels
    return out


def _diagnose_dict(r) -> dict | None:
    if r is None:
        return None
    return {
        "category": r.category,
        "confidence": r.confidence,
        "signals": r.signals,
        "root_cause": r.upgraded_root_cause or r.root_cause,
        "fix_strategy": r.fix_strategy,
        "fix_applied": r.fix_applied,
        "fix_target_file": r.fix_target_file,
        "verify_status": r.verify_status,
        "verify_duration": r.verify_duration,
        "rolled_back": r.rolled_back,
        "upgraded_root_cause": r.upgraded_root_cause,
        "upgrade_reason": r.upgrade_reason,
        "raw_error": r.raw_error,
    }


# ============ HTML 模板（对齐 api-report-generator 风格） ============


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{
  --primary: #1a73e8;
  --success: #34a853;
  --fail: #ea4335;
  --skip: #9aa0a6;
  --warn: #fbbc04;
  --bg: #f8f9fa;
  --card: #ffffff;
  --text: #202124;
  --text-muted: #5f6368;
  --border: #e0e0e0;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6;
}}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
header.report-header {{
  background: linear-gradient(135deg, var(--primary), #174ea6);
  color: #fff; padding: 32px 24px; border-radius: 12px; margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}}
header.report-header h1 {{ font-size: 24px; font-weight: 600; margin-bottom: 8px; }}
header.report-header .meta {{ font-size: 13px; opacity: 0.9; }}
header.report-header .meta span {{ margin-right: 24px; }}
header.report-header .header-row {{
  display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
}}
header.report-header .allure-btn {{
  display: inline-block; padding: 10px 22px; background: #fff; color: var(--primary);
  text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: 600;
  box-shadow: 0 2px 6px rgba(0,0,0,0.2); transition: all 0.2s; white-space: nowrap;
  align-self: flex-start;
}}
header.report-header .allure-btn:hover {{ background: #f1f3f4; transform: translateY(-1px); }}
header.report-header .allure-btn.disabled {{
  background: rgba(255,255,255,0.25); color: rgba(255,255,255,0.7);
  cursor: not-allowed; box-shadow: none; font-weight: 500;
}}
header.report-header .allure-btn.disabled:hover {{ transform: none; background: rgba(255,255,255,0.25); }}
section {{ background: var(--card); border-radius: 12px; padding: 24px; margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
section h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; color: var(--text);
  border-left: 4px solid var(--primary); padding-left: 12px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px;
  display: flex; flex-direction: column; }}
.card .label {{ font-size: 13px; color: var(--text-muted); margin-bottom: 8px; }}
.card .value {{ font-size: 28px; font-weight: 600; }}
.card.success .value {{ color: var(--success); }}
.card.fail .value {{ color: var(--fail); }}
.card.warn .value {{ color: var(--warn); }}
.card.primary .value {{ color: var(--primary); }}
.charts-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }}
.chart-box {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }}
.chart-box h3 {{ font-size: 14px; font-weight: 600; margin-bottom: 12px; color: var(--text-muted); }}
.chart-canvas-wrap {{ position: relative; height: 220px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
table th, table td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
table th {{ background: #f1f3f4; font-weight: 600; color: var(--text-muted); font-size: 13px; }}
table tr:hover {{ background: #f8f9fa; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 500; }}
.badge.passed {{ background: #e6f4ea; color: var(--success); }}
.badge.failed {{ background: #fce8e6; color: var(--fail); }}
.badge.skipped {{ background: #f1f3f4; color: var(--skip); }}
.badge.error {{ background: #fef7e0; color: #b06000; }}
.badge.high {{ background: #fce8e6; color: var(--fail); }}
.badge.mid {{ background: #fef7e0; color: #b06000; }}
.badge.low {{ background: #e6f4ea; color: var(--success); }}
.badge.upgraded {{ background: #fef7e0; color: #b06000; }}
.controls {{ display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }}
.controls input, .controls select {{
  padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px;
}}
.controls input {{ flex: 1; min-width: 200px; }}
.failure-detail {{
  border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px;
  background: #fafbfc;
}}
.failure-detail h3 {{ font-size: 15px; margin-bottom: 12px; word-break: break-all; }}
.failure-detail .field {{ margin-bottom: 6px; font-size: 13px; }}
.failure-detail .field strong {{ color: var(--text-muted); display: inline-block; min-width: 80px; }}
.failure-detail pre {{
  background: #f1f3f4; padding: 12px; border-radius: 6px; font-size: 12px;
  overflow-x: auto; margin-top: 8px; max-height: 200px;
}}
.failure-detail img {{
  max-width: 100%; border: 1px solid var(--border); border-radius: 6px; margin-top: 8px;
}}
.failure-detail video {{ max-width: 100%; margin-top: 8px; }}
.failure-detail .actions {{ margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
/* === 失败用例截图 grid + 点击放大 === */
.screenshot-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px; margin-top: 8px;
}}
.screenshot-thumb {{
  position: relative; cursor: pointer; border: 1px solid var(--border);
  border-radius: 6px; overflow: hidden; aspect-ratio: 16 / 10; background: #f1f3f4;
  transition: transform 0.15s, box-shadow 0.15s;
}}
.screenshot-thumb:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
.screenshot-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.screenshot-thumb .zoom-hint {{
  position: absolute; bottom: 6px; right: 6px; background: rgba(0,0,0,0.6);
  color: #fff; font-size: 11px; padding: 2px 6px; border-radius: 3px;
  opacity: 0; transition: opacity 0.15s;
}}
.screenshot-thumb:hover .zoom-hint {{ opacity: 1; }}
/* === 内联视频播放器 === */
.video-player {{
  margin-top: 8px; background: #000; border-radius: 6px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
}}
.video-player video {{ width: 100%; max-height: 480px; display: block; }}
/* === Lightbox：截图放大查看 === */
.lightbox {{
  display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.92);
  z-index: 9999; align-items: center; justify-content: center; padding: 32px;
  cursor: zoom-out;
}}
.lightbox.open {{ display: flex; }}
.lightbox img {{
  max-width: 95vw; max-height: 92vh; object-fit: contain;
  border-radius: 4px; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  cursor: default;
}}
.lightbox-close {{
  position: fixed; top: 20px; right: 28px; color: #fff; font-size: 28px;
  cursor: pointer; line-height: 1; opacity: 0.8;
}}
.lightbox-close:hover {{ opacity: 1; }}
.btn {{
  display: inline-block; padding: 6px 14px; background: var(--primary); color: #fff;
  text-decoration: none; border-radius: 6px; font-size: 13px; cursor: pointer; border: none;
}}
.btn.secondary {{ background: var(--text-muted); }}
.btn.trace {{ background: var(--warn); color: #202124; }}
.pager {{ display: flex; justify-content: space-between; align-items: center; margin-top: 16px; font-size: 14px; }}
.empty {{ padding: 32px; text-align: center; color: var(--text-muted); }}
ul.suggestions {{ list-style: none; }}
ul.suggestions li {{
  padding: 12px; border-left: 4px solid var(--warn); background: #fefcf3;
  margin-bottom: 8px; border-radius: 4px; font-size: 14px;
}}
ul.suggestions li.P0 {{ border-color: var(--fail); background: #fef0ef; }}
ul.suggestions li strong {{ display: block; margin-bottom: 4px; }}
.trace-cmd {{ background: #f1f3f4; padding: 8px; font-family: monospace; font-size: 12px;
  border-radius: 4px; word-break: break-all; }}
footer {{ text-align: center; color: var(--text-muted); font-size: 12px; padding: 24px 0; }}
</style>
</head>
<body>
<div class="container">
  <header class="report-header">
    <div class="header-row">
      <div>
        <h1>{title}</h1>
        <div class="meta">
          <span>生成时间：{generated_at}</span>
          <span id="meta-env"></span>
          <span id="meta-duration"></span>
        </div>
      </div>
      {allure_btn}
    </div>
  </header>

  <section>
    <h2>总览大盘</h2>
    <div class="cards" id="overview-cards"></div>
  </section>

  <section>
    <h2>数据图表</h2>
    <div class="charts-row">
      <div class="chart-box"><h3>状态分布</h3><div class="chart-canvas-wrap"><canvas id="chart-status"></canvas></div></div>
      <div class="chart-box"><h3>模块通过率</h3><div class="chart-canvas-wrap"><canvas id="chart-module"></canvas></div></div>
      <div class="chart-box"><h3>历史通过率趋势</h3><div class="chart-canvas-wrap"><canvas id="chart-trend"></canvas></div></div>
    </div>
    <div id="chart-fallback" style="display:none; margin-top: 16px;"></div>
  </section>

  <section>
    <h2>浏览器矩阵</h2>
    <div id="browser-matrix"></div>
  </section>

  <section>
    <h2>模块统计</h2>
    <div id="module-table"></div>
  </section>

  <section>
    <h2>诊断根因聚合</h2>
    <div id="diagnose-summary"></div>
  </section>

  <section>
    <h2>风险与建议</h2>
    <div id="risk-section"></div>
  </section>

  <section>
    <h2>失败详情 <span id="failure-count" style="color:var(--text-muted); font-weight:400; font-size:14px;"></span></h2>
    <div id="failure-list"></div>
  </section>

  <section>
    <h2>用例明细</h2>
    <div class="controls">
      <input id="filter-input" placeholder="按用例名/文件/标签筛选..." />
      <select id="filter-status"><option value="">所有状态</option><option value="passed">通过</option><option value="failed">失败</option><option value="error">错误</option><option value="skipped">跳过</option></select>
      <select id="filter-browser"><option value="">所有浏览器</option></select>
    </div>
    <div id="test-table"></div>
    <div class="pager">
      <span id="pager-info"></span>
      <div>
        <button class="btn secondary" id="pager-prev">上一页</button>
        <button class="btn secondary" id="pager-next">下一页</button>
      </div>
    </div>
  </section>

  <footer>
    Generated by <strong>ui-report-generator</strong> skill · {generated_at}
  </footer>
</div>

<!-- Lightbox：截图放大查看 -->
<div id="lightbox" class="lightbox" onclick="closeLightbox()">
  <span class="lightbox-close" title="关闭 (Esc)">✕</span>
  <img id="lightbox-img" src="" alt="enlarged screenshot" onclick="event.stopPropagation()" />
</div>

<script>
const PAYLOAD = {payload_json};

// === 总览卡片 ===
function renderOverview() {{
  const s = PAYLOAD.suite;
  const cards = [
    {{label: "总用例", value: s.total, cls: "primary"}},
    {{label: "通过", value: s.passed, cls: "success"}},
    {{label: "失败", value: s.failed, cls: s.failed > 0 ? "fail" : "success"}},
    {{label: "跳过", value: s.skipped, cls: "warn"}},
    {{label: "通过率", value: s.pass_rate + "%", cls: s.pass_rate >= 90 ? "success" : (s.pass_rate >= 70 ? "warn" : "fail")}},
    {{label: "总耗时(s)", value: s.total_duration, cls: "primary"}},
  ];
  document.getElementById("overview-cards").innerHTML = cards.map(c =>
    `<div class="card ${{c.cls}}"><div class="label">${{c.label}}</div><div class="value">${{c.value}}</div></div>`
  ).join("");
  document.getElementById("meta-duration").textContent = "总耗时：" + s.total_duration + "s";
  if (PAYLOAD.browser_env && PAYLOAD.browser_env.browsers) {{
    const env = PAYLOAD.browser_env.browsers.filter(b => b.available).map(b => b.name).join(" / ");
    document.getElementById("meta-env").textContent = "浏览器：" + env;
  }}
}}

// === 图表 ===
let charts = {{}};
function renderCharts() {{
  if (typeof Chart === "undefined") {{
    document.getElementById("chart-fallback").style.display = "block";
    document.getElementById("chart-fallback").innerHTML =
      "<p style='color:#5f6368;'>⚠️ 无法加载 Chart.js（离线环境），改用表格展示：</p>" +
      renderStatusTable() + renderModuleTable();
    return;
  }}
  const s = PAYLOAD.suite;
  charts.status = new Chart(document.getElementById("chart-status"), {{
    type: "doughnut",
    data: {{
      labels: ["通过", "失败", "跳过"],
      datasets: [{{ data: [s.passed, s.failed, s.skipped], backgroundColor: ["#34a853", "#ea4335", "#9aa0a6"] }}]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: "bottom" }} }} }}
  }});
  const mods = Object.entries(PAYLOAD.by_module);
  charts.module = new Chart(document.getElementById("chart-module"), {{
    type: "bar",
    data: {{
      labels: mods.map(m => m[0]),
      datasets: [{{ label: "通过率%", data: mods.map(m => m[1].pass_rate), backgroundColor: "#1a73e8" }}]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }},
      scales: {{ y: {{ beginAtZero: true, max: 100 }} }} }}
  }});
  const hist = PAYLOAD.history || [];
  charts.trend = new Chart(document.getElementById("chart-trend"), {{
    type: "line",
    data: {{
      labels: hist.length ? hist.map(h => h.timestamp || h.generated_at || "") : ["本次"],
      datasets: [{{ label: "通过率%", data: hist.length ? hist.map(h => h.pass_rate) : [s.pass_rate],
        borderColor: "#1a73e8", backgroundColor: "rgba(26,115,232,0.1)", fill: true }}]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }},
      scales: {{ y: {{ beginAtZero: true, max: 100 }} }} }}
  }});
}}
function renderStatusTable() {{
  const s = PAYLOAD.suite;
  return `<table><tr><th>状态</th><th>数量</th></tr>
    <tr><td>通过</td><td>${{s.passed}}</td></tr>
    <tr><td>失败</td><td>${{s.failed}}</td></tr>
    <tr><td>跳过</td><td>${{s.skipped}}</td></tr></table>`;
}}

// === 浏览器矩阵 ===
function renderBrowserMatrix() {{
  const b = PAYLOAD.by_browser;
  const keys = Object.keys(b);
  if (!keys.length) {{
    document.getElementById("browser-matrix").innerHTML = "<div class='empty'>暂无浏览器数据</div>";
    return;
  }}
  let html = "<table><tr><th>浏览器</th><th>总数</th><th>通过</th><th>失败</th><th>通过率</th></tr>";
  keys.forEach(k => {{
    const d = b[k];
    const cls = d.pass_rate >= 90 ? "low" : (d.pass_rate >= 70 ? "mid" : "high");
    html += `<tr><td><strong>${{k}}</strong></td><td>${{d.total}}</td><td>${{d.passed}}</td><td>${{d.failed}}</td>
      <td><span class="badge ${{cls}}">${{d.pass_rate}}%</span></td></tr>`;
  }});
  html += "</table>";
  document.getElementById("browser-matrix").innerHTML = html;
}}

// === 模块表 ===
function renderModuleTable() {{
  const m = PAYLOAD.by_module;
  const keys = Object.keys(m).sort((a, b) => m[b].failed - m[a].failed || m[a].pass_rate - m[b].pass_rate);
  if (!keys.length) {{ document.getElementById("module-table").innerHTML = "<div class='empty'>暂无模块数据</div>"; return; }}
  let html = "<table><tr><th>模块</th><th>总数</th><th>通过</th><th>失败</th><th>跳过</th><th>通过率</th><th>平均耗时(s)</th><th>风险</th></tr>";
  keys.forEach(k => {{
    const d = m[k];
    html += `<tr><td><strong>${{k}}</strong></td><td>${{d.total}}</td><td>${{d.passed}}</td><td>${{d.failed}}</td><td>${{d.skipped}}</td>
      <td>${{d.pass_rate}}%</td><td>${{d.avg_duration}}</td>
      <td><span class="badge ${{d.risk}}">${{d.risk === "high" ? "高" : (d.risk === "mid" ? "中" : "低")}}</span></td></tr>`;
  }});
  html += "</table>";
  document.getElementById("module-table").innerHTML = html;
}}

// === 诊断聚合 ===
function renderDiagnose() {{
  const cat = PAYLOAD.by_category || {{}};
  const rc = PAYLOAD.by_root_cause || {{}};
  const overview = PAYLOAD.diagnose_overview || {{}};
  if (!Object.keys(cat).length && !Object.keys(overview).length) {{
    document.getElementById("diagnose-summary").innerHTML = "<div class='empty'>未检测到诊断报告（ui_repair_report.md）</div>";
    return;
  }}
  let html = "<table><tr><th>分类</th><th>数量</th></tr>";
  Object.entries(cat).forEach(([k, v]) => {{
    html += `<tr><td>${{k}}</td><td>${{v}}</td></tr>`;
  }});
  html += "</table><h3 style='margin-top:16px; font-size:14px; color:#5f6368;'>根因分布</h3><table><tr><th>根因</th><th>数量</th></tr>";
  Object.entries(rc).forEach(([k, v]) => {{
    html += `<tr><td>${{k}}</td><td>${{v}}</td></tr>`;
  }});
  html += "</table>";
  document.getElementById("diagnose-summary").innerHTML = html;
}}

// === 风险与建议 ===
function renderRisk() {{
  const risks = PAYLOAD.risk_modules || [];
  const suggestions = PAYLOAD.suggestions || [];
  let html = "";
  if (risks.length) {{
    html += "<h3 style='font-size:14px; color:#5f6368; margin-bottom:8px;'>高风险模块</h3><table><tr><th>模块</th><th>通过率</th><th>失败数</th><th>等级</th><th>原因</th></tr>";
    risks.forEach(r => {{
      html += `<tr><td><strong>${{r.module}}</strong></td><td>${{r.pass_rate}}%</td><td>${{r.failed}}</td>
        <td><span class="badge ${{r.level === '高' ? 'high' : 'mid'}}">${{r.level}}</span></td><td>${{r.reason}}</td></tr>`;
    }});
    html += "</table>";
  }}
  if (suggestions.length) {{
    html += "<h3 style='font-size:14px; color:#5f6368; margin: 16px 0 8px;'>优化建议</h3><ul class='suggestions'>";
    suggestions.forEach(s => {{
      html += `<li class="${{s.priority}}"><strong>[${{s.priority}}] ${{s.category}}：${{s.suggestion}}</strong> — ${{s.action}}</li>`;
    }});
    html += "</ul>";
  }}
  if (!html) html = "<div class='empty'>暂无风险与建议</div>";
  document.getElementById("risk-section").innerHTML = html;
}}

// === 失败详情 ===
function renderFailures() {{
  const fs = PAYLOAD.failures || [];
  document.getElementById("failure-count").textContent = `（${{fs.length}} 条）`;
  if (!fs.length) {{
    document.getElementById("failure-list").innerHTML = "<div class='empty'>✅ 无失败用例</div>";
    return;
  }}
  let html = "";
  fs.forEach((f, idx) => {{
    const diag = f.diagnose;
    let body = `<div class="field"><strong>失败阶段：</strong>${{f.failure_stage || "call"}}</div>`;
    body += `<div class="field"><strong>耗时：</strong>${{f.duration}}s</div>`;
    if (f.browser) body += `<div class="field"><strong>浏览器：</strong>${{f.browser}}</div>`;
    if (diag) {{
      body += `<div class="field"><strong>分类：</strong>${{diag.category || "—"}}</div>`;
      body += `<div class="field"><strong>根因：</strong>${{diag.root_cause || "—"}}`;
      if (diag.upgraded_root_cause) body += ` <span class="badge upgraded">已升级</span>`;
      body += `</div>`;
      if (diag.fix_strategy) body += `<div class="field"><strong>修复策略：</strong>${{diag.fix_strategy}}</div>`;
      if (diag.fix_applied) body += `<div class="field"><strong>修复状态：</strong>已应用 ${{diag.rolled_back ? "(已回滚)" : ""}}`;
      if (diag.verify_status) body += ` · 验证 ${{diag.verify_status}} (${{diag.verify_duration}}s)</div>`;
      if (diag.upgrade_reason) body += `<div class="field"><strong>升级原因：</strong>${{diag.upgrade_reason}}</div>`;
    }}
    body += `<div class="field"><strong>错误：</strong></div><pre>${{escapeHtml(f.message || "")}}</pre>`;
    if (f.traceback) body += `<details><summary style="cursor:pointer; color:#5f6368; font-size:13px; margin-top:8px;">查看 Traceback</summary><pre>${{escapeHtml(f.traceback)}}</pre></details>`;

    // === 截图 grid + 点击放大 ===
    const shots = f.screenshots || [];
    if (shots.length) {{
      body += `<div class="field" style="margin-top:12px;"><strong>失败截图（${{shots.length}}）<span style="color:#5f6368; font-weight:400;">· 点击放大</span></strong></div>`;
      body += `<div class="screenshot-grid">`;
      shots.forEach((src, i) => {{
        body += `<div class="screenshot-thumb" onclick="openLightbox('${{src}}')"><img src="${{src}}" alt="screenshot ${{i+1}}" loading="lazy" /><div class="zoom-hint">🔍</div></div>`;
      }});
      body += `</div>`;
    }}

    // === 录屏内联播放（HTML5 <video>）===
    if (f.video_url) {{
      body += `<div class="field" style="margin-top:12px;"><strong>操作录屏</strong></div>`;
      body += `<div class="video-player"><video controls preload="metadata" src="${{escapeAttr(f.video_url)}}"></video></div>`;
    }}

    // === 其他 artifacts 按钮（DOM 快照 / Console / Trace）===
    const actions = [];
    if (f.page_source_url) actions.push(`<a class="btn secondary" href="${{escapeAttr(f.page_source_url)}}" target="_blank">查看 DOM 快照</a>`);
    if (f.console_logs_url) actions.push(`<a class="btn secondary" href="${{escapeAttr(f.console_logs_url)}}" target="_blank">Console 日志</a>`);
    if (f.trace_launch_cmd) actions.push(`<button class="btn trace" onclick="showTraceHelp('${{escapeAttr(f.trace_launch_cmd)}}')">🎬 Trace Viewer 已启动</button>`);
    else if (f.trace_url) actions.push(`<a class="btn trace" href="${{escapeAttr(f.trace_url)}}" download>⬇️ 下载 trace.zip</a>`);
    if (actions.length) body += `<div class="actions">${{actions.join("")}}</div>`;
    if (f.trace_launch_cmd) body += `<div class="trace-cmd" style="margin-top:8px;"><span style="color:#5f6368; font-size:12px;">如未弹出窗口，复制以下命令到终端执行：</span><pre>${{escapeHtml(f.trace_launch_cmd)}}</pre></div>`;
    html += `<div class="failure-detail"><h3>${{escapeHtml(f.nodeid)}}</h3>${{body}}</div>`;
  }});
  document.getElementById("failure-list").innerHTML = html;
}}

// === Lightbox：点击截图放大查看 ===
function openLightbox(src) {{
  const lb = document.getElementById("lightbox");
  document.getElementById("lightbox-img").src = src;
  lb.classList.add("open");
  document.body.style.overflow = "hidden";
}}
function closeLightbox() {{
  const lb = document.getElementById("lightbox");
  lb.classList.remove("open");
  document.getElementById("lightbox-img").src = "";
  document.body.style.overflow = "";
}}

// === Trace Viewer 帮助弹窗（generate_report 阶段已 detached 启动）===
function showTraceHelp(cmd) {{
  const msg = "Trace Viewer 已在报告生成时启动，请切到 Playwright Trace Viewer 窗口查看。\\n\\n如未看到窗口，复制以下命令到终端执行：\\n\\n" + cmd;
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(cmd).then(() => alert(msg + "\\n\\n（命令已复制到剪贴板）"));
  }} else {{
    alert(msg);
  }}
}}

// Esc 关闭 lightbox
document.addEventListener("keydown", e => {{
  if (e.key === "Escape") closeLightbox();
}});

function escapeHtml(s) {{
  return (s || "").replace(/[&<>"']/g, c => ({{
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }})[c]);
}}
function escapeAttr(s) {{
  return (s || "").replace(/[']/g, "\\'");
}}

// === 用例明细表 ===
let FILTERED = [];
let PAGE = 0;
const PAGE_SIZE = 20;
function applyFilter() {{
  const q = document.getElementById("filter-input").value.toLowerCase();
  const st = document.getElementById("filter-status").value;
  const br = document.getElementById("filter-browser").value;
  FILTERED = PAYLOAD.tests.filter(t => {{
    if (q && !(t.nodeid.toLowerCase().includes(q) || (t.file||"").toLowerCase().includes(q))) return false;
    if (st && t.status !== st) return false;
    if (br && t.browser !== br) return false;
    return true;
  }});
  PAGE = 0;
  renderTestTable();
}}
function renderTestTable() {{
  const total = FILTERED.length;
  const start = PAGE * PAGE_SIZE;
  const slice = FILTERED.slice(start, start + PAGE_SIZE);
  if (!slice.length) {{
    document.getElementById("test-table").innerHTML = "<div class='empty'>无匹配用例</div>";
  }} else {{
    let html = "<table><tr><th>用例</th><th>状态</th><th>耗时(s)</th><th>浏览器</th><th>标记</th></tr>";
    slice.forEach(t => {{
      const cls = t.status === "passed" ? "passed" : (t.status === "skipped" ? "skipped" : "failed");
      html += `<tr><td title="${{escapeAttr(t.nodeid)}}">${{escapeHtml(t.nodeid)}}</td>
        <td><span class="badge ${{cls}}">${{t.status}}</span></td>
        <td>${{t.duration}}</td><td>${{t.browser || "—"}}</td>
        <td>${{(t.markers || []).join(", ")}}</td></tr>`;
    }});
    html += "</table>";
    document.getElementById("test-table").innerHTML = html;
  }}
  document.getElementById("pager-info").textContent = `第 ${{total === 0 ? 0 : start + 1}}-${{Math.min(start + PAGE_SIZE, total)}} 条 / 共 ${{total}} 条`;
}}
function setupTestTable() {{
  // 浏览器筛选项
  const browsers = [...new Set(PAYLOAD.tests.map(t => t.browser).filter(x => x))];
  const sel = document.getElementById("filter-browser");
  browsers.forEach(b => {{ const o = document.createElement("option"); o.value = b; o.textContent = b; sel.appendChild(o); }});
  document.getElementById("filter-input").addEventListener("input", applyFilter);
  document.getElementById("filter-status").addEventListener("change", applyFilter);
  document.getElementById("filter-browser").addEventListener("change", applyFilter);
  document.getElementById("pager-prev").addEventListener("click", () => {{ if (PAGE > 0) {{ PAGE--; renderTestTable(); }} }});
  document.getElementById("pager-next").addEventListener("click", () => {{
    if ((PAGE + 1) * PAGE_SIZE < FILTERED.length) {{ PAGE++; renderTestTable(); }}
  }});
  FILTERED = PAYLOAD.tests;
  renderTestTable();
}}

// === 启动 ===
renderOverview();
renderCharts();
renderBrowserMatrix();
renderModuleTable();
renderDiagnose();
renderRisk();
renderFailures();
setupTestTable();
</script>
</body>
</html>
"""
