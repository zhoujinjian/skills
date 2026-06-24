# 报告模板规范

**对齐 api-report-generator** + UI 增强。本规范定义 `ui-report-generator` 生成的单文件 HTML 布局、配色、组件。

## 配色（与 api-report-generator 一致）

| 变量 | 色值 | 用途 |
|---|---|---|
| `--primary` | `#1a73e8` | 主色：标题左边框、按钮、链接 |
| `--success` | `#34a853` | 通过状态、低风险 |
| `--fail` | `#ea4335` | 失败状态、高风险 |
| `--skip` | `#9aa0a6` | 跳过状态 |
| `--warn` | `#fbbc04` | 中风险、Trace 按钮 |
| `--bg` | `#f8f9fa` | 页面背景 |
| `--card` | `#ffffff` | 卡片背景 |
| `--text` | `#202124` | 正文 |
| `--text-muted` | `#5f6368` | 辅助文字 |
| `--border` | `#e0e0e0` | 分割线 |

## 排版

- 字体：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif`
- 行高：1.6
- 卡片圆角：12px
- 阴影：`0 1px 3px rgba(0,0,0,0.08)`
- 容器最大宽度：1400px

## 页面分区（顺序固定）

### 1. 报告头部（渐变蓝背景）
- `<h1>` 标题（用户可配）
- 元信息：生成时间 + 浏览器清单 + 总耗时

### 2. 总览大盘（6 张 KPI 卡）
- 总用例（primary）
- 通过（success）
- 失败（fail）
- 跳过（warn）
- 通过率（根据值变色：≥90% success / 70-90% warn / <70% fail）
- 总耗时秒（primary）

### 3. 数据图表（3 列 grid）
- 状态饼图（doughnut）
- 模块通过率柱图
- 历史通过率折线

### 4. 浏览器矩阵（**UI 特有**）
跨浏览器通过率表 + 风险 badge。

### 5. 模块统计
按模块（tests 子目录）展开的表，含风险列。

### 6. 诊断根因聚合
- 分类表（SCRIPT_ERROR / LOCATOR_ERROR / ...）
- 根因表（missing_async_list_wait / locator_drift / ...）
- 升级标记（assertion_mismatch）

### 7. 风险与建议
- 高风险模块表
- 优化建议列表（按 P0/P1 排序）

### 8. 失败详情（**UI 特有**）
每个失败 case 一个卡片：
- 节点路径（`h3`）
- 失败阶段 / 耗时 / 浏览器
- 诊断信息（分类 / 根因 / 修复策略 / 验证状态 / 升级原因）
- 错误消息（`<pre>`）
- Traceback（折叠的 `<details>`）
- 截图（base64 内联 `<img>`，最多 2 张）
- 操作按钮：DOM 快照 / Console 日志 / 录屏 / 打开 Trace

### 9. 用例明细（可筛选分页）
- 筛选：用例名/文件/标签 input + 状态 select + 浏览器 select
- 分页：每页 20 条

### 10. 页脚
- 生成技能标识 + 时间戳

## 交互

- **筛选**：用例明细表的 input + 2 个 select 实时筛选
- **分页**：上一页 / 下一页按钮
- **Trace 打开**：点击按钮 → `navigator.clipboard.writeText(cmd)` → alert 提示
- **图表响应式**：`maintainAspectRatio: false`，跟随容器尺寸

## 离线降级

`<script src="cdn.jsdelivr.net/.../chart.umd.min.js">` 加载失败时：
- 检测 `typeof Chart === "undefined"`
- 显示 `<div id="chart-fallback">`，内容为状态表 + 模块表的 HTML 表格
