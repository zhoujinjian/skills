# 标签索引文件规范 (tag_index.json)

## 文件位置

项目根目录下的 `tag_index.json`，由 `api-test-tagger` 技能生成。

## 数据结构

```json
{
  "version": "1.0",
  "generated_at": "2026-06-10T14:00:00+08:00",
  "project": "shop-lab-api-test",
  "tag_statistics": {
    "total_cases": 232,
    "tag_distribution": {
      "scope:smoke": 45,
      "scope:regression": 180,
      "priority:P0": 30,
      "priority:P1": 80,
      "priority:P2": 100,
      "priority:P3": 22,
      "module:auth": 25,
      "module:order": 40,
      "module:product": 35
    }
  },
  "cases": [
    {
      "case_id": "testcases/test_auth.py::TestLogin::test_login_success",
      "file": "testcases/test_auth.py",
      "class": "TestLogin",
      "method": "test_login_success",
      "tags": [
        "scope:smoke",
        "scope:regression",
        "priority:P0",
        "module:auth",
        "scene:positive",
        "run:ci"
      ]
    },
    {
      "case_id": "testcases/test_auth.py::TestLogin::test_login_password_error",
      "file": "testcases/test_auth.py",
      "class": "TestLogin",
      "method": "test_login_password_error",
      "tags": [
        "scope:regression",
        "priority:P1",
        "module:auth",
        "scene:negative"
      ]
    }
  ]
}
```

## 标签命名规范

### 五维标签体系

| 维度 | 前缀 | 可选值 | 示例 |
|------|------|--------|------|
| 优先级 | `priority:` | P0, P1, P2, P3 | `priority:P0` |
| 模块 | `module:` | 项目模块名 | `module:auth` |
| 场景 | `scene:` | positive, negative, boundary, business, security | `scene:positive` |
| 执行策略 | `run:` | ci, nightly, manual, skip | `run:ci` |
| 环境 | `env:` | dev-only, test-only, pre-only, all | `env:all` |
| 范围 | `scope:` | smoke, regression | `scope:smoke` |
| 状态 | (无前缀) | flaky, unstable, stable | `flaky` |

### 筛选逻辑

- **scope** 过滤：匹配 `scope:{value}` 标签
- **module** 过滤：匹配 `module:{value}` 标签
- **priority** 过滤：匹配 `priority:{value}` 标签
- **tag** 过滤：精确匹配任意标签值
- **exclude-tag** 过滤：排除包含指定标签的用例

### 多条件组合

多筛选条件之间为 **AND** 关系：
- `--scope smoke --module auth --priority P0` → 必须同时满足 scope:smoke AND module:auth AND priority:P0

同一维度多值为 **OR** 关系：
- `--module auth,order` → module:auth OR module:order
- `--priority P0,P1` → priority:P0 OR priority:P1

## 无标签索引时的回退策略

当 `tag_index.json` 不存在时：
1. 按 `--module` 匹配文件路径（如 `test_auth.py` 匹配 `module:auth`）
2. 按测试方法名关键字推断场景（如 `test_*_success` → 正向场景）
3. 打印 WARNING 提示建议先运行 `api-test-tagger`
