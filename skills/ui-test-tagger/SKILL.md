---
name: ui-test-tagger
description: "WEB UI 自动化测试脚本（Playwright + POM + Pytest）的智能标签化管理专家。当用户需要为 UI 测试脚本批量打标签、检测标签冲突、补全缺失标签、生成标签统计报告时使用此技能。支持六维标签体系：优先级(P0-P3)、模块(module:xxx)、场景(scene:xxx)、页面类型(page:xxx)、执行策略(run:xxx)、浏览器/平台(browser:xxx, platform:xxx)。自动解析测试方法名、docstring、page.goto() 路径、Playwright 操作步骤、断言内容，并参照 pages.yaml 推断模块和优先级。即使用户只是说'给 UI 用例打标签'、'按模块跑用例'、'筛选冒烟用例'、'这些 Playwright 脚本要分类'，也应使用此技能。"
agent_created: true
---

# UI 测试脚本智能标签化管理

## Overview

为 WEB UI 自动化测试脚本（Playwright + Page Object Model + Pytest）自动打上标准化标签，建立可筛选、可过滤、可统计的标签体系，为后续按标签执行（`pytest -m`）、按模块生成报告、按优先级调度、按浏览器分发提供基础。

## 触发场景

- 用户要求为 UI 测试脚本打标签、添加标记、标注优先级
- 用户要求按模块/场景/页面/优先级分类管理 Playwright 测试用例
- 用户要求检测标签冲突或补全缺失标签
- 用户要求生成标签分布统计报告
- 用户提到"标签管理"、"标记用例"、"分类测试"、"冒烟用例筛选"、"按浏览器跑用例"等关键词
- 用户已经用 `ui-testscript-generator` / `ui-testscript-enhancer` 产出了大量测试脚本，需要建立标签体系统一管理

## 标签体系

六维标准化标签：

| 维度 | 标签格式 | 值域示例 | 必填 |
|------|---------|----------|------|
| 优先级 | P0/P1/P2/P3 | P0=核心链路, P1=重要, P2=一般, P3=边缘 | 是 |
| 模块 | module:xxx | login/product/cart/order/checkout/user/address/payment/admin | 是 |
| 场景 | scene:xxx | positive/negative/boundary/full_flow/visual_regress | 是 |
| 页面类型 | page:xxx | home/list/detail/form/dialog | 是 |
| 执行策略 | run:xxx | smoke/regression/full | 是 |
| 浏览器/平台 | browser:xxx, platform:xxx | chrome/firefox/edge/safari/headless；windows/linux/mac | 否（按需） |

详细规范参见 `references/tag_specification.md`。

## 工作流程

### Step 1: 收集输入

确认以下输入：

1. **测试脚本目录**（必需）：包含 `test_*.py` 或 `*_test.py` 的目录路径（通常是 `testcases/` 或 `tests/`）
2. **页面定义文件**（可选）：`pages.yaml` 路径，用于辅助模块归属、页面类型识别和优先级判断
3. **操作模式**：
   - `analyze`：仅分析，不修改文件，输出推荐结果和统计报告（默认，安全优先）
   - `apply`：分析并写入标签到脚本文件
   - `report`：仅生成标签统计报告

若用户未明确指定模式，默认使用 `analyze` 模式。

### Step 2: 运行标签分析脚本

使用 `scripts/tag_analyzer.py` 执行分析。**执行 Python 前先在用户环境中确认可用的解释器**，优先级为：

1. 用户项目虚拟环境（`.venv/bin/python`、`venv/bin/python`）
2. 全局 `python3`
3. 已知的内部环境 `/Users/zhoujinjian/.workbuddy/binaries/python/envs/default/bin/python3`

```bash
# 分析模式（不写入，推荐首次使用）
python3 <skill_dir>/scripts/tag_analyzer.py <testcase_dir> \
    --pages-yaml <pages_yaml_path> \
    --dry-run \
    --output ui_tag_statistics.md

# 写入模式（用户确认后再执行）
python3 <skill_dir>/scripts/tag_analyzer.py <testcase_dir> \
    --pages-yaml <pages_yaml_path> \
    --output ui_tag_statistics.md

# 仅生成报告（不写入标签）
python3 <skill_dir>/scripts/tag_analyzer.py <testcase_dir> \
    --no-write \
    --output ui_tag_statistics.md
```

其中 `<skill_dir>` 为本技能的安装路径（通常为 `~/.claude/skills/ui-test-tagger`）。

**参数说明：**
- `testcase_dir`：测试脚本目录（必需）
- `--pages-yaml`：pages.yaml 路径（可选；缺失时仅依赖脚本语义推断）
- `--dry-run`：仅分析不写入（推荐首次使用）
- `--no-write`：不写入标签到脚本，仅生成报告
- `--output`：统计报告输出路径（默认 `ui_tag_statistics.md`）
- `--browser`：预设浏览器标签，批量覆盖（如 `chrome`，可选）
- `--platform`：预设平台标签，批量覆盖（如 `linux`，可选）

### Step 3: 人工确认标签推荐结果

向用户展示分析结果摘要：
- 解析的测试方法数量、测试类数量、涉及页面数
- 推荐标签分布（按六维统计）
- 检测到的标签冲突数量
- 缺失关键标签的方法数量
- 页面类型识别准确率提示

**对于 `apply` 模式**，在写入前必须先以 `--dry-run` 运行并让用户确认推荐结果。UI 测试标签中模块/页面类型推断依赖路径和类名，需用户校验是否符合项目实际模块划分。

### Step 4: 标签写入（apply 模式）

用户确认后，去掉 `--dry-run` 参数重新运行脚本，将标签写入测试文件。

写入方式采用 `@pytest.mark.xxx` 装饰器，含冒号标签使用下划线替代（如 `module:login` → `@pytest.mark.module_login`，`page:detail` → `@pytest.mark.page_detail`），详见 `references/tag_specification.md` 中的装饰器映射表。

同时需确保项目的 `conftest.py` 中注册了对应的自定义标记（脚本会在报告中提示缺失的标记）。

### Step 5: 生成统计报告

脚本运行完成后自动生成 `ui_tag_statistics.md`，内容包括：
- 概览（方法总数、类总数、页面总数、冲突数、缺失数）
- 六维标签分布表格
- 标签冲突明细
- 标签补全建议清单
- 页面类型识别命中率
- 标签覆盖缺口

将报告内容展示给用户，并提示后续可以：
- 按 `pytest -m "P0 and scene_positive"` 执行冒烟测试
- 按 `pytest -m "module_order"` 执行订单模块测试
- 按 `pytest -m "page_form and run_regression"` 执行所有表单页回归
- 按 `pytest -m "browser_chrome"` 筛选 Chrome 专用用例
- 结合 `--browser` 参数与 `browser:` 标签做跨浏览器矩阵执行

## 智能标签推荐规则

### 优先级判定

1. 页面 URL 路径匹配核心链路（`/login`、`/order/create`、`/checkout`、`/payment/pay` 等）→ **P0**
2. pages.yaml 中页面标记了 `priority` 字段 → 按标记
3. 方法名/docstring 含核心业务关键词（登录、下单、支付、结账、全流程）→ **P0**
4. 方法名/docstring 含管理/统计/配置关键词 → **P2/P3**
5. 默认 → **P1**

### 场景判定

1. 方法名含 success/valid/normal/complete/full_flow → **scene:positive** 或 **scene:full_flow**
2. 方法名含 error/invalid/fail/exception → **scene:negative**
3. 方法名含 boundary/limit/min/max → **scene:boundary**
4. 方法名含 visual/screenshot/regress → **scene:visual_regress**
5. docstring 含「全流程」「端到端」「E2E」→ **scene:full_flow**
6. 默认 → **scene:positive**

### 页面类型判定

| 路径特征 | 页面类型 |
|---------|---------|
| `/`、`/home`、`/index` | page:home |
| `/list`、`/search`、`/products`、`/category` | page:list |
| `/detail`、`/info`、含动态 ID 段 | page:detail |
| `/login`、`/register`、`/create`、`/edit`、`/add`、`/checkout` | page:form |
| 测试涉及 dialog/modal/popup/alert | page:dialog |

### 模块判定（按优先级排列）

1. pages.yaml 中页面声明的 `module` 字段 → 对应模块
2. 测试方法内 `page.goto()` 的 URL 路径模式匹配 → 对应模块
3. 测试类名含模块关键词（`TestLoginPage` → `module:login`）→ 对应模块
4. 文件路径含模块关键词（`testcases/order/test_checkout.py` → `module:checkout`）→ 对应模块

### 执行策略判定

1. P0 + scene:positive → **run:smoke**
2. P0 或 P1 → **run:regression**
3. 其余 → **run:full**

## 冲突检测

自动检测以下冲突类型：
- 优先级冲突（如 P0 与 P3 共存）
- 场景冲突（如 scene:positive 与 scene:negative 共存）
- 策略冲突（如 run:smoke 与 P3 或 scene:negative 共存）
- 页面类型冲突（如同一方法标记多个 page:xxx）

发现冲突时在统计报告中标注，由用户决定处理方式。

## 标签补全

每个测试方法必须具备 5 类必填标签（优先级、模块、场景、页面类型、执行策略），缺失任何一类都将在报告的补全建议清单中列出。

## 批量操作

- 支持 `scripts/tag_analyzer.py` 对整个 `testcases/` 目录递归分析
- 一次运行完成全部脚本的标签推荐、冲突检测、写入和报告生成
- 支持 `--dry-run` 先预览再执行
- 支持 `--browser` / `--platform` 批量预设浏览器/平台标签，用于跨环境矩阵分发

## Resources

### scripts/

- **tag_analyzer.py** — 核心脚本，执行 UI 测试脚本语义解析（Playwright POM 模式）、pages.yaml 加载、六维智能标签推荐、冲突检测、装饰器写入和统计报告生成。直接运行即可完成全流程。

### references/

- **tag_specification.md** — 完整 UI 标签规范、打标签规则、页面类型识别规则、冲突检测规则、装饰器映射表、conftest.py 标记注册模板。当需要了解具体标签定义或冲突规则时加载此文件。
