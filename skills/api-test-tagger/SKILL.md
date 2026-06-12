---
name: api-test-tagger
description: 接口自动化测试脚本智能标签化管理专家。当用户需要为API测试脚本批量打标签、检测标签冲突、补全缺失标签、生成标签统计报告时使用此技能。适用于已有pytest测试脚本但缺乏标准化标签体系的场景，支持优先级(P0-P3)、模块(module:xxx)、场景(scene:xxx)、执行策略(run:xxx)、环境(env:xxx)五维标签体系，自动基于脚本语义和接口定义推荐标签，检测冲突并生成统计报告。
agent_created: true
---

# API测试脚本智能标签化管理

## Overview

为接口自动化测试脚本自动打上标准化标签，建立可筛选、可过滤、可统计的标签体系，为后续按标签执行（pytest -m）、按模块报告、按优先级调度提供基础。

## 触发场景

- 用户要求为测试脚本打标签、添加标记、标注优先级
- 用户要求按模块/场景/优先级分类管理测试用例
- 用户要求检测标签冲突或补全缺失标签
- 用户要求生成标签分布统计报告
- 用户提到"标签管理"、"标记用例"、"分类测试"、"冒烟用例筛选"等关键词

## 标签体系

五维标准化标签：

| 维度 | 标签格式 | 值域 | 必填 |
|------|---------|------|------|
| 优先级 | P0/P1/P2/P3 | P0=核心链路, P1=重要, P2=一般, P3=边缘 | 是 |
| 模块 | module:xxx | auth/order/product/cart/user/address/payment/admin | 是 |
| 场景 | scene:xxx | positive/negative/boundary/security | 是 |
| 执行策略 | run:xxx | smoke/regression/full | 是 |
| 环境 | env:xxx | dev/test/pre/prod | 否（默认env:test） |

详细规范参见 `references/tag_specification.md`。

## 工作流程

### Step 1: 收集输入

确认以下输入：

1. **测试脚本目录**（必需）：包含 `test_*.py` 或 `*_test.py` 的目录路径
2. **接口定义文件**（可选）：`api_definitions.json` 路径，用于辅助模块归属和优先级判断
3. **操作模式**：
   - `analyze`：仅分析，不修改文件，输出推荐结果和统计报告
   - `apply`：分析并写入标签到脚本文件
   - `report`：仅生成标签统计报告

若用户未明确指定模式，默认使用 `analyze` 模式（安全优先）。

### Step 2: 运行标签分析脚本

使用 `scripts/tag_analyzer.py` 执行分析：

```bash
# 分析模式（不写入）
/Users/zhoujinjian/.workbuddy/binaries/python/envs/default/bin/python3 <skill_dir>/scripts/tag_analyzer.py <script_dir> --api-definitions <api_defs_path> --dry-run --output tag_statistics.md

# 写入模式
/Users/zhoujinjian/.workbuddy/binaries/python/envs/default/bin/python3 <skill_dir>/scripts/tag_analyzer.py <script_dir> --api-definitions <api_defs_path> --output tag_statistics.md

# 仅生成报告（不写入标签）
/Users/zhoujinjian/.workbuddy/binaries/python/envs/default/bin/python3 <skill_dir>/scripts/tag_analyzer.py <script_dir> --no-write --output tag_statistics.md
```

其中 `<skill_dir>` 为本技能的安装路径（通常为 `~/.workbuddy/skills/api-test-tagger`）。

**参数说明：**
- `script_dir`：测试脚本目录（必需）
- `--api-definitions`：API定义文件路径（可选）
- `--dry-run`：仅分析不写入（推荐首次使用）
- `--no-write`：不写入标签到脚本，仅生成报告
- `--output`：统计报告输出路径（默认 `tag_statistics.md`）

### Step 3: 人工确认标签推荐结果

向用户展示分析结果摘要：
- 解析的测试方法数量
- 推荐标签分布
- 检测到的标签冲突数量
- 缺失标签的方法数量

**对于 `apply` 模式**，在写入前必须先以 `--dry-run` 运行并让用户确认推荐结果。

### Step 4: 标签写入（apply模式）

用户确认后，去掉 `--dry-run` 参数重新运行脚本，将标签写入测试文件。

写入方式采用 `@pytest.mark.xxx` 装饰器，含冒号标签使用下划线替代（如 `module:auth` → `@pytest.mark.module_auth`），详见 `references/tag_specification.md` 中的标签映射表。

同时需确保项目的 `conftest.py` 中注册了对应的自定义标记。

### Step 5: 生成统计报告

脚本运行完成后自动生成 `tag_statistics.md`，内容包括：
- 概览（方法总数、类总数、冲突数、缺失数）
- 各维度标签分布表格
- 标签冲突明细
- 标签补全建议清单
- 标签覆盖缺口

将报告内容展示给用户，并提示后续可以：
- 按 `pytest -m "P0 and scene_positive"` 执行冒烟测试
- 按 `pytest -m "module_order"` 执行订单模块测试
- 按 `pytest -m "run_regression"` 执行回归测试

## 智能标签推荐规则

### 优先级判定

1. 接口路径匹配核心链路（`/api/auth/login`、`/api/order/create`、`/api/payment/pay` 等）→ **P0**
2. API定义文件中标记 priority → 按标记
3. 方法名/docstring含核心业务关键词 → **P0**
4. 方法名/docstring含通用业务关键词 → **P1**
5. 方法名/docstring含管理/配置关键词 → **P2/P3**
6. 默认 → **P1**

### 场景判定

1. 方法名含 success/valid/normal/correct → **scene:positive**
2. 方法名含 error/invalid/fail/exception → **scene:negative**
3. 方法名含 boundary/limit/min/max → **scene:boundary**
4. 方法名含 sql/xss/inject/attack → **scene:security**
5. docstring含异常/边界/安全关键词 → 对应场景
6. 默认 → **scene:positive**

### 执行策略判定

1. P0 + scene:positive → **run:smoke**
2. P0 或 P1 → **run:regression**
3. 其余 → **run:full**

### 模块判定

1. 请求URL路径匹配模块路径模式 → 对应模块
2. 测试类名含模块关键词 → 对应模块
3. 文件路径含模块关键词 → 对应模块

## 冲突检测

自动检测以下冲突类型：
- 优先级冲突（如 P0 与 P3 共存）
- 场景冲突（如 scene:positive 与 scene:negative 共存）
- 策略冲突（如 run:smoke 与 P3 或 scene:negative 共存）

发现冲突时在统计报告中标注，由用户决定处理方式。

## 标签补全

每个测试方法必须具备4类必填标签（优先级、模块、场景、执行策略），缺失任何一类都将在报告的补全建议清单中列出。

## 批量操作

- 支持 `scripts/tag_analyzer.py` 对整个目录递归分析
- 一次运行完成全部脚本的标签推荐、冲突检测、写入和报告生成
- 支持 `--dry-run` 先预览再执行

## Resources

### scripts/

- **tag_analyzer.py** — 核心脚本，执行测试脚本语义解析、智能标签推荐、冲突检测、标签写入和统计报告生成。直接运行即可完成全流程。

### references/

- **tag_specification.md** — 完整标签规范、打标签规则、冲突检测规则、装饰器映射表。当需要了解具体标签定义或冲突规则时加载此文件。
