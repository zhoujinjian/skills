# Report JSON Schema

## 顶层结构

```json
{
  "generated_at": "2026-06-16T14:32:00",
  "suite": { TestSuiteSummary },
  "by_module": { ... },
  "by_priority": { ... },
  "by_browser": { ... },
  "failures": [ TestCaseResult, ... ],
  "tests": [ TestCaseResult, ... ]
}
```

## TestSuiteSummary

| 字段 | 类型 | 说明 |
|------|------|------|
| `total` | int | 用例总数 |
| `passed` | int | 通过数 |
| `failed` | int | 失败数（断言失败）|
| `errors` | int | 错误数（setup/teardown 异常）|
| `skipped` | int | 跳过数（skip / xfail）|
| `reruns` | int | 重试次数（pytest-rerunfailures）|
| `pass_rate` | float | 通过率（0-100）|
| `total_duration` | float | 总耗时秒数 |
| `slowest_test` | string | 最慢用例 nodeid |
| `slowest_duration` | float | 最慢用例耗时秒数 |

## TestCaseResult

| 字段 | 类型 | 说明 |
|------|------|------|
| `nodeid` | string | 完整用例 ID（`tests/x.py::TestClass::test_method`）|
| `name` | string | 用例方法名 |
| `classname` | string | 类全名 |
| `file` | string | 测试文件相对路径 |
| `line` | string | 源码行号 |
| `status` | string | `passed` / `failed` / `error` / `skipped` / `rerun` |
| `duration` | float | 单用例耗时秒数 |
| `message` | string | 失败摘要（首行）|
| `traceback` | string | 完整 traceback（截断 4000 字符）|
| `markers` | array[string] | pytest marker 列表 |
| `artifacts` | dict | artifact 路径字典 |
| `browser` | string | 执行浏览器（如 `chromium`）|
| `worker` | string | xdist worker ID（如 `gw0`）|

## artifacts 字段结构

```json
"artifacts": {
  "screenshots": [
    "test-results/artifacts/screenshots/xxx-viewport.png",
    "test-results/artifacts/screenshots/xxx-fullpage.png"
  ],
  "videos": [
    "test-results/artifacts/videos/xxx.webm"
  ],
  "traces": [
    "test-results/artifacts/traces/xxx.zip"
  ],
  "har": [],
  "page_source": [
    "test-results/artifacts/page-source/xxx.html"
  ],
  "console_logs": [
    "test-results/artifacts/console-logs/xxx.log"
  ]
}
```

## by_module 聚合

key 是从 `classname` 推断的模块名（去掉 `test_` 前缀）：

```json
"by_module": {
  "auth": {
    "passed": 5,
    "failed": 1,
    "error": 0,
    "skipped": 0,
    "total": 6
  },
  "product": {
    "passed": 13,
    "failed": 1,
    "error": 0,
    "skipped": 0,
    "total": 14
  }
}
```

## by_priority 聚合

key 是优先级 marker（`P0` / `P1` / `P2` / `P3`）：

```json
"by_priority": {
  "P0": {"passed": 6, "failed": 0, "total": 6},
  "P1": {"passed": 7, "failed": 1, "total": 8}
}
```

**注意**：`by_priority` 当前从测试用例的 marker 提取，需要项目 conftest 把 marker 注入到 JUnit XML（默认 JUnit 不含 marker 信息）。可以通过自定义 `pytest_runtest_makereport` 在 `system-out` 写入 `[MARKERS=P0,scene_positive,...]` 实现。

## by_browser 聚合

key 是浏览器引擎名（`chromium` / `firefox` / `webkit`）：

```json
"by_browser": {
  "chromium": {"passed": 18, "failed": 2, "total": 20},
  "firefox": {"passed": 19, "failed": 1, "total": 20}
}
```

通过 `conftest_template.py` 的 `inject_browser_worker_marker` fixture 注入 `[BROWSER=xxx]` 标记，报告生成器解析后填充此字段。

## 失败用例优先级判定

`failures` 数组按以下顺序排序：

1. 失败时间倒序（最近的在前）
2. 同一时间按 nodeid 字典序

## 扩展字段

如需添加自定义字段（如 JIRA 链接、用例所有者），扩展 `TestCaseResult` 数据类：

```python
@dataclass
class TestCaseResult:
    # ... 原有字段
    jira_id: str = ""
    owner: str = ""
    tags: list[str] = field(default_factory=list)
```

并在 `parse_junit_xml` 中从 properties 提取：

```xml
<testcase name="test_xxx">
  <properties>
    <property name="jira_id" value="PROJ-123"/>
    <property name="owner" value="alice"/>
  </properties>
</testcase>
```

通过 pytest 的 `@pytest.mark.property(name="jira_id", value="PROJ-123")` 或自定义 marker 注入。

## CI 集成模式

### 模式 1：单行摘要

读取 `summary.txt`：

```
✅ UI Test: 18/20 passed (90.0%) | 2 failed, 0 errors, 0 skipped | 156.3s
```

直接作为 CI build description。

### 模式 2：完整 JSON

读取 `report.json`，推送到看板系统：

```python
import json
report = json.load(open("test-results/report.json"))

# 失败用例推送到 Slack
for failure in report["failures"]:
    notify_slack(
        title=failure["nodeid"],
        message=failure["message"],
        artifacts=failure["artifacts"]
    )
```

### 模式 3：趋势分析

将多次执行的 `suite` 字段写入时序数据库：

```sql
INSERT INTO ui_test_history (run_id, total, passed, failed, pass_rate, duration, ts)
VALUES ('build-1234', 20, 18, 2, 90.0, 156.3, NOW());
```

Grafana 通过 pass_rate 趋势图识别质量波动。

### 模式 4：失败聚类

将所有 `failures` 的 `message` + `traceback` 做文本聚类，找出同类失败：

```python
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer

messages = [f["message"] for f in report["failures"]]
vec = TfidfVectorizer()
X = vec.fit_transform(messages)
clusters = DBSCAN().fit_predict(X)

for cluster_id in set(clusters):
    members = [i for i, c in enumerate(clusters) if c == cluster_id]
    print(f"Cluster {cluster_id}: {len(members)} failures")
```

## 与 JUnit XML 的映射

| JUnit 字段 | report.json 字段 | 说明 |
|-----------|------------------|------|
| `<testsuite tests="N">` | `suite.total` | |
| `<testsuite failures="F">` | `suite.failed` | |
| `<testsuite errors="E">` | `suite.errors` | |
| `<testsuite skipped="S">` | `suite.skipped` | |
| `<testsuite time="T">` | `suite.total_duration` | |
| `<testcase time="t">` | `TestCaseResult.duration` | |
| `<testcase><failure message="...">` | `TestCaseResult.message` | |
| `<testcase><failure>traceback</failure>` | `TestCaseResult.traceback` | |
| `<testcase><system-out>[BROWSER=...]` | `TestCaseResult.browser` | 自定义注入 |

## 与 Allure 的关系

如果项目需要更丰富的报告（图表、历史趋势、用例分类树），可以同时集成 Allure：

```bash
pytest tests/ --alluredir=./allure-results
allure serve ./allure-results
```

本技能不内置 Allure（避免重型依赖），但 `report.json` 的结构化数据可以直接转换为 `allure-results` 格式（每个 TestCaseResult 对应用例一个 JSON）。
