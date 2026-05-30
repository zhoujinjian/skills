---
name: ui-page-parser
description: "UI自动化测试数据预处理技能。负责将页面URL或自然语言用例描述转换为标准化pages.yaml页面对象定义。支持全站自动爬取（单入口URL发现全站页面）、Playwright动态抓取、CDP连接模式、推断兜底模式。是ui-testcase-generator、ui-testscript-generator等后续技能的标准输入来源。当用户提供页面URL或自然语言描述的测试用例需要生成结构化页面定义文件时触发。"
agent_created: true
---

# ui-page-parser — UI 页面解析技能

## 技能概述

将多种来源的页面信息统一转换为标准化的 `pages.yaml/json` 页面对象定义，
作为 UI 自动化测试数据链路的起点，向下游所有技能提供标准输入。

核心策略：**Playwright 动态抓取 → CDP 连接 → 推断兜底**（三级降级）

- **Playwright 动态模式**（首选，零配置）：自动启动无头浏览器，抓取渲染后真实 DOM + 截图 + 文本结构
- **CDP 连接模式**（macOS 沙箱兼容）：连接沙箱外 Chrome 进程（`localhost:9222`）
- **认证抓取**：CDP 交互式认证（复用已登录会话）或 Storage State 录制（保存/复用登录状态）
- **推断兜底模式**（无法访问页面）：基于测试用例让 AI 推断页面结构，标注推断置信度

---

## 输入类型识别

接收到任务时，首先判断输入源类型，按以下优先级处理：

| 输入类型 | 识别特征 | 处理模式 |
|---------|---------|---------|
| 入口 URL（全站） | 单个 URL + "全站/所有页面" 或仅提供入口 URL | 全站爬取 |
| 页面 URL | 包含 `http://`、`https://`、`localhost` | 动态抓取 |
| DOM 文件 | `.html` 文件 / HTML 字符串 | 静态解析 |
| 前端源码 | `.vue`、`.tsx`、`.jsx` 等源码文件 | 源码分析 |
| 自然语言描述 | 纯文本用例 / 操作步骤 | AI 推断 |
| 混合输入 | URL + 用例描述（最常见场景） | 动态抓取 + 语义增强 |

### 认证需求识别

在判断输入类型的同时，检测用户是否表达了认证需求：

**显式触发**（用户明确提示）—— 直接进入认证流程，跳过首次探测：
- 用户提到"需要登录"、"要认证"、"登录后才能访问"、"需要先登录"
- 用户提供了登录页 URL 或凭据信息
- 用户提到"内网页面"、"后台页面"、"管理后台"

**隐式触发**（运行后自动检测）—— 先抓取，发现认证拦截后询问用户：
- `crawl_result.json` 中 `auth_blocked_urls` 非空
- `dom_output.json` 中页面被重定向到 `/login` 等路径
- 抓取到的页面标题包含"登录"、"Login"、"Sign In"

---

## 工作流程

### 全站爬取模式（首选，单入口 URL）

**当用户只提供一个入口 URL 时，优先使用全站爬取模式**，自动发现并抓取所有可访问页面。

#### Step 1：认证判定与准备

**如果用户显式提到需要登录/认证**（见"认证需求识别"），直接进入认证准备：

```bash
SCRIPT_DIR=~/.claude/skills/ui-page-parser/scripts

# 方案 B（推荐）：弹出浏览器录制登录状态
python3 "${SCRIPT_DIR}/auth_login.py <登录页URL> --output auth_state.json
# 用户在浏览器中完成登录后按 Enter，脚本自动保存 Storage State
```

认证完成后，后续所有抓取命令都附加 `--storage-state auth_state.json`。

**如果用户未提及认证**，跳过此步，直接进入 Step 2。

#### Step 2：运行 crawl_site.py 全站爬取

```bash
SCRIPT_DIR=~/.claude/skills/ui-page-parser/scripts

# 无认证需求时
python3 "${SCRIPT_DIR}/crawl_site.py" <入口URL> \
  --output crawl_result.json \
  --screenshots-dir ./screenshots \
  --max-depth 3 \
  --max-pages 50 \
  --verbose

# 有认证需求时（Step 1 已完成认证）
python3 "${SCRIPT_DIR}/crawl_site.py" <入口URL> \
  --storage-state auth_state.json \
  --output crawl_result.json \
  --screenshots-dir ./screenshots \
  --max-depth 3 \
  --max-pages 50 \
  --verbose
```

**爬虫自动完成：**
- 从入口 URL 开始 BFS 广度优先遍历
- 提取页面中所有 `<a href>` 链接加入爬取队列
- **Vue Router 路由发现**：自动提取 Vue 应用的路由表（支持 Vue 2/3），发现 SPA 中无 `<a>` 标签的页面
- **参数化 URL 归组**：`/product/1` ~ `/product/10` 只采样 2 个，其余标记为同类型
- **认证检测**：自动识别需登录的页面，标记为 `auth_blocked`，不重复爬取
- 每页提取：交互元素 + 文本结构 + 截图

**常用参数：**
- `--max-depth 3` — 最大爬取深度（默认 3）
- `--max-pages 50` — 最大页面数（默认 50）
- `--pattern-samples 2` — 参数化 URL 采样数（默认 2）
- `--delay-ms 500` — 页面间延迟（默认 500ms）
- `--no-screenshot` — 跳过截图（加速爬取）
- `--storage-state <path>` — 注入认证状态文件

#### Step 3：认证拦截检测与补爬

读取 `crawl_result.json`，检查 `auth_blocked_urls[]` 是否非空：

**情况 A：无认证拦截（auth_blocked_urls 为空）**
→ 直接进入 Step 4

**情况 B：有认证拦截，且已使用认证模式（Step 1 已完成）**
→ 说明 session 可能已过期，提示用户："检测到 N 个页面仍被认证拦截，Storage State 可能已过期。是否需要重新录制登录状态？"
→ 用户确认后重新运行 `auth_login.py`，再带 `--storage-state` 重新爬取

**情况 C：有认证拦截，且未使用认证模式（用户未提前声明）**
→ 向用户报告："爬取发现 N 个页面需要登录才能访问（列出前 5 个路径）。是否需要登录认证后重新抓取这些页面？"
→ 用户确认后：
  1. 运行 `auth_login.py` 录制登录状态
  2. 带 `--storage-state` 重新运行 `crawl_site.py`
  3. 用新结果替换 `crawl_result.json`

#### Step 4：分析爬取结果

读取 `crawl_result.json`，关注：
- `crawl_summary`：发现总数、已爬取、需认证、参数化跳过、耗时、`auth_mode`
- `pages[]`：每个已爬取页面的完整 DOM 数据（elements、text_structure、screenshot）
- `vue_routes`：Vue Router 发现的完整路由表（含路由名、参数信息）
- `url_patterns[]`：参数化 URL 归组（如 `/product/{product}` 共 10 个实例，采样了 2 个）
- `auth_blocked_urls[]`：需认证的页面列表（含重定向信息）

#### Step 5：生成全站 pages.yaml

基于爬取结果，为每个页面生成 pages.yaml：
- 对 `pages[]` 中 `auth_blocked=false` 的页面，使用其 DOM 数据生成元素定义
- 对 `auth_blocked=true` 的页面（认证补爬后仍存在的），基于路由信息和业务语义推断页面结构（标注 `inference_mode`）
- 利用 `vue_routes` 的路由名作为页面名称参考
- 利用 `url_patterns` 定义参数化页面的模板

---

### 单页面抓取模式

### 识别到 URL 时的自动处理流程（核心路径）

**当输入包含 URL 时，立即执行以下步骤，无需用户手动配置：**

#### Step 1：认证判定与准备（同全站爬取 Step 1）

**如果用户显式提到需要登录/认证**：
1. 向用户询问登录页 URL（如果用户未提供）
2. 运行 `auth_login.py` 弹出浏览器，用户手动登录
3. 保存 Storage State，后续抓取附加 `--storage-state`

**如果用户未提及认证**，跳过此步。

#### Step 2：运行 fetch_dom.py 抓取页面

```bash
SCRIPT_DIR=~/.claude/skills/ui-page-parser/scripts

# 无认证需求时
python3 "${SCRIPT_DIR}/fetch_dom.py" <URL> \
  --output dom_output.json \
  --screenshot screenshot.png \
  --extract-text-structure

# 有认证需求时（Step 1 已完成认证）
python3 "${SCRIPT_DIR}/fetch_dom.py" <URL> \
  --storage-state auth_state.json \
  --output dom_output.json \
  --screenshot screenshot.png \
  --extract-text-structure
```

**该脚本会自动检测并选择最佳模式：**
- 优先尝试 Launch 模式（Playwright 直接启动无头浏览器，适用于非沙箱环境）
- 若 CDP 端口可用则自动切换为 CDP 连接模式
- 若提供了 `--storage-state`，在创建浏览器上下文时注入认证状态
- 捕获失败时返回 error 字段

**常用参数：**
- `--wait-for "#app"` — 等待 SPA 根节点渲染后再抓取
- `--wait-for "[data-testid='page-loaded']"` — 等待特定加载标识
- `--timeout 60000` — 慢速网络适当延长超时
- `--full-page-screenshot` — 全页截图（默认仅视口）
- `--storage-state <path>` — 注入认证状态文件

#### Step 3：认证拦截检测与重试

读取 `dom_output.json`，检查是否被重定向到登录页：
- 如果 `error` 为 null 但页面标题包含"登录"/"Login"/"Sign In"，且用户未使用认证模式 → 页面可能需要登录
- 如果 `auth_mode` 有值但仍然被拦截 → 提示用户 session 可能已过期

**发现认证拦截时**，向用户报告：
> "页面 `URL` 抓取结果显示为登录页面，该页面可能需要登录后才能访问。是否需要登录认证后重新抓取？"

用户确认后：
1. 询问登录页 URL
2. 运行 `auth_login.py` 录制登录状态
3. 带 `--storage-state` 重新运行 `fetch_dom.py`
4. 用新结果替换 `dom_output.json`

#### Step 4：分析抓取结果

读取 `dom_output.json`，重点分析：
- `error` 字段：若非 null，说明抓取失败，降级到推断模式
- `auth_mode` 字段：认证方式（`cdp_authenticated` / `storage_state` / null）
- `title`：页面标题
- `elements` 数组：所有可交互元素，包含：
  - `tag`, `type`, `id`, `name`, `placeholder`
  - `data_testid`, `aria_label`, `aria_labelledby`, `role`
  - `class`, `text_content`, `href`, `value`
  - `is_visible`, `interaction_hint`（navigate/submit/input/select/click/toggle 等）
  - `xpath`, `css`（定位器）
- `text_structure` 数组：页面语义文本（h1-h6, p, li, label, nav-link 等）
- `screenshot`：截图路径，用于视觉确认页面内容

#### Step 5：结合业务用例进行语义增强

如果有用户提供的业务用例，为每个元素赋予**业务语义名称**：
- DOM 中的 `data-testid="login-btn"` → 业务名称："登录按钮"
- 根据元素在页面中的位置、上下文、`interaction_hint` 判断其用途

#### Step 6：生成 pages.yaml

**如果有 DOM 数据（error == null）：**

1. 生成 LLM 草稿 YAML（按 `references/pages_schema.md` 结构）
2. 调用 `scripts/build_pages_yaml.py` 合并 DOM 数据与 LLM 草稿：

```bash
python3 "${SCRIPT_DIR}/build_pages_yaml.py" dom_output.json llm_draft.yaml --output pages.yaml
```

**如果抓取失败（error != null）：** 进入推断兜底模式（见下方）

---

### macOS 沙箱环境（CDP 连接模式）

**仅当 Playwright Launch 模式失败时**（沙箱环境报错 `Permission denied (1100)`），才需要使用 CDP 模式：

```bash
# 在 Terminal（沙箱外）执行一次即可：
bash ~/.workbuddy/skills/ui-page-parser/scripts/start_chrome_cdp.sh

# 验证 CDP 服务已启动：
curl -s http://localhost:9222/json/version
```

CDP 启动后，重新运行 `fetch_dom.py`（脚本会自动检测并使用 CDP 模式）。

---

### 认证页面抓取

当目标页面需要登录才能访问时，提供两种认证抓取方式。根据场景选择：

| 场景 | 推荐方式 |
|------|---------|
| 单次快速抓取 | 方案 A：CDP 交互式 |
| 需要反复抓取 / CI/CD | 方案 B：Storage State 录制 |
| SSO / OAuth / 验证码 / MFA | 方案 A 或方案 B 均可 |

#### 方案 A：CDP 交互式认证（适合单次抓取）

原理：启动带界面的 Chrome，用户手动登录后，技能通过 CDP 复用已认证会话。

**Step 1：启动交互式 Chrome CDP**

```bash
bash ~/.claude/skills/ui-page-parser/scripts/start_chrome_cdp.sh --interactive
```

**Step 2：在弹出的浏览器中手动登录目标网站**

- 浏览器会显示完整界面（非 headless），支持任意认证方式
- 登录成功后保持浏览器窗口打开

**Step 3：执行抓取（CDP 自动复用认证会话）**

```bash
# 单页面抓取
SCRIPT_DIR=~/.claude/skills/ui-page-parser/scripts
python3 "${SCRIPT_DIR}/fetch_dom.py <认证页面URL> --output dom.json --screenshot screenshot.png

# 全站爬取
python3 "${SCRIPT_DIR}/crawl_site.py <入口URL> --output crawl.json --screenshots-dir ./screenshots --verbose
```

脚本自动检测 CDP 连接并复用已认证的浏览器会话。输出 JSON 中 `auth_mode` 为 `"cdp_authenticated"` 表示使用了 CDP 认证模式。

#### 方案 B：Storage State 录制（适合反复抓取 / CI/CD）

原理：弹出浏览器让用户登录一次，保存 cookies + localStorage 到文件，后续抓取自动注入。

**Step 1：录制登录会话（仅需一次）**

```bash
SCRIPT_DIR=~/.claude/skills/ui-page-parser/scripts
python3 "${SCRIPT_DIR}/auth_login.py <登录页URL> --output auth_state.json
```

脚本会：
- 弹出有头浏览器并导航到登录页
- 用户在浏览器中手动完成登录
- 登录成功后回到终端按 Enter
- 保存 Storage State（cookies + localStorage）到 `auth_state.json`

**Step 2：使用录制状态进行抓取**

```bash
# 单页面抓取
python3 "${SCRIPT_DIR}/fetch_dom.py <认证页面URL> \
  --storage-state auth_state.json \
  --output dom.json --screenshot screenshot.png

# 全站爬取
python3 "${SCRIPT_DIR}/crawl_site.py <入口URL> \
  --storage-state auth_state.json \
  --output crawl.json --screenshots-dir ./screenshots --verbose
```

输出 JSON 中 `auth_mode` 为 `"storage_state"` 表示使用了 Storage State 认证模式。

**注意事项：**
- Storage State 文件包含敏感认证信息，请勿提交到版本控制系统
- Session 过期后需重新运行 `auth_login.py` 录制
- 若抓取时仍被重定向到登录页，说明 session 已过期，需重新录制

---

### 推断兜底模式（仅有自然语言或抓取失败）

当无法访问页面时，基于用例描述进行 AI 推断：

1. **页面识别**：从用例中的操作描述推断涉及哪些页面
2. **元素推断**：根据动词推断元素类型（输入→input，点击→button，选择→select）
3. **定位器推断**：按 `references/locator_strategy.md` 优先级推断合理定位器
4. **标注推断模式**：
   ```yaml
   source:
     inference_mode: true
     confidence: "medium"
   metadata:
     inference_note: "元素定位器为AI推断值，建议通过真实页面访问后校准"
   ```
5. **直接生成 pages.yaml**（跳过 `build_pages_yaml.py` 的 DOM 富化步骤）

---

### 静态 HTML / 前端源码模式

- **HTML 文件**：直接读取 HTML 内容，用正则或简单解析提取元素属性
- **Vue/React 源码**：分析模板/JSX 中的元素定义，提取 `data-testid`、`ref`、`id`、事件绑定

---

## 关键解析要点

### 定位策略选择
优先级：`data-testid` > `aria-label` > `id` > `name` > CSS > XPath
详细规则参考 `references/locator_strategy.md`

### 状态机识别
识别页面状态时关注：
- 加载态、空态、有数据态（列表/详情页）
- 表单：初始态、填写中、提交中、成功态、失败态
- 权限控制态（未登录/无权限）
- 弹窗触发状态

### 隐性规则提取
重点识别：
- **弹窗触发**：哪些操作会触发 Modal/Drawer/Toast
- **异步加载**：AJAX 请求、Skeleton 骨架屏、Loading 图标
- **iframe 嵌套**：验证码、第三方组件
- **权限控制**：哪些元素/功能需要特定角色才可见
- **表单联动**：字段间的级联关系（选省→选市）

### 多页面处理
当用例涉及多个页面时：
- 每个页面对应 `pages` 数组中的独立条目
- 在 `flows` 中记录页面间的跳转关系
- 确保 `url` 字段能唯一区分各页面
- 对每个 URL 分别运行 `fetch_dom.py` 获取各页面的 DOM

---

## 输出规范

### 文件命名
```
pages.yaml          # 完整页面定义（首选格式）
pages.json          # 等价 JSON 格式（工具链集成时使用）
pages_{module}.yaml # 按模块拆分（元素数量超过 100 个时建议拆分）
```

### 交付要求
- 必须包含所有在用例中提及的页面
- 每个页面至少包含：`page_name`、`url`、`elements`
- 所有可交互元素必须有有效的 `locator`（真实或推断）
- 推断模式下必须添加 `inference_mode: true` 和 `inference_note`

---

## Schema 快速参考

完整字段定义见 `references/pages_schema.md`，
定位策略详细说明见 `references/locator_strategy.md`，
可用 `assets/pages_template.yaml` 作为起点修改。

---

## 典型使用场景示例

**场景 1：全站爬取（首选，仅入口 URL）**
```
输入：URL = http://localhost:3000/
处理：
  1. 运行 crawl_site.py http://localhost:3000/ -o crawl.json --screenshots-dir ./screenshots --verbose
  2. 读取 crawl.json，获取全站 21 个 URL、6 个公开页面 DOM、15 个需认证页面、24 条路由
  3. 为每个页面生成 pages.yaml（公开页面用真实 DOM，需认证页面用推断模式）
```

**场景 2：单页面抓取（指定 URL + 用例）**
```
输入：URL = http://localhost:3000/login
      用例 = "用户在登录页输入用户名和密码，点击登录按钮，成功后跳转到首页"
处理：
  1. 运行 fetch_dom.py http://localhost:3000/login --output dom.json --screenshot shot.png --extract-text-structure
  2. 读取 dom.json 分析元素
  3. 结合用例语义增强
  4. 生成 pages.yaml
```

**场景 3：多页面 URL**
```
输入：URLs = http://localhost:3000/, http://localhost:3000/products, http://localhost:3000/cart
处理：
  1. 对每个 URL 分别运行 fetch_dom.py
  2. 合并分析所有页面的 DOM 数据
  3. 识别页面间跳转关系
  4. 生成统一 pages.yaml
```

**场景 4：仅有用例描述（推断模式）**
```
输入：用例 = "用户打开商品列表页，筛选'电子产品'类目，点击某商品进入详情页"
处理：AI 推断 → 推断模式 pages.yaml（标注 inference_mode: true）
```

**场景 5：前端源码**
```
输入：Login.vue / LoginPage.tsx
处理：分析模板/JSX 中的元素定义 → 提取 data-testid、ref、id → 生成 pages.yaml
```

**场景 6：认证页面抓取（用户显式提示）**
```
输入：URL = https://example.com/dashboard
      提示 = "这个页面需要登录，登录页是 https://example.com/login"
处理：
  1. 识别到认证需求 → 运行 auth_login.py https://example.com/login --output auth_state.json
  2. 用户在浏览器中完成登录，按 Enter
  3. 运行 fetch_dom.py https://example.com/dashboard --storage-state auth_state.json --output dom.json
  4. 读取 dom.json（auth_mode=storage_state），分析认证后的真实页面元素
  5. 生成 pages.yaml
```

**场景 7：全站爬取自动检测认证（隐式触发）**
```
输入：URL = http://localhost:3000/
      无认证提示
处理：
  1. 运行 crawl_site.py（不带 --storage-state）
  2. 爬取结果：6 个公开页面 + 15 个 auth_blocked_urls
  3. 向用户报告："发现 15 个页面需要登录才能访问，是否需要认证后重新抓取？"
  4. 用户确认 → 运行 auth_login.py 录制登录状态
  5. 带 --storage-state 重新爬取 → 获得全部页面的真实 DOM
  6. 生成完整 pages.yaml
```
