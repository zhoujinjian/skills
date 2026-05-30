#!/usr/bin/env python3
"""
build_pages_yaml.py — 将 fetch_dom.py 的 JSON 输出 + LLM 解析结果 合并写入 pages.yaml

用法（由 LLM 生成 YAML 内容后调用本脚本合并/格式化）：
    python build_pages_yaml.py <dom_json_path> <llm_yaml_path> [--output <pages_yaml_path>]

也可以直接将 LLM 生成的 YAML 内容通过 stdin 传入：
    cat llm_output.yaml | python build_pages_yaml.py <dom_json_path> - --output pages.yaml

功能：
1. 读取 dom_json（fetch_dom.py 输出）提取元素定位信息
2. 读取 LLM 生成的 YAML（页面对象定义草稿）
3. 用 dom_json 中的真实定位器补全/优先替换 LLM 推断的 xpath/css/locator
4. 校验必填字段，输出最终 pages.yaml
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    print("❌ 缺少依赖：请运行 pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="合并 DOM JSON + LLM YAML 生成 pages.yaml")
    parser.add_argument("dom_json", help="fetch_dom.py 输出的 JSON 文件路径（或 - 表示无 DOM 数据）")
    parser.add_argument("llm_yaml", help="LLM 生成的页面 YAML 路径（或 - 表示 stdin）")
    parser.add_argument("--output", "-o", default="pages.yaml", help="输出文件路径（默认 pages.yaml）")
    return parser.parse_args()


def load_dom_elements(dom_json_path: str) -> list[dict]:
    if dom_json_path == "-" or not Path(dom_json_path).exists():
        return []
    with open(dom_json_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("elements", [])


def best_locator(el: dict) -> dict:
    """根据定位策略优先级返回最优定位器"""
    locator = {}

    if el.get("data_testid"):
        locator["strategy"] = "data-testid"
        locator["value"] = f"[data-testid='{el['data_testid']}']"
        locator["priority"] = 1
    elif el.get("aria_label"):
        locator["strategy"] = "aria-label"
        locator["value"] = f"[aria-label='{el['aria_label']}']"
        locator["priority"] = 2
    elif el.get("id"):
        locator["strategy"] = "id"
        locator["value"] = f"#{el['id']}"
        locator["priority"] = 3
    elif el.get("name"):
        locator["strategy"] = "name"
        locator["value"] = f"[name='{el['name']}']"
        locator["priority"] = 4
    elif el.get("css"):
        locator["strategy"] = "css"
        locator["value"] = el["css"]
        locator["priority"] = 5
    elif el.get("xpath"):
        locator["strategy"] = "xpath"
        locator["value"] = el["xpath"]
        locator["priority"] = 6

    return locator


def enrich_elements(page_elements: list[dict], dom_elements: list[dict]) -> list[dict]:
    """用真实 DOM 元素信息补全 LLM 推断的页面元素"""
    if not dom_elements:
        return page_elements

    # 建立 DOM 元素索引
    index_by_testid = {e["data_testid"]: e for e in dom_elements if e.get("data_testid")}
    index_by_id = {e["id"]: e for e in dom_elements if e.get("id")}
    index_by_name = {e["name"]: e for e in dom_elements if e.get("name")}

    for elem in page_elements:
        key = (
            elem.get("locator", {}).get("value", "")
            or elem.get("name", "")
            or elem.get("element_name", "")
        )

        # 尝试从 DOM 匹配
        matched_dom = None
        for testid_key, dom_el in index_by_testid.items():
            if testid_key in key or key in testid_key:
                matched_dom = dom_el
                break
        if not matched_dom:
            for id_key, dom_el in index_by_id.items():
                if id_key in key or key in id_key:
                    matched_dom = dom_el
                    break
        if not matched_dom:
            for name_key, dom_el in index_by_name.items():
                if name_key in key or key in name_key:
                    matched_dom = dom_el
                    break

        if matched_dom:
            real_locator = best_locator(matched_dom)
            if real_locator and real_locator.get("priority", 99) < elem.get("locator", {}).get("priority", 99):
                elem["locator"] = real_locator
            if not elem.get("element_type") and matched_dom.get("tag"):
                elem["element_type"] = matched_dom["tag"]

    return page_elements


def validate_pages(pages: list[dict]) -> list[str]:
    """校验必填字段，返回警告列表"""
    warnings = []
    required_page_fields = ["page_name", "url", "elements"]
    required_elem_fields = ["element_name", "element_type", "locator"]

    for i, page in enumerate(pages):
        for field in required_page_fields:
            if not page.get(field):
                warnings.append(f"页面[{i}] 缺少必填字段: {field}")
        for j, elem in enumerate(page.get("elements", [])):
            for field in required_elem_fields:
                if not elem.get(field):
                    warnings.append(f"页面[{i}].元素[{j}] 缺少必填字段: {field}")

    return warnings


def main():
    args = parse_args()

    # 读取 LLM YAML
    if args.llm_yaml == "-":
        llm_content = sys.stdin.read()
    else:
        with open(args.llm_yaml, encoding="utf-8") as f:
            llm_content = f.read()

    pages_data = yaml.safe_load(llm_content)
    if not pages_data:
        print("❌ YAML 内容为空或解析失败", file=sys.stderr)
        sys.exit(1)

    pages = pages_data.get("pages", []) if isinstance(pages_data, dict) else pages_data

    # 读取 DOM 元素
    dom_elements = load_dom_elements(args.dom_json)
    print(f"ℹ️  已加载 DOM 元素: {len(dom_elements)} 个", file=sys.stderr)

    # 富化元素定位信息
    for page in pages:
        if page.get("elements"):
            page["elements"] = enrich_elements(page["elements"], dom_elements)

    # 添加元数据
    output_data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "ui-page-parser",
            "dom_source": args.dom_json if args.dom_json != "-" else "none",
            "page_count": len(pages),
        },
        "pages": pages,
    }

    # 校验
    warnings = validate_pages(pages)
    if warnings:
        print(f"⚠️  校验警告 ({len(warnings)} 条):", file=sys.stderr)
        for w in warnings:
            print(f"   - {w}", file=sys.stderr)

    # 写入
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"✅ pages.yaml 已写入: {output_path}", file=sys.stderr)
    print(f"   共 {len(pages)} 个页面定义", file=sys.stderr)


if __name__ == "__main__":
    main()
