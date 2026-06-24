# 调度策略详解

## Marker 表达式构建

`execute_tests.py::build_marker_expression()` 按以下规则构建 pytest `-m` 表达式。

### 优先级（累积包含）

`--priority P1` 表示"P1 及以上都要跑"，而不是"只跑 P1 排除 P0"。

```
P0 → (P0)
P1 → (P0 or P1)
P2 → (P0 or P1 or P2)
P3 → (P0 or P1 or P2 or P3)
```

**为什么累积？** P0 是核心链路必跑，P1 是重要回归，P2 是补充。当用户说"跑到 P2"，意味着回归要覆盖核心 + 重要 + 一般，但不跑边缘的 P3。

### 模块（OR 关系）

`--modules login order` 表示"任一模块匹配即可"：

```
--modules login order → (module_login or module_order)
```

**为什么 OR？** 用户通常想跑多个独立模块，AND 会让结果集为空。

### 标签（AND 关系）

`--tags smoke scene_positive` 表示"必须同时满足所有标签"：

```
--tags smoke scene_positive → smoke and scene_positive
```

**为什么 AND？** 标签用于精细筛选（"既是冒烟又是正向"），OR 会包含过多无关用例。

### 标签归一化

用户输入 | 归一化为 pytest marker
---|---
`P0` | `P0`
`@smoke` | `smoke`
`scene:positive` | `scene_positive`
`scene_negative` | `scene_negative`
`module:login` | `module_login`

### 用户表达式覆盖

`--marker-expr "P0 and not slow"` 提供原始表达式，**直接覆盖**自动构建：

```
自动构建: (P0) and scene_positive
用户提供: P0 and not slow
合并后: ((P0) and scene_positive) and (P0 and not slow)
```

**为什么 AND 而不是 replace？** 用户的原始表达式通常是补充限制，而不是推翻前面的筛选意图。

## 并行分发策略（pytest-xdist `--dist`）

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| `load`（默认）| 用例级负载均衡，按完成时间分发下一个 | 用例独立、setup 快 |
| `loadscope` | 类/模块内用例固定在同一 worker | POM 项目（避免 fixture 重复初始化） |
| `loadfile` | 同一文件用例固定在同一 worker | 文件间有共享状态 |
| `no` | 关闭并行 | 排查并行问题 |

### POM 项目推荐 `loadscope`

POM 项目中，每个测试类共享 `setup_class`（如启动浏览器、加载登录态）。`loadscope` 让同类用例在同一进程跑，避免每个用例都重新初始化。

### 并行度推荐

| 机器 | 推荐并行度 |
|------|-----------|
| 本地开发（4 核）| 2-4 |
| CI 容器（2 核）| 2 |
| CI 大实例（8 核）| 4-6 |
| 跨浏览器矩阵 | 浏览器数 × 单浏览器并行度 |

**注意**：并行度过高会触发系统资源限制（文件句柄、内存），开始前观察 `ulimit -n`。

## 重试策略（pytest-rerunfailures）

### 适用场景

- 网络抖动（API 偶发超时）
- CI 容器资源竞争
- 第三方服务不稳定
- 验证码识别偶发失败

### 不适用场景

- 确定性失败（DOM 结构错误、定位器失效）
- 视觉回归失败（重试可能掩盖真实回归）
- 数据状态依赖（重试会跳过 setup）

### 重试间隔

默认 2 秒，通过 `--reruns-delay` 控制。**过短的重试间隔**会导致下一次重试触发相同的临时故障；**过长**会让总执行时间爆炸。

### 重试 vs 失败重跑

| 机制 | pytest-rerunfailures | 手动重跑整个测试 |
|------|---------------------|----------------|
| 粒度 | 单用例 | 整个测试集 |
| 时机 | 实时（同一进程）| 异步（新进程）|
| 速度 | 快（已初始化的浏览器复用）| 慢（重新启动浏览器）|
| 适用 | 偶发故障 | 修复后验证 |

## 超时策略（pytest-timeout）

### 双层超时

1. **单用例超时**：`--timeout 300`（默认 5 分钟）
2. **整 suite 超时**：CI 系统级（如 GitHub Actions 6 小时）

### 推荐配置

| 用例类型 | 推荐超时 |
|---------|---------|
| 单元型 UI（登录、点击）| 60s |
| 表单流程（结账、下单）| 180s |
| 全流程 E2E | 600s |
| 视觉回归（含截图比对）| 120s |

## 跨浏览器矩阵

```bash
# 3 浏览器 × 所有用例
--browser chromium firefox webkit

# 在每个浏览器内部再并行
--browser chromium firefox webkit --parallel 3 --dist loadscope
```

### 总执行时间估算

```
总时间 = (用例数 × 单用例平均耗时) / 并行度 × 浏览器数
```

### CI 资源规划

| 浏览器数 | 并行度 | 实际进程数 | 推荐内存 |
|---------|--------|-----------|---------|
| 1 | 2 | 2 | 4GB |
| 3 | 1 | 3 | 6GB |
| 3 | 2 | 6 | 12GB |
| 3 | 4 | 12 | 24GB |

## 失败快速失败（fail-fast）

`-x` / `--fail-fast`：第一个失败立即停止。

**适用场景：**

- 本地开发快速确认问题
- CI 阻塞流水线（避免无意义继续跑）

**不适用场景：**

- 完整回归（要看所有失败）
- 上线前最终验证

## 调度策略组合示例

### 场景 1：本地快速验证 P0

```bash
--priority P0 --browser chromium --no-headless
```

无并行、有头、单浏览器，方便观察。

### 场景 2：CI 完整回归

```bash
--priority P2 \
--browser chromium firefox webkit \
--headless \
--parallel 3 \
--dist loadscope \
--retry 2 \
--timeout 600
```

3 浏览器 × 3 并行 = 9 进程，全 P0/P1/P2 用例，失败重试 2 次。

### 场景 3：每日冒烟

```bash
--tags run_smoke \
--browser chromium \
--headless \
--parallel 4 \
--fail-fast
```

只跑冒烟标签，失败立即停（冒烟失败代表 build 不稳定）。

### 场景 4：性能基线测试

```bash
--priority P0 \
--browser chromium \
--headless \
--parallel 1 \      # 串行避免竞争
--retry 0 \          # 不重试，看真实表现
--timeout 60
```
