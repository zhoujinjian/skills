"""
接口测试数据清理脚本
- 数据库清理：按模块清理测试产生的临时数据
- Redis 缓存清理：清理验证码、Token 等临时缓存
- 本地文件清理：清理日志、报告、临时文件
- 白名单保护：admin 账号、正式数据永久保留
- 生产环境强制拦截
"""
import os
import sys
import time
import json
import glob
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("testdata_cleaner")


# ── 白名单配置 ──────────────────────────────────────────────

PROTECTED_USERNAMES = ["admin"]
TEST_USER_PATTERNS = [
    "test", "测试", "logout_", "pwdtest_", "_init_", "temp_",
    "newuser_", "bypass_", "duplicate_user", "nonexistent",
]
TEST_PRODUCT_PATTERNS = ["测试商品", "test_"]
TEST_CATEGORY_PATTERNS = ["测试分类"]
TEST_ADDRESS_PATTERNS = ["测试收货人", "张三"]

REDIS_CLEAN_PATTERNS = ["captcha:*"]
FILE_CLEAN_DIRS = ["logs", "allure-results", ".pytest_cache"]
FILE_MAX_AGE_HOURS = 24


# ── 清理报告 ────────────────────────────────────────────────

class CleanReport:
    """清理报告收集器"""

    def __init__(self, env, auto_trigger=False):
        self.env = env
        self.auto_trigger = auto_trigger
        self.start_time = time.time()
        self.results = []
        self.status = "success"

    def add(self, module, target, count, status, detail=""):
        self.results.append({
            "module": module,
            "target": target,
            "count": count,
            "status": status,
            "detail": detail,
        })
        if status == "failed":
            self.status = "success_with_errors" if self.status == "success" else self.status

    def mark_failed(self):
        self.status = "failed"

    def total_count(self):
        return sum(r["count"] for r in self.results)

    def format_report(self):
        elapsed = round(time.time() - self.start_time, 2)
        lines = [
            "=== 测试数据清理报告 ===",
            f"环境: {self.env}",
            f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"耗时: {elapsed}s",
            f"白名单保护: 启用 (admin 账号已保护)",
            "",
        ]

        db_results = [r for r in self.results if r["target"] == "db"]
        redis_results = [r for r in self.results if r["target"] == "redis"]
        file_results = [r for r in self.results if r["target"] == "file"]

        if db_results:
            lines.append("【数据库清理】")
            for r in db_results:
                detail = f", 备注: {r['detail']}" if r["detail"] else ""
                lines.append(f"  - {r['module']}: 清理 {r['count']} 条, 状态: {r['status']}{detail}")
            lines.append("")

        if redis_results:
            lines.append("【缓存清理】")
            for r in redis_results:
                lines.append(f"  - {r['module']}: 清理 {r['count']} 项, 状态: {r['status']}")
            lines.append("")

        if file_results:
            lines.append("【文件清理】")
            for r in file_results:
                lines.append(f"  - {r['module']}: 清理 {r['count']} 个, 状态: {r['status']}")
            lines.append("")

        lines.extend([
            "【总计】",
            f"清理数据条数: {self.total_count()}",
            f"执行状态: {self.status}",
        ])
        return "\n".join(lines)

    def to_json(self):
        elapsed = round(time.time() - self.start_time, 2)
        return {
            "status": self.status,
            "env": self.env,
            "elapsed_seconds": elapsed,
            "total_cleaned": self.total_count(),
            "details": self.results,
            "timestamp": datetime.now().isoformat(),
            "auto_trigger": self.auto_trigger,
        }


# ── 数据库清理 ──────────────────────────────────────────────

def _build_test_user_where():
    """构建测试用户 WHERE 条件"""
    conditions = []
    for p in TEST_USER_PATTERNS:
        conditions.append(f"username LIKE '%{p}%'")
    return " OR ".join(conditions)


def _clean_db_users(cursor, report):
    """清理测试用户及其关联数据"""
    where = _build_test_user_where()
    protect = " AND username NOT IN ({})".format(
        ",".join(f"'{u}'" for u in PROTECTED_USERNAMES)
    )

    # 查询待清理用户 ID
    cursor.execute(f"SELECT id FROM user WHERE ({where}){protect}")
    user_ids = [row[0] for row in cursor.fetchall()]

    if not user_ids:
        report.add("用户表", "db", 0, "success")
        return

    count = len(user_ids)
    id_list = ",".join(str(uid) for uid in user_ids)

    # 按依赖顺序清理关联数据
    for table, col in [
        ("cart", "user_id"),
        ("order_item", "order_id"),
    ]:
        try:
            # 先清理订单项（通过订单关联用户）
            pass
        except Exception:
            pass

    # 清理购物车
    try:
        cursor.execute(f"DELETE FROM cart WHERE user_id IN ({id_list})")
        logger.info(f"清理购物车: {cursor.rowcount} 条")
    except Exception as e:
        logger.warning(f"清理购物车失败: {e}")

    # 清理订单
    try:
        cursor.execute(f"DELETE FROM `order` WHERE user_id IN ({id_list})")
        logger.info(f"清理订单: {cursor.rowcount} 条")
    except Exception as e:
        logger.warning(f"清理订单失败: {e}")

    # 清理地址
    try:
        cursor.execute(f"DELETE FROM address WHERE user_id IN ({id_list})")
        logger.info(f"清理地址: {cursor.rowcount} 条")
    except Exception as e:
        logger.warning(f"清理地址失败: {e}")

    # 清理用户
    try:
        cursor.execute(f"DELETE FROM user WHERE id IN ({id_list}){protect}")
        actual = cursor.rowcount
        report.add("用户表", "db", actual, "success")
        logger.info(f"清理用户: {actual} 条")
    except Exception as e:
        report.add("用户表", "db", 0, "failed", str(e))


def _clean_db_products(cursor, report):
    """清理测试商品"""
    conditions = " OR ".join(f"name LIKE '%{p}%'" for p in TEST_PRODUCT_PATTERNS)
    try:
        cursor.execute(f"DELETE FROM product WHERE ({conditions})")
        count = cursor.rowcount
        report.add("商品表", "db", count, "success")
        logger.info(f"清理测试商品: {count} 条")
    except Exception as e:
        report.add("商品表", "db", 0, "failed", str(e))


def _clean_db_categories(cursor, report):
    """清理测试分类"""
    conditions = " OR ".join(f"name LIKE '%{p}%'" for p in TEST_CATEGORY_PATTERNS)
    try:
        cursor.execute(f"DELETE FROM category WHERE ({conditions})")
        count = cursor.rowcount
        report.add("分类表", "db", count, "success")
        logger.info(f"清理测试分类: {count} 条")
    except Exception as e:
        report.add("分类表", "db", 0, "failed", str(e))


def _clean_db_captcha_records(cursor, report):
    """清理验证码记录"""
    try:
        cursor.execute("DELETE FROM captcha_record")
        count = cursor.rowcount
        report.add("验证码记录", "db", count, "success")
        logger.info(f"清理验证码记录: {count} 条")
    except Exception as e:
        report.add("验证码记录", "db", 0, "failed", str(e))


def clean_database(db_config, report, clean_scope="all"):
    """执行数据库清理"""
    try:
        import pymysql
        conn = pymysql.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["username"],
            password=db_config["password"],
            database=db_config["name"],
            charset="utf8mb4",
            autocommit=True,
        )
        cursor = conn.cursor()
        logger.info("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        report.add("数据库连接", "db", 0, "failed", str(e))
        report.mark_failed()
        return

    try:
        if clean_scope in ("all", "user"):
            _clean_db_users(cursor, report)
        if clean_scope in ("all",):
            _clean_db_products(cursor, report)
            _clean_db_categories(cursor, report)
        if clean_scope in ("all",):
            _clean_db_captcha_records(cursor, report)
    finally:
        conn.close()
        logger.info("数据库连接已关闭")


# ── Redis 缓存清理 ─────────────────────────────────────────

def clean_redis(redis_config, report):
    """执行 Redis 缓存清理"""
    try:
        import redis
        r = redis.Redis(
            host=redis_config.get("host", "localhost"),
            port=redis_config.get("port", 6379),
            db=redis_config.get("db", 0),
            decode_responses=True,
        )
        r.ping()
        logger.info("Redis 连接成功")
    except Exception as e:
        logger.error(f"Redis 连接失败: {e}")
        report.add("Redis缓存", "redis", 0, "failed", str(e))
        return

    total = 0
    for pattern in REDIS_CLEAN_PATTERNS:
        try:
            keys = r.keys(pattern)
            if keys:
                deleted = r.delete(*keys)
                total += deleted
                logger.info(f"清理 {pattern}: {deleted} 项")
        except Exception as e:
            logger.warning(f"清理 {pattern} 失败: {e}")

    report.add("验证码缓存", "redis", total, "success")


# ── 本地文件清理 ────────────────────────────────────────────

def clean_files(project_dir, report, keep_debug_data=False):
    """执行本地文件清理"""
    total = 0
    now = time.time()
    cutoff = now - (FILE_MAX_AGE_HOURS * 3600)

    for dir_name in FILE_CLEAN_DIRS:
        dir_path = os.path.join(project_dir, dir_name)
        if not os.path.exists(dir_path):
            continue

        count = 0
        for fpath in glob.glob(os.path.join(dir_path, "**"), recursive=True):
            if os.path.isfile(fpath):
                try:
                    mtime = os.path.getmtime(fpath)
                    if keep_debug_data and (now - mtime) < 3600:
                        continue
                    if mtime < cutoff or not keep_debug_data:
                        os.remove(fpath)
                        count += 1
                except Exception as e:
                    logger.warning(f"删除文件失败 {fpath}: {e}")

        report.add(dir_name, "file", count, "success")
        total += count
        logger.info(f"清理 {dir_name}/: {count} 个文件")

    return total


# ── 主入口 ──────────────────────────────────────────────────

def run_clean(
    env_type="test",
    clean_scope="all",
    clean_target="all",
    keep_debug_data=False,
    auto_trigger=False,
    protect_white_list=True,
    project_dir=None,
):
    """
    执行测试数据清理

    Args:
        env_type: 执行环境
        clean_scope: 清理范围
        clean_target: 清理目标
        keep_debug_data: 保留调试数据
        auto_trigger: 是否自动触发
        protect_white_list: 启用白名单保护
        project_dir: 项目目录

    Returns:
        CleanReport 实例
    """
    # Step 1: 环境校验
    if env_type == "prod":
        logger.error("【安全拦截】生产环境禁止执行数据清理操作！")
        report = CleanReport(env_type, auto_trigger)
        report.mark_failed()
        report.add("安全拦截", "db", 0, "failed", "生产环境禁止清理")
        return report

    logger.info(f"开始清理测试数据 | 环境: {env_type} | 范围: {clean_scope} | 目标: {clean_target}")

    report = CleanReport(env_type, auto_trigger)

    # Step 2: 加载配置
    project_dir = project_dir or os.getcwd()
    config_dir = os.path.join(project_dir, "config")
    config_file = os.path.join(config_dir, f"{env_type}.yaml")

    db_config = {}
    redis_config = {}
    if os.path.exists(config_file):
        try:
            import yaml
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            db_config = cfg.get("database", {})
            redis_config = cfg.get("redis", {})
        except Exception as e:
            logger.warning(f"加载配置失败: {e}")

    # Step 3-5: 分层清理
    if clean_target in ("db", "all") and db_config:
        clean_database(db_config, report, clean_scope)

    if clean_target in ("redis", "all"):
        clean_redis(redis_config, report)

    if clean_target in ("file", "all"):
        clean_files(project_dir, report, keep_debug_data)

    # Step 6: 输出报告
    logger.info(report.format_report())
    return report


if __name__ == "__main__":
    params = {}
    if len(sys.argv) > 1:
        try:
            params = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            print("用法: python clean_testdata.py '{\"env_type\":\"test\",\"clean_scope\":\"all\"}'")
            sys.exit(1)

    report = run_clean(**params)
    print(report.format_report())
    if report.status == "failed":
        sys.exit(1)
