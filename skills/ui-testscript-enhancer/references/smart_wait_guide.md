# 智能等待策略详解

## 等待场景分类

### 1. 页面加载等待

```python
# 基础：等待网络空闲
def navigate(self) -> "PageNamePage":
    self.page.goto("/path", wait_until="networkidle")
    return self

# 严格：等待 DOM + 网络 + 特定元素
def navigate(self) -> "PageNamePage":
    self.page.goto("/path")
    self.page.wait_for_load_state("domcontentloaded")
    self.page.wait_for_load_state("networkidle")
    self._key_element.wait_for(state="visible")
    return self
```

### 2. 元素可见性等待

```python
# Playwright 自动等待（最常用）
locator.click()       # 自动等待元素 可操作
locator.fill("text")  # 自动等待元素可编辑

# 显式等待
locator.wait_for(state="visible", timeout=10000)
locator.wait_for(state="hidden", timeout=10000)
locator.wait_for(state="attached", timeout=10000)
```

### 3. AJAX 异步请求等待

```python
# 等待特定 API 响应
def submit_form(self) -> "NextPage":
    with self.page.expect_response("**/api/submit") as resp:
        self._submit_button.click()
    assert resp.value.status == 200
    return NextPage(self.page)

# 等待任意 API 完成
def wait_for_api_complete(self, api_pattern: str = "**/api/**"):
    self.page.wait_for_response(api_pattern, timeout=15000)

# 等待列表数据加载完成
def wait_for_list_loaded(self):
    self.page.wait_for_response("**/api/products**", timeout=10000)
    # 等待列表渲染
    self.page.locator(".product-item").first.wait_for(state="visible")
```

### 4. 动画/过渡等待

```python
# 方案 1：固定短延迟（简单场景）
def wait_for_animation(self, locator: Locator):
    locator.wait_for(state="visible")
    self.page.wait_for_timeout(300)  # CSS transition buffer

# 方案 2：检测 CSS 动画状态（精确）
def wait_for_css_transition(self, locator: Locator, timeout: int = 3000):
    locator.wait_for(state="visible")
    end_time = time.time() + timeout / 1000
    while time.time() < end_time:
        is_animating = locator.evaluate(
            "el => getComputedStyle(el).transitionProperty !== 'none'"
            " && getComputedStyle(el).transitionDuration !== '0s'"
        )
        if not is_animating:
            return
        self.page.wait_for_timeout(100)
    raise TimeoutError("Animation did not complete")

# 方案 3：等待元素稳定（位置不变）
def wait_for_stable(self, locator: Locator, stable_ms: int = 500):
    """等待元素位置稳定（不再变化）"""
    last_box = None
    stable_count = 0
    for _ in range(30):
        box = locator.bounding_box()
        if box == last_box:
            stable_count += 1
            if stable_count >= 5:
                return
        else:
            stable_count = 0
            last_box = box
        self.page.wait_for_timeout(100)
```

### 5. 元素状态变更等待

```python
# 等待按钮变为可点击
def wait_for_enabled(self, locator: Locator):
    expect(locator).to_be_enabled(timeout=10000)

# 等待元素消失（loading 结束）
def wait_for_loading_gone(self):
    loading = self.page.locator(".loading, .el-loading-mask, [class*='skeleton']")
    if loading.count() > 0:
        loading.last.wait_for(state="hidden", timeout=15000)

# 等待文本内容变更
def wait_for_text_change(self, locator: Locator, expected_text: str):
    expect(locator).to_have_text(expected_text, timeout=10000)

# 等待 URL 变更
def wait_for_url(self, expected_url: str):
    expect(self.page).to_have_url(expected_url, timeout=10000)
```

### 6. 组合等待策略

```python
def smart_wait(self, locator: Locator, timeout: int = 10000):
    """智能等待：先等加载消失，再等元素可见"""
    self.wait_for_loading_gone()
    locator.wait_for(state="visible", timeout=timeout)
```

## 等待策略选择矩阵

| 场景 | 策略 | 超时建议 |
|------|------|---------|
| 页面跳转 | `wait_until="networkidle"` | 30s |
| 表单提交 | `expect_response` | 15s |
| 列表加载 | response + 元素可见 | 10s |
| 动画完成 | 位置稳定检测 | 3s |
| Loading 消失 | 元素 hidden | 15s |
| 按钮激活 | `to_be_enabled` | 5s |
| Toast 出现 | `to_be_visible` | 5s |
