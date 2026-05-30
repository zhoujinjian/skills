# 测试数据工厂指南

本文件定义测试数据生成规则，底层基于 faker 库实现。

---

## DataFactory 基础模板

```python
# utils/data_factory.py
from dataclasses import dataclass, field
from typing import Optional
from faker import Faker

fake = Faker("zh_CN")


@dataclass
class TestUser:
    """测试用户数据"""
    username: str = ""
    password: str = ""
    email: str = ""
    phone: str = ""
    nickname: str = ""

    def __post_init__(self):
        if not self.username:
            self.username = fake.user_name()
        if not self.password:
            self.password = fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True)
        if not self.email:
            self.email = fake.email()
        if not self.phone:
            self.phone = fake.phone_number()
        if not self.nickname:
            self.nickname = fake.name()


@dataclass
class TestAddress:
    """测试收货地址数据"""
    receiver: str = ""
    phone: str = ""
    province: str = ""
    city: str = ""
    district: str = ""
    detail: str = ""

    def __post_init__(self):
        if not self.receiver:
            self.receiver = fake.name()
        if not self.phone:
            self.phone = fake.phone_number()
        if not self.province:
            self.province = fake.province()
        if not self.city:
            self.city = fake.city()
        if not self.district:
            self.district = fake.district()
        if not self.detail:
            self.detail = fake.street_address()


class DataFactory:
    """测试数据工厂"""

    @staticmethod
    def generate_user(**overrides) -> dict:
        """生成随机用户数据"""
        user = TestUser()
        data = {
            "username": user.username,
            "password": user.password,
            "email": user.email,
            "phone": user.phone,
            "nickname": user.nickname,
        }
        data.update(overrides)
        return data

    @staticmethod
    def generate_address(**overrides) -> dict:
        """生成随机地址数据"""
        addr = TestAddress()
        data = {
            "receiver": addr.receiver,
            "phone": addr.phone,
            "province": addr.province,
            "city": addr.city,
            "district": addr.district,
            "detail": addr.detail,
        }
        data.update(overrides)
        return data

    @staticmethod
    def generate_product_search() -> dict:
        """生成商品搜索数据"""
        keywords = ["手机", "电脑", "耳机", "键盘", "鼠标", "显示器", "笔记本", "平板"]
        import random
        return {
            "keyword": random.choice(keywords),
        }

    @staticmethod
    def batch_users(count: int = 5, **overrides) -> list[dict]:
        """批量生成用户数据"""
        return [DataFactory.generate_user(**overrides) for _ in range(count)]
```

---

## 自定义数据规则

用户可通过提供数据规则文件来自定义生成逻辑。规则文件格式为 YAML：

```yaml
# data_rules.yaml
entities:
  user:
    fields:
      username:
        type: "faker"
        method: "user_name"
        prefix: "test_"         # 前缀
        unique: true            # 确保唯一
      password:
        type: "fixed"
        value: "Test@1234"      # 固定密码
      email:
        type: "faker"
        method: "email"
        domain: "testcompany.com"  # 自定义域名
      phone:
        type: "faker"
        method: "phone_number"
        pattern: "^1[3-9]\\d{9}$"  # 校验正则

  address:
    fields:
      province:
        type: "faker"
        method: "province"
      city:
        type: "faker"
        method: "city"
      detail:
        type: "faker"
        method: "street_address"

  product:
    fields:
      name:
        type: "faker"
        method: "word"
        locale: "zh_CN"
      price:
        type: "range"
        min: 10
        max: 10000
```

---

## 数据生成策略

### 静态数据 vs 动态数据

| 场景 | 策略 | 存放位置 |
|------|------|---------|
| 稳定的测试账号 | 静态数据 | `data/test_data.yaml` |
| 每次运行需唯一的注册数据 | 动态生成 | `DataFactory.generate_user()` |
| 多数据集参数化 | 静态 + 参数化 | `@pytest.mark.parametrize` + YAML |
| 边界值测试 | 精心构造 | `data/test_data.yaml` |

### 数据文件格式

```yaml
# data/test_data.yaml
login:
  valid_user:
    username: "test_user_001"
    password: "Test@1234"
  invalid_users:
    - username: "wrong_user"
      password: "wrong_pass"
      description: "用户名密码均错误"
    - username: ""
      password: "Test@1234"
      description: "用户名为空"
    - username: "test_user_001"
      password: ""
      description: "密码为空"

register:
  valid_user_template:
    username_prefix: "test_user_"
    password: "Test@1234"
    email_domain: "test.com"
    phone_pattern: "138****0001"

product:
  search_keywords:
    - "手机"
    - "电脑"
    - "耳机"
  price_ranges:
    - min: 0
      max: 100
      label: "低价"
    - min: 100
      max: 1000
      label: "中价"
    - min: 1000
      max: 10000
      label: "高价"
```

---

## 在测试中使用数据

### 方式 1：Fixtures 注入

```python
# tests/fixtures/data_fixture.py
import pytest
import yaml
from utils.data_factory import DataFactory


@pytest.fixture
def test_data():
    with open("data/test_data.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def valid_user(test_data) -> dict:
    return test_data["login"]["valid_user"]


@pytest.fixture
def random_user() -> dict:
    return DataFactory.generate_user()
```

### 方式 2：参数化

```python
@pytest.mark.parametrize("user_data", [
    pytest.param({"username": "user1", "password": "Pass@123"}, id="user1"),
    pytest.param({"username": "user2", "password": "Pass@456"}, id="user2"),
])
def test_login_with_different_users(self, page: Page, user_data: dict):
    login_page = LoginPage(page).navigate()
    login_page.fill_username(user_data["username"])
    login_page.fill_password(user_data["password"])
    login_page.click_login()
```

### 方式 3：动态生成

```python
def test_register_new_user(self, page: Page):
    new_user = DataFactory.generate_user()
    register_page = RegisterPage(page).navigate()
    register_page.fill_username(new_user["username"])
    register_page.fill_password(new_user["password"])
    register_page.fill_email(new_user["email"])
    # ...
```
