#!/usr/bin/env python3
"""
API Schema Parser - 接口定义解析器

将不同来源、不同格式的接口定义数据统一转换为结构化接口数据。
支持输入：Swagger 2.0 / OpenAPI 3.x / Postman / HAR / YApi / Apifox / 纯文本
输出格式：JSON / YAML

用法：
    python3 schema_parser.py <input_file> [--format json|yaml] [--output <path>] [--type <source_type>]
"""

import argparse
import copy
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

SCHEMA_VERSION = "1.0.0"
MAX_APIS_PER_SHARD = 100

# ─────────────────────── 类型映射表 ───────────────────────

TYPE_MAP = {
    # Swagger 2.0 / OpenAPI 3.x 基本类型
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
    "file": "file",
    # YApi 类型映射
    "int": "integer",
    "long": "integer",
    "float": "number",
    "double": "number",
    "date": "string",
    "datetime": "string",
    "text": "string",
    "email": "string",
    "password": "string",
    "url": "string",
    "uri": "string",
    "uuid": "string",
}

FORMAT_MAP = {
    "date-time": "date-time",
    "date": "date",
    "email": "email",
    "uri": "uri",
    "url": "uri",
    "uuid": "uuid",
    "int32": "int32",
    "int64": "int64",
    "float": "float",
    "double": "double",
    "binary": "binary",
    "password": "password",
    "byte": "byte",
}


# ─────────────────────── 自动识别输入源类型 ───────────────────────

def detect_source_type(file_path: str) -> str:
    """自动识别输入源类型"""
    ext = Path(file_path).suffix.lower()

    # 先尝试按扩展名快速判断
    if ext == ".har":
        return "har"

    # 读取文件内容
    content = _read_file_content(file_path)
    if content is None:
        return "text"

    # 尝试解析 JSON/YAML
    data = _parse_content(content)
    if data is None:
        return "text"

    # 根据内容结构判断
    if isinstance(data, dict):
        if "swagger" in data:
            return "swagger"
        if "openapi" in data:
            return "openapi"
        if "log" in data and isinstance(data.get("log"), dict) and "entries" in data.get("log", {}):
            return "har"
        if "info" in data and "item" in data:
            return "postman"
        if "_postman_id" in data.get("info", {}):
            return "postman"

    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        if isinstance(first, dict):
            if "path" in first and "method" in first:
                # 区分 YApi 和 Apifox
                if "req_body_type" in first or "req_query" in first:
                    return "yapi"
                if "apiDetail" in first or "api" in first:
                    return "apifox"
                # 可能是简化格式，尝试 YApi
                return "yapi"

    return "text"


def _read_file_content(file_path: str) -> Optional[str]:
    """读取文件内容"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="gbk") as f:
                return f.read()
        except Exception:
            return None
    except Exception:
        return None


def _parse_content(content: str) -> Any:
    """解析 JSON/YAML 内容"""
    content = content.strip()
    # 尝试 JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 尝试 YAML
    if YAML_AVAILABLE:
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError:
            pass
    return None


# ─────────────────────── Swagger 2.0 解析 ───────────────────────

def parse_swagger(data: dict) -> dict:
    """解析 Swagger 2.0 文件"""
    definitions = data.get("definitions", {})
    base_path = data.get("basePath", "")
    paths = data.get("paths", {})
    apis = []

    for path, path_item in paths.items():
        for method in ["get", "post", "put", "delete", "patch", "head", "options"]:
            if method not in path_item:
                continue
            operation = path_item[method]
            full_path = base_path.rstrip("/") + "/" + path.lstrip("/") if base_path else path

            api_id = f"{method.upper()}_{full_path}"
            name = operation.get("operationId", operation.get("summary", f"{method.upper()} {full_path}"))
            tags = operation.get("tags", [])
            module = tags[0] if tags else _infer_module(full_path)

            # 解析参数
            parameters = _parse_swagger_params(operation.get("parameters", []), definitions, full_path, data)

            # 解析响应
            responses = _parse_swagger_responses(operation.get("responses", {}), definitions, data)

            # 识别业务规则
            business_rules = _extract_business_rules(
                operation.get("description", ""),
                operation.get("summary", ""),
                api_id
            )

            api_def = {
                "api_id": api_id,
                "name": name,
                "path": full_path,
                "method": method.upper(),
                "module": module,
                "description": operation.get("description", ""),
                "deprecated": operation.get("deprecated", False),
                "tags": tags,
                "parameters": parameters,
                "responses": responses,
                "business_rules": business_rules,
            }
            apis.append(api_def)

    # 提取全局安全规则
    global_rules = _extract_swagger_global_rules(data)

    return _build_output(apis, "swagger", global_rules=global_rules)


def _parse_swagger_params(params: list, definitions: dict, path: str, root_doc: dict = None) -> dict:
    """解析 Swagger 2.0 参数"""
    path_params = []
    query_params = []
    header_params = []
    body_params = []

    for param in params:
        # 处理 $ref
        if "$ref" in param:
            param = _resolve_ref(param["$ref"], definitions, set(), root_doc)

        param_in = param.get("in", "query")
        resolved = _resolve_param(param, definitions, root_doc)

        if param_in == "path":
            path_params.append(resolved)
        elif param_in == "query":
            query_params.append(resolved)
        elif param_in == "header":
            header_params.append(resolved)
        elif param_in in ("body", "formData"):
            body_params.append(resolved)

    return {
        "path_params": path_params,
        "query_params": query_params,
        "header_params": header_params,
        "body_params": body_params,
    }


def _resolve_param(param: dict, definitions: dict, root_doc: dict = None) -> dict:
    """解析单个参数"""
    result = {
        "name": param.get("name", ""),
        "in": param.get("in", "query"),
        "required": param.get("required", param.get("in") == "path"),
        "type": _map_type(param.get("type", param.get("schema", {}).get("type", "string"))),
    }

    # 可选字段
    for field in ["format", "description", "pattern"]:
        if field in param:
            result[field] = param[field]
        elif "schema" in param and field in param["schema"]:
            result[field] = param["schema"][field]

    if "default" in param:
        result["default"] = param["default"]
    elif "schema" in param and "default" in param["schema"]:
        result["default"] = param["schema"]["default"]

    if "enum" in param:
        result["enum"] = param["enum"]
    elif "schema" in param and "enum" in param["schema"]:
        result["enum"] = param["schema"]["enum"]

    for field in ["minLength", "maxLength", "minimum", "maximum"]:
        if field in param:
            result[field] = param[field]
        elif "schema" in param and field in param["schema"]:
            result[field] = param["schema"][field]

    if "example" in param:
        result["example"] = param["example"]
    elif "x-example" in param:
        result["example"] = param["x-example"]

    # Body 参数的 schema 展开
    if "schema" in param:
        schema = param["schema"]
        if "$ref" in schema:
            resolved_schema = _resolve_ref(schema["$ref"], definitions, set(), root_doc)
            result.update(_expand_schema(resolved_schema, definitions, root_doc=root_doc))
        elif schema.get("type") == "object" and "properties" in schema:
            result["type"] = "object"
            result["properties"] = _expand_properties(schema["properties"], definitions, root_doc=root_doc)
        elif schema.get("type") == "array" and "items" in schema:
            result["type"] = "array"
            result["items"] = _resolve_schema_item(schema["items"], definitions, root_doc=root_doc)

    return result


def _expand_schema(schema: dict, definitions: dict, visited: set = None, root_doc: dict = None) -> dict:
    """展开 Schema 定义"""
    if visited is None:
        visited = set()

    result = {}
    schema_type = schema.get("type", "object")
    result["type"] = _map_type(schema_type)

    for field in ["format", "description", "pattern", "default"]:
        if field in schema:
            result[field] = schema[field]

    if "enum" in schema:
        result["enum"] = schema["enum"]

    for field in ["minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems"]:
        if field in schema:
            result[field] = schema[field]

    if schema_type == "object" and "properties" in schema:
        result["properties"] = _expand_properties(schema["properties"], definitions, visited, root_doc)

    if schema_type == "array" and "items" in schema:
        result["items"] = _resolve_schema_item(schema["items"], definitions, visited, root_doc)

    # allOf 合并
    if "allOf" in schema:
        merged = _merge_all_of(schema["allOf"], definitions, visited, root_doc)
        result.update(merged)

    return result


def _expand_properties(properties: dict, definitions: dict, visited: set = None, root_doc: dict = None) -> list:
    """展开对象属性"""
    if visited is None:
        visited = set()

    result = []
    for prop_name, prop_schema in properties.items():
        if "$ref" in prop_schema:
            resolved = _resolve_ref(prop_schema["$ref"], definitions, visited, root_doc)
            prop = _expand_schema(resolved, definitions, visited, root_doc)
        else:
            prop = _expand_schema(prop_schema, definitions, visited, root_doc)

        prop["name"] = prop_name
        prop["required"] = False  # 默认选填，由 required 列表覆盖
        result.append(prop)

    return result


def _resolve_schema_item(items: dict, definitions: dict, visited: set = None, root_doc: dict = None) -> dict:
    """解析数组 items"""
    if visited is None:
        visited = set()

    if "$ref" in items:
        resolved = _resolve_ref(items["$ref"], definitions, visited, root_doc)
        return _expand_schema(resolved, definitions, visited, root_doc)
    return _expand_schema(items, definitions, visited, root_doc)


def _merge_all_of(all_of: list, definitions: dict, visited: set = None, root_doc: dict = None) -> dict:
    """合并 allOf 中的 schemas"""
    if visited is None:
        visited = set()

    merged = {"type": "object", "properties": []}
    for schema in all_of:
        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], definitions, visited, root_doc)
        expanded = _expand_schema(schema, definitions, visited, root_doc)
        if "properties" in expanded:
            merged["properties"].extend(expanded["properties"])
    return merged


def _resolve_ref(ref: str, definitions: dict, visited: set, root_doc: dict = None) -> dict:
    """解析 $ref 引用

    Args:
        ref: 引用路径，如 '#/components/schemas/User' 或 '#/definitions/User'
        definitions: 向后兼容的 definitions 字典（仅 Swagger 2.0 直接使用）
        visited: 已访问引用集合，防循环
        root_doc: 完整的文档根结构，用于正确解析 #/components/schemas/ 路径
    """
    if visited is None:
        visited = set()

    # 防止循环引用
    if ref in visited:
        return {"type": "object", "description": f"[循环引用] {ref}"}
    visited.add(ref)

    # 优先从 root_doc 解析完整引用路径
    lookup_root = root_doc if root_doc else {"definitions": definitions}

    # 解析引用路径: #/components/schemas/User → ['components', 'schemas', 'User']
    parts = ref.lstrip("#/").split("/")
    current = lookup_root
    try:
        for part in parts:
            current = current[part]
        if isinstance(current, dict):
            # 递归解析嵌套 $ref
            if "$ref" in current:
                return _resolve_ref(current["$ref"], definitions, visited, root_doc)
            return copy.deepcopy(current)
    except (KeyError, TypeError):
        pass

    # 回退：尝试从 definitions 直接查找最后一部分
    schema_name = parts[-1] if parts else ""
    if schema_name in definitions:
        found = definitions[schema_name]
        if isinstance(found, dict):
            if "$ref" in found:
                return _resolve_ref(found["$ref"], definitions, visited, root_doc)
            return copy.deepcopy(found)

    return {"type": "object", "description": f"[未找到引用] {ref}"}


def _parse_swagger_responses(responses: dict, definitions: dict, root_doc: dict = None) -> dict:
    """解析 Swagger 2.0 响应"""
    success = None
    errors = []

    for status_code, response_def in responses.items():
        if "$ref" in response_def:
            response_def = _resolve_ref(response_def["$ref"], definitions, set(), root_doc)

        resp = {
            "status_code": int(status_code) if status_code != "default" else 0,
            "description": response_def.get("description", ""),
        }

        schema = response_def.get("schema")
        if schema:
            if "$ref" in schema:
                resolved = _resolve_ref(schema["$ref"], definitions, set(), root_doc)
                resp["schema"] = _flatten_response_schema(resolved, definitions, root_doc=root_doc)
            else:
                resp["schema"] = _flatten_response_schema(schema, definitions, root_doc=root_doc)

        if "examples" in response_def:
            json_example = response_def["examples"].get("application/json")
            if json_example:
                resp["example"] = json_example

        if status_code in ("200", "201", "202", "204") or status_code == "default":
            if success is None:
                success = resp
        else:
            errors.append(resp)

    if success is None:
        success = {"status_code": 200, "description": "成功（未在文档中定义响应结构）"}

    return {"success": success, "errors": errors}


def _flatten_response_schema(schema: dict, definitions: dict, prefix: str = "", visited: set = None, root_doc: dict = None) -> list:
    """将嵌套的响应 Schema 展平为字段列表"""
    if visited is None:
        visited = set()

    fields = []
    schema_type = schema.get("type", "object")

    if schema_type == "object" and "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            field_path = f"{prefix}.{prop_name}" if prefix else prop_name

            if "$ref" in prop_schema:
                prop_schema = _resolve_ref(prop_schema["$ref"], definitions, visited, root_doc)

            prop_type = _map_type(prop_schema.get("type", "string"))
            field = {
                "field_path": field_path,
                "type": prop_type,
                "description": prop_schema.get("description", ""),
            }

            if "enum" in prop_schema:
                field["enum"] = prop_schema["enum"]
            if "example" in prop_schema:
                field["example"] = prop_schema["example"]

            if prop_type == "object" and "properties" in prop_schema:
                field["nested_fields"] = _flatten_response_schema(prop_schema, definitions, field_path, visited, root_doc)
            elif prop_type == "array" and "items" in prop_schema:
                items = prop_schema["items"]
                if "$ref" in items:
                    items = _resolve_ref(items["$ref"], definitions, visited, root_doc)
                field["nested_fields"] = _flatten_response_schema(
                    {**items, "type": items.get("type", "object")},
                    definitions, f"{field_path}[]", visited, root_doc
                )

            fields.append(field)
    elif schema_type == "array" and "items" in schema:
        items = schema["items"]
        if "$ref" in items:
            items = _resolve_ref(items["$ref"], definitions, visited, root_doc)
        fields.extend(_flatten_response_schema(
            {**items, "type": items.get("type", "object")},
            definitions, f"{prefix}[]", visited, root_doc
        ))
    else:
        field_path = prefix if prefix else "value"
        fields.append({
            "field_path": field_path,
            "type": _map_type(schema_type),
            "description": schema.get("description", ""),
        })

    return fields


def _extract_swagger_global_rules(data: dict) -> dict:
    """提取 Swagger 全局规则"""
    global_rules = {}

    # 鉴权规则
    security_definitions = data.get("securityDefinitions", {})
    if security_definitions:
        for name, scheme in security_definitions.items():
            auth_type = scheme.get("type", "")
            if auth_type == "apiKey":
                global_rules["authentication"] = {
                    "type": "APIKey",
                    "header": scheme.get("name", ""),
                    "description": scheme.get("description", f"API Key: {name}"),
                }
            elif auth_type == "oauth2":
                global_rules["authentication"] = {
                    "type": "OAuth2",
                    "description": scheme.get("description", f"OAuth2: {name}"),
                }
            elif auth_type == "basic":
                global_rules["authentication"] = {
                    "type": "Basic",
                    "header": "Authorization",
                    "description": scheme.get("description", "HTTP Basic 认证"),
                }
            break  # 取第一个安全定义作为默认

    # 全局限流
    for ext_key in ["x-rate-limit", "x-ratelimit", "x-throttling"]:
        if ext_key in data:
            global_rules["rate_limiting"] = {
                "default": str(data[ext_key]),
                "description": f"来自 {ext_key} 扩展字段",
            }
            break

    return global_rules


# ─────────────────────── OpenAPI 3.x 解析 ───────────────────────

def parse_openapi(data: dict) -> dict:
    """解析 OpenAPI 3.x 文件"""
    components = data.get("components", {})
    schemas = components.get("schemas", {})
    security_schemes = components.get("securitySchemes", {})
    paths = data.get("paths", {})
    apis = []

    for path, path_item in paths.items():
        for method in ["get", "post", "put", "delete", "patch", "head", "options"]:
            if method not in path_item:
                continue
            operation = path_item[method]

            api_id = f"{method.upper()}_{path}"
            name = operation.get("operationId", operation.get("summary", f"{method.upper()} {path}"))
            tags = operation.get("tags", [])
            module = tags[0] if tags else _infer_module(path)

            # 解析参数（Path/Query/Header）
            parameters = _parse_openapi_params(operation.get("parameters", []), schemas, path, data)

            # 解析 requestBody
            request_body = operation.get("requestBody")
            if request_body:
                body_params = _parse_openapi_request_body(request_body, schemas, data)
                parameters["body_params"] = body_params

            # 解析响应
            responses = _parse_openapi_responses(operation.get("responses", {}), schemas, data)

            # 识别业务规则
            business_rules = _extract_business_rules(
                operation.get("description", ""),
                operation.get("summary", ""),
                api_id
            )

            api_def = {
                "api_id": api_id,
                "name": name,
                "path": path,
                "method": method.upper(),
                "module": module,
                "description": operation.get("description", ""),
                "deprecated": operation.get("deprecated", False),
                "tags": tags,
                "parameters": parameters,
                "responses": responses,
                "business_rules": business_rules,
            }
            apis.append(api_def)

    # 提取全局规则
    global_rules = _extract_openapi_global_rules(data, security_schemes)

    return _build_output(apis, "openapi", global_rules=global_rules)


def _parse_openapi_params(params: list, schemas: dict, path: str, root_doc: dict = None) -> dict:
    """解析 OpenAPI 3.x Path/Query/Header 参数"""
    path_params = []
    query_params = []
    header_params = []

    for param in params:
        if "$ref" in param:
            param = _resolve_ref(param["$ref"], schemas, set(), root_doc)

        param_in = param.get("in", "query")
        schema = param.get("schema", {})

        resolved = {
            "name": param.get("name", ""),
            "in": param_in,
            "required": param.get("required", param_in == "path"),
            "type": _map_type(schema.get("type", "string")),
        }

        for field in ["format", "description", "pattern"]:
            if field in schema:
                resolved[field] = schema[field]

        if "default" in schema:
            resolved["default"] = schema["default"]
        if "enum" in schema:
            resolved["enum"] = schema["enum"]
        for field in ["minLength", "maxLength", "minimum", "maximum"]:
            if field in schema:
                resolved[field] = schema[field]
        if "example" in param:
            resolved["example"] = param["example"]
        elif "example" in schema:
            resolved["example"] = schema["example"]

        if param_in == "path":
            path_params.append(resolved)
        elif param_in == "query":
            query_params.append(resolved)
        elif param_in == "header":
            header_params.append(resolved)

    return {
        "path_params": path_params,
        "query_params": query_params,
        "header_params": header_params,
        "body_params": [],
    }


def _parse_openapi_request_body(request_body: dict, schemas: dict, root_doc: dict = None) -> list:
    """解析 OpenAPI 3.x requestBody"""
    body_params = []
    content = request_body.get("content", {})

    # 优先 application/json
    media_type = None
    for mt in ["application/json", "multipart/form-data", "application/x-www-form-urlencoded"]:
        if mt in content:
            media_type = mt
            break

    if media_type is None and content:
        media_type = list(content.keys())[0]

    if media_type and media_type in content:
        schema = content[media_type].get("schema", {})
        required_fields = schema.get("required", [])

        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], schemas, set(), root_doc)

        if schema.get("type") == "object" and "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                if "$ref" in prop_schema:
                    prop_schema = _resolve_ref(prop_schema["$ref"], schemas, set(), root_doc)

                prop = _expand_schema(prop_schema, schemas, root_doc=root_doc)
                prop["name"] = prop_name
                prop["in"] = "body"
                prop["required"] = prop_name in required_fields

                if media_type == "multipart/form-data" and prop.get("type") == "string" and prop.get("format") == "binary":
                    prop["type"] = "file"

                body_params.append(prop)
        elif schema.get("type") == "array":
            prop = _expand_schema(schema, schemas, root_doc=root_doc)
            prop["name"] = "body"
            prop["in"] = "body"
            prop["required"] = request_body.get("required", False)
            body_params.append(prop)
        else:
            # 简单类型
            body_params.append({
                "name": "body",
                "in": "body",
                "required": request_body.get("required", False),
                "type": _map_type(schema.get("type", "string")),
                "description": schema.get("description", ""),
            })

    return body_params


def _parse_openapi_responses(responses: dict, schemas: dict, root_doc: dict = None) -> dict:
    """解析 OpenAPI 3.x 响应"""
    success = None
    errors = []

    for status_code, response_def in responses.items():
        resp = {
            "status_code": int(status_code) if status_code != "default" else 0,
            "description": response_def.get("description", ""),
        }

        content = response_def.get("content", {})
        if "application/json" in content:
            schema = content["application/json"].get("schema", {})
            if "$ref" in schema:
                schema = _resolve_ref(schema["$ref"], schemas, set(), root_doc)
            resp["schema"] = _flatten_response_schema(schema, schemas, prefix="", visited=None, root_doc=root_doc)
            if "example" in content["application/json"]:
                resp["example"] = content["application/json"]["example"]

        if status_code in ("200", "201", "202", "204") or status_code == "default":
            if success is None:
                success = resp
        else:
            errors.append(resp)

    if success is None:
        success = {"status_code": 200, "description": "成功（未在文档中定义响应结构）"}

    return {"success": success, "errors": errors}


def _extract_openapi_global_rules(data: dict, security_schemes: dict) -> dict:
    """提取 OpenAPI 3.x 全局规则"""
    global_rules = {}

    if security_schemes:
        for name, scheme in security_schemes.items():
            auth_type = scheme.get("type", "")
            if auth_type == "http":
                scheme_type = scheme.get("scheme", "").capitalize()
                global_rules["authentication"] = {
                    "type": scheme_type,
                    "header": "Authorization",
                    "description": scheme.get("description", f"HTTP {scheme_type} 认证"),
                }
            elif auth_type == "apiKey":
                global_rules["authentication"] = {
                    "type": "APIKey",
                    "header": scheme.get("name", ""),
                    "description": scheme.get("description", f"API Key: {name}"),
                }
            elif auth_type == "oauth2":
                global_rules["authentication"] = {
                    "type": "OAuth2",
                    "description": scheme.get("description", f"OAuth2: {name}"),
                }
            break

    for ext_key in ["x-rate-limit", "x-ratelimit", "x-throttling"]:
        if ext_key in data:
            global_rules["rate_limiting"] = {
                "default": str(data[ext_key]),
                "description": f"来自 {ext_key} 扩展字段",
            }
            break

    return global_rules


# ─────────────────────── Postman 解析 ───────────────────────

def parse_postman(data: dict) -> dict:
    """解析 Postman 集合"""
    apis = []
    _parse_postman_items(data.get("item", []), apis, "")

    return _build_output(apis, "postman")


def _parse_postman_items(items: list, apis: list, parent_module: str):
    """递归解析 Postman item"""
    for item in items:
        if "item" in item:
            # 文件夹
            _parse_postman_items(item["item"], apis, item.get("name", parent_module))
        elif "request" in item:
            request = item["request"]
            method = request.get("method", "GET").upper()

            # 解析 URL
            url_obj = request.get("url", {})
            if isinstance(url_obj, str):
                path = url_obj
            else:
                raw_path = url_obj.get("raw", url_obj.get("path", ""))
                path_parts = url_obj.get("path", [])
                if path_parts:
                    path = "/" + "/".join(path_parts)
                else:
                    # 从 raw URL 提取路径
                    from urllib.parse import urlparse
                    parsed = urlparse(raw_path)
                    path = parsed.path or raw_path

            # 还原路径参数
            path = re.sub(r":(\w+)", r"{\1}", path)

            api_id = f"{method}_{path}"
            module = parent_module or _infer_module(path)

            # 解析参数
            path_params = []
            query_params = []
            header_params = []
            body_params = []

            # Path 参数
            for path_match in re.finditer(r"\{(\w+)\}", path):
                path_params.append({
                    "name": path_match.group(1),
                    "in": "path",
                    "required": True,
                    "type": "string",
                })

            # Query 参数
            if isinstance(url_obj, dict):
                for q in url_obj.get("query", []):
                    query_params.append({
                        "name": q.get("key", ""),
                        "in": "query",
                        "required": False,
                        "type": _infer_type_from_value(q.get("value", "")),
                        "description": q.get("description", ""),
                        "example": q.get("value", ""),
                    })

            # Header 参数
            for h in request.get("header", []):
                header_params.append({
                    "name": h.get("key", ""),
                    "in": "header",
                    "required": False,
                    "type": "string",
                    "description": h.get("description", ""),
                    "example": h.get("value", ""),
                })

            # Body 参数
            body = request.get("body", {})
            if body:
                body_mode = body.get("mode", "")
                if body_mode == "raw":
                    raw_body = body.get("raw", "")
                    try:
                        json_body = json.loads(raw_body)
                        body_params = _infer_params_from_json(json_body)
                    except json.JSONDecodeError:
                        body_params = [{"name": "body", "in": "body", "required": False, "type": "string", "description": "Raw request body"}]
                elif body_mode in ("formdata", "urlencoded"):
                    for field in body.get(body_mode, []):
                        body_params.append({
                            "name": field.get("key", ""),
                            "in": "body",
                            "required": False,
                            "type": "file" if field.get("type") == "file" else _infer_type_from_value(field.get("value", "")),
                            "description": field.get("description", ""),
                            "example": field.get("value", ""),
                        })

            # 解析响应
            success = None
            errors = []
            for resp in item.get("response", []):
                resp_obj = {
                    "status_code": resp.get("code", 200),
                    "description": resp.get("status", ""),
                }
                resp_body = resp.get("body", "")
                if resp_body:
                    try:
                        json_resp = json.loads(resp_body)
                        resp_obj["schema"] = _infer_response_fields(json_resp)
                        resp_obj["example"] = json_resp
                    except json.JSONDecodeError:
                        resp_obj["example"] = resp_body

                code = resp.get("code", 200)
                if code < 400:
                    if success is None:
                        success = resp_obj
                else:
                    errors.append(resp_obj)

            if success is None:
                success = {"status_code": 200, "description": "成功（无示例响应）"}

            # 识别业务规则
            business_rules = _extract_business_rules(
                request.get("description", ""),
                item.get("name", ""),
                api_id
            )

            api_def = {
                "api_id": api_id,
                "name": item.get("name", ""),
                "path": path,
                "method": method,
                "module": module,
                "description": request.get("description", ""),
                "deprecated": False,
                "tags": [],
                "parameters": {
                    "path_params": path_params,
                    "query_params": query_params,
                    "header_params": header_params,
                    "body_params": body_params,
                },
                "responses": {"success": success, "errors": errors},
                "business_rules": business_rules,
            }
            apis.append(api_def)


# ─────────────────────── HAR 解析 ───────────────────────

def parse_har(data: dict) -> dict:
    """解析 HAR 文件"""
    entries = data.get("log", {}).get("entries", [])
    apis = []
    seen_api_ids = set()

    for entry in entries:
        request = entry.get("request", {})
        method = request.get("method", "GET").upper()
        url = request.get("url", "")

        # 解析 URL
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        path = parsed.path or "/"

        api_id = f"{method}_{path}"

        # 去重
        if api_id in seen_api_ids:
            continue
        seen_api_ids.add(api_id)

        module = _infer_module(path)

        # 解析参数
        path_params = []
        query_params = []
        header_params = []
        body_params = []

        # Query 参数
        qs = parse_qs(parsed.query)
        for key, values in qs.items():
            query_params.append({
                "name": key,
                "in": "query",
                "required": False,
                "type": _infer_type_from_value(values[0] if values else ""),
                "example": values[0] if values else "",
            })

        # Header 参数
        for h in request.get("headers", []):
            name = h.get("name", "")
            if name.lower() not in ("host", "connection", "content-length", "accept-encoding"):
                header_params.append({
                    "name": name,
                    "in": "header",
                    "required": False,
                    "type": "string",
                    "example": h.get("value", ""),
                })

        # Body 参数
        post_data = request.get("postData", {})
        if post_data:
            mime_type = post_data.get("mimeType", "")
            text = post_data.get("text", "")
            if "json" in mime_type and text:
                try:
                    json_body = json.loads(text)
                    body_params = _infer_params_from_json(json_body)
                except json.JSONDecodeError:
                    body_params = [{"name": "body", "in": "body", "required": False, "type": "string"}]
            elif "form" in mime_type:
                for param in post_data.get("params", []):
                    body_params.append({
                        "name": param.get("name", ""),
                        "in": "body",
                        "required": False,
                        "type": "file" if param.get("fileName") else "string",
                        "example": param.get("value", ""),
                    })

        # 解析响应
        response = entry.get("response", {})
        success = None
        errors = []

        resp_obj = {
            "status_code": response.get("status", 200),
            "description": response.get("statusText", ""),
        }
        resp_content = response.get("content", {})
        resp_text = resp_content.get("text", "")
        if resp_text:
            try:
                json_resp = json.loads(resp_text)
                resp_obj["schema"] = _infer_response_fields(json_resp)
                resp_obj["example"] = json_resp
            except json.JSONDecodeError:
                resp_obj["example"] = resp_text

        if response.get("status", 200) < 400:
            success = resp_obj
        else:
            errors.append(resp_obj)

        if success is None:
            success = {"status_code": 200, "description": "成功（无示例响应）"}

        business_rules = _extract_business_rules("", "", api_id)

        api_def = {
            "api_id": api_id,
            "name": f"{method} {path}",
            "path": path,
            "method": method,
            "module": module,
            "description": "来自 HAR 抓包",
            "deprecated": False,
            "tags": [],
            "parameters": {
                "path_params": path_params,
                "query_params": query_params,
                "header_params": header_params,
                "body_params": body_params,
            },
            "responses": {"success": success, "errors": errors},
            "business_rules": business_rules,
        }
        apis.append(api_def)

    return _build_output(apis, "har")


# ─────────────────────── YApi 解析 ───────────────────────

def parse_yapi(data: list) -> dict:
    """解析 YApi 导出数据"""
    apis = []

    for item in data:
        path = item.get("path", "/")
        method = item.get("method", "GET").upper()

        api_id = f"{method}_{path}"
        module = _infer_module(path)

        # 解析参数
        path_params = []
        query_params = []
        header_params = []
        body_params = []

        # Path 参数
        for path_match in re.finditer(r"\{(\w+)\}", path):
            path_params.append({
                "name": path_match.group(1),
                "in": "path",
                "required": True,
                "type": "string",
            })

        # Query 参数
        for q in item.get("req_query", []):
            query_params.append({
                "name": q.get("name", ""),
                "in": "query",
                "required": q.get("required", "0") == "1",
                "type": _map_type(q.get("type", "string")),
                "description": q.get("desc", q.get("description", "")),
                "example": q.get("example", ""),
            })

        # Header 参数
        for h in item.get("req_headers", []):
            name = h.get("name", "")
            if name.lower() not in ("content-type",):
                header_params.append({
                    "name": name,
                    "in": "header",
                    "required": False,
                    "type": "string",
                    "description": h.get("desc", h.get("description", "")),
                    "example": h.get("value", ""),
                })

        # Body 参数
        req_body_type = item.get("req_body_type", "")
        req_body_other = item.get("req_body_other", "")
        if req_body_type == "json" and req_body_other:
            try:
                body_schema = json.loads(req_body_other)
                required_fields = body_schema.get("required", [])
                if body_schema.get("type") == "object" and "properties" in body_schema:
                    for prop_name, prop_schema in body_schema.get("properties", {}).items():
                        body_params.append({
                            "name": prop_name,
                            "in": "body",
                            "required": prop_name in required_fields,
                            "type": _map_type(prop_schema.get("type", "string")),
                            "description": prop_schema.get("description", ""),
                        })
            except json.JSONDecodeError:
                body_params = [{"name": "body", "in": "body", "required": False, "type": "string", "description": "JSON body"}]
        elif req_body_type == "form":
            for f in item.get("req_body_form", []):
                body_params.append({
                    "name": f.get("name", ""),
                    "in": "body",
                    "required": f.get("required", "0") == "1",
                    "type": "file" if f.get("type") == "file" else _map_type(f.get("type", "string")),
                    "description": f.get("desc", f.get("description", "")),
                    "example": f.get("example", ""),
                })
        elif req_body_type == "file":
            body_params.append({"name": "file", "in": "body", "required": True, "type": "file", "description": "上传文件"})

        # 解析响应
        res_body = item.get("res_body", "")
        success = {"status_code": 200, "description": "成功响应"}
        if res_body:
            try:
                res_schema = json.loads(res_body)
                success["schema"] = _flatten_response_schema(res_schema, {})
            except json.JSONDecodeError:
                pass

        business_rules = _extract_business_rules(
            item.get("desc", item.get("description", "")),
            item.get("title", ""),
            api_id
        )

        api_def = {
            "api_id": api_id,
            "name": item.get("title", ""),
            "path": path,
            "method": method,
            "module": module,
            "description": item.get("desc", item.get("description", "")),
            "deprecated": False,
            "tags": [],
            "parameters": {
                "path_params": path_params,
                "query_params": query_params,
                "header_params": header_params,
                "body_params": body_params,
            },
            "responses": {"success": success, "errors": []},
            "business_rules": business_rules,
        }
        apis.append(api_def)

    return _build_output(apis, "yapi")


# ─────────────────────── Apifox 解析 ───────────────────────

def parse_apifox(data: Any) -> dict:
    """解析 Apifox 导出数据（兼容 OpenAPI 3.x 格式）"""
    # Apifox 导出格式与 OpenAPI 3.x 高度兼容
    if isinstance(data, dict):
        if "openapi" in data:
            return parse_openapi(data)
        elif "api" in data or "apiDetail" in data:
            return _parse_apifox_native(data)
    return _build_output([], "apifox")


def _parse_apifox_native(data: dict) -> dict:
    """解析 Apifox 原生格式"""
    apis = []
    api_list = data.get("api", [data]) if isinstance(data.get("api"), list) else [data]

    for api_item in api_list:
        detail = api_item.get("apiDetail", api_item)
        # 简化处理，使用通用解析
        path = detail.get("path", "/")
        method = detail.get("method", "GET").upper()
        api_id = f"{method}_{path}"

        api_def = {
            "api_id": api_id,
            "name": detail.get("name", detail.get("title", "")),
            "path": path,
            "method": method,
            "module": _infer_module(path),
            "description": detail.get("description", ""),
            "deprecated": False,
            "tags": [],
            "parameters": {
                "path_params": [],
                "query_params": [],
                "header_params": [],
                "body_params": [],
            },
            "responses": {"success": {"status_code": 200, "description": "成功"}, "errors": []},
            "business_rules": [],
        }
        apis.append(api_def)

    return _build_output(apis, "apifox")


# ─────────────────────── 纯文本解析 ───────────────────────

def parse_text(content: str) -> dict:
    """解析纯文本接口描述"""
    apis = []
    lines = content.strip().split("\n")

    current_api = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 检测接口定义行
        api_match = re.match(
            r'(?:###\s*)?((?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+)(/[^\s]*)',
            line, re.IGNORECASE
        )
        if api_match:
            if current_api:
                apis.append(current_api)

            method = api_match.group(1).strip().upper()
            path = api_match.group(2).strip()
            api_id = f"{method}_{path}"

            current_api = {
                "api_id": api_id,
                "name": f"{method} {path}",
                "path": path,
                "method": method,
                "module": _infer_module(path),
                "description": "",
                "deprecated": False,
                "tags": [],
                "parameters": {
                    "path_params": [],
                    "query_params": [],
                    "header_params": [],
                    "body_params": [],
                },
                "responses": {"success": {"status_code": 200, "description": "成功"}, "errors": []},
                "business_rules": [],
            }

            # 提取路径参数
            for path_match in re.finditer(r"\{(\w+)\}", path):
                current_api["parameters"]["path_params"].append({
                    "name": path_match.group(1),
                    "in": "path",
                    "required": True,
                    "type": "string",
                })
            continue

        # 检测中文格式：接口名称 + 方法 + 路径
        cn_match = re.match(
            r'(.+?)\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/?\S+)',
            line, re.IGNORECASE
        )
        if cn_match and not api_match:
            if current_api:
                apis.append(current_api)

            name = cn_match.group(1).strip()
            method = cn_match.group(2).upper()
            path = cn_match.group(3).strip()
            api_id = f"{method}_{path}"

            current_api = {
                "api_id": api_id,
                "name": name,
                "path": path,
                "method": method,
                "module": _infer_module(path),
                "description": "",
                "deprecated": False,
                "tags": [],
                "parameters": {
                    "path_params": [],
                    "query_params": [],
                    "header_params": [],
                    "body_params": [],
                },
                "responses": {"success": {"status_code": 200, "description": "成功"}, "errors": []},
                "business_rules": [],
            }
            continue

        # 如果当前有接口，尝试解析参数和响应描述
        if current_api:
            # 参数行
            param_match = re.match(r'[-*]\s*(\w+)[（(](必填|选填)[,，]\s*(\w+)(?:[,，]\s*(.+?))?[)）]', line)
            if param_match:
                param_name = param_match.group(1)
                required = param_match.group(2) == "必填"
                param_type = _map_type(param_match.group(3))
                desc = param_match.group(4) or ""

                param = {
                    "name": param_name,
                    "in": "query",  # 默认 query，需根据上下文调整
                    "required": required,
                    "type": param_type,
                    "description": desc,
                }
                current_api["parameters"]["query_params"].append(param)
                continue

            # 描述行
            if line.startswith("描述") or line.startswith("说明") or line.startswith("功能"):
                current_api["description"] = re.sub(r'^(描述|说明|功能)[：:]\s*', '', line)
                continue

    if current_api:
        apis.append(current_api)

    return _build_output(apis, "text")


# ─────────────────────── 公共工具函数 ───────────────────────

def _map_type(raw_type: str) -> str:
    """映射类型到标准类型"""
    if not raw_type:
        return "string"
    return TYPE_MAP.get(raw_type.lower(), raw_type.lower())


def _infer_module(path: str) -> str:
    """根据路径推断模块"""
    parts = path.strip("/").split("/")
    # 跳过 api/v1 等通用前缀
    module_parts = []
    skip_prefixes = {"api", "v1", "v2", "v3", "rest", "graphql"}
    for part in parts:
        if part.lower() not in skip_prefixes and not re.match(r"\{.*\}", part):
            module_parts.append(part)
        if module_parts:
            break

    if not module_parts:
        return "未分类"

    module_name = module_parts[0]
    # 中文化模块名
    module_map = {
        "users": "用户模块",
        "user": "用户模块",
        "products": "商品模块",
        "product": "商品模块",
        "orders": "订单模块",
        "order": "订单模块",
        "payments": "支付模块",
        "payment": "支付模块",
        "cart": "购物车模块",
        "carts": "购物车模块",
        "auth": "认证模块",
        "login": "认证模块",
        "categories": "分类模块",
        "category": "分类模块",
        "comments": "评论模块",
        "comment": "评论模块",
        "search": "搜索模块",
        "upload": "文件模块",
        "files": "文件模块",
        "admin": "管理模块",
        "config": "配置模块",
        "settings": "设置模块",
    }
    return module_map.get(module_name.lower(), module_name)


def _infer_type_from_value(value: str) -> str:
    """根据示例值推断类型"""
    if not value:
        return "string"
    if value.lower() in ("true", "false"):
        return "boolean"
    try:
        int(value)
        return "integer"
    except ValueError:
        pass
    try:
        float(value)
        return "number"
    except ValueError:
        pass
    if value.startswith("["):
        return "array"
    if value.startswith("{"):
        return "object"
    return "string"


def _infer_params_from_json(json_data: Any, prefix: str = "") -> list:
    """从 JSON 示例推断参数列表"""
    params = []
    if isinstance(json_data, dict):
        for key, value in json_data.items():
            param_name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                params.append({
                    "name": param_name,
                    "in": "body",
                    "required": False,
                    "type": "object",
                    "description": "",
                })
                params.extend(_infer_params_from_json(value, param_name))
            elif isinstance(value, list):
                params.append({
                    "name": param_name,
                    "in": "body",
                    "required": False,
                    "type": "array",
                    "description": "",
                })
            else:
                params.append({
                    "name": param_name,
                    "in": "body",
                    "required": False,
                    "type": _infer_type_from_value(str(value)),
                    "example": value,
                    "description": "",
                })
    return params


def _infer_response_fields(json_data: Any, prefix: str = "") -> list:
    """从 JSON 响应示例推断字段结构"""
    fields = []
    if isinstance(json_data, dict):
        for key, value in json_data.items():
            field_path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                field = {
                    "field_path": field_path,
                    "type": "object",
                    "description": "",
                    "nested_fields": _infer_response_fields(value, field_path),
                }
                fields.append(field)
            elif isinstance(value, list):
                field = {
                    "field_path": field_path,
                    "type": "array",
                    "description": "",
                }
                if value and isinstance(value[0], dict):
                    field["nested_fields"] = _infer_response_fields(value[0], f"{field_path}[]")
                fields.append(field)
            else:
                field = {
                    "field_path": field_path,
                    "type": _infer_type_from_value(str(value)),
                    "description": "",
                    "example": value,
                }
                fields.append(field)
    return fields


# ─────────────────────── 业务规则提取 ───────────────────────

RULE_PATTERNS = {
    "rate_limiting": [
        (r'(\d+)\s*[次/QPS/qps/请求]/\s*[秒/分钟/小时/min/hour/s/m/h]', "high"),
        (r'同一\s*(?:IP|用户).*?(\d+).*?[次/请求]', "medium"),
        (r'限流|频率|QPS|限次|rate\s*limit|throttle', "medium"),
    ],
    "encryption": [
        (r'(?:RSA|AES|DES|MD5|SHA\d*|HMAC)\s*[-–—]?\s*(?:加密|签名|算法)', "high"),
        (r'加密|签名|encrypt|sign|crypto', "medium"),
        (r'密码.*?(?:加密|不明文)', "low"),
    ],
    "authentication": [
        (r'(?:Bearer|OAuth|APIKey|Basic)\s*(?:Token|Auth|认证)', "high"),
        (r'鉴权|认证|授权|auth|token', "medium"),
    ],
    "dependency": [
        (r'需?(?:要先|必须先|前置).*?调用.*?(?:接口|API)', "high"),
        (r'依赖.*?接口|depend', "medium"),
    ],
    "consistency": [
        (r'事务|原子|一致性|回滚|transaction|atomic', "high"),
    ],
    "idempotency": [
        (r'幂等|idempotent', "high"),
        (r'防重|去重|防重复|dedup', "medium"),
    ],
    "data_masking": [
        (r'脱敏|掩码|遮盖|mask|desensitize', "high"),
        (r'\d+\*+\d+', "medium"),
    ],
    "concurrency": [
        (r'(?:分布式锁|乐观锁|悲观锁)', "high"),
        (r'并发|互斥|concurrent|lock|mutex', "medium"),
    ],
}


def _extract_business_rules(description: str, summary: str, api_id: str) -> list:
    """从描述中提取隐性业务规则"""
    rules = []
    rule_counter = 0
    combined_text = f"{description} {summary}"

    for category, patterns in RULE_PATTERNS.items():
        for pattern, confidence in patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                rule_counter += 1
                rules.append({
                    "rule_id": f"BR-{rule_counter:03d}",
                    "category": category,
                    "description": match.group(0),
                    "affected_apis": [api_id],
                    "source": "text_inference",
                    "confidence": confidence,
                })
                break  # 每个类别只取最高置信度的匹配

    return rules


# ─────────────────────── 输出构建 ───────────────────────

def _build_output(apis: list, source_type: str, source_file: str = "", global_rules: dict = None) -> dict:
    """构建标准化输出"""
    # 统计模块
    module_stats = {}
    for api in apis:
        module = api.get("module", "未分类")
        module_stats[module] = module_stats.get(module, 0) + 1

    modules = [{"name": name, "api_count": count} for name, count in sorted(module_stats.items())]

    result = {
        "meta": {
            "version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "source_type": source_type,
            "source_file": source_file,
            "total_apis": len(apis),
            "modules": modules,
        },
        "apis": apis,
        "global_rules": global_rules or {},
    }

    return result


def merge_definitions(definitions_list: list) -> dict:
    """合并多个解析结果"""
    if not definitions_list:
        return _build_output([], "mixed")

    if len(definitions_list) == 1:
        return definitions_list[0]

    all_apis = []
    all_modules = {}
    merged_global_rules = {}
    source_types = set()
    source_files = []

    for definition in definitions_list:
        meta = definition.get("meta", {})
        source_types.add(meta.get("source_type", "unknown"))
        if meta.get("source_file"):
            source_files.append(meta["source_file"])

        for api in definition.get("apis", []):
            # 去重：相同 api_id 的取更完整版本
            existing = next((a for a in all_apis if a["api_id"] == api["api_id"]), None)
            if existing:
                # 合并参数和响应
                _merge_api(existing, api)
            else:
                all_apis.append(api)

        for module in meta.get("modules", []):
            name = module["name"]
            all_modules[name] = all_modules.get(name, 0) + module["api_count"]

        # 合并全局规则
        for key, value in definition.get("global_rules", {}).items():
            if key not in merged_global_rules:
                merged_global_rules[key] = value

    # 重新统计模块
    module_stats = {}
    for api in all_apis:
        module = api.get("module", "未分类")
        module_stats[module] = module_stats.get(module, 0) + 1

    modules = [{"name": name, "api_count": count} for name, count in sorted(module_stats.items())]

    # 重新编号业务规则
    rule_counter = 0
    for api in all_apis:
        for rule in api.get("business_rules", []):
            rule_counter += 1
            rule["rule_id"] = f"BR-{rule_counter:03d}"

    source_type = "mixed" if len(source_types) > 1 else (source_types.pop() if source_types else "mixed")

    return {
        "meta": {
            "version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "source_type": source_type,
            "source_file": ", ".join(source_files),
            "total_apis": len(all_apis),
            "modules": modules,
        },
        "apis": all_apis,
        "global_rules": merged_global_rules,
    }


def _merge_api(existing: dict, new: dict):
    """合并两个相同 api_id 的接口定义"""
    # 保留更完整的描述
    if len(new.get("description", "")) > len(existing.get("description", "")):
        existing["description"] = new["description"]
    if len(new.get("name", "")) > len(existing.get("name", "")):
        existing["name"] = new["name"]

    # 合并参数（取并集）
    for param_type in ["path_params", "query_params", "header_params", "body_params"]:
        existing_params = existing["parameters"].get(param_type, [])
        new_params = new["parameters"].get(param_type, [])

        existing_names = {p.get("name") for p in existing_params}
        for param in new_params:
            if param.get("name") not in existing_names:
                existing_params.append(param)
            else:
                # 更新已有参数的详细信息
                for ep in existing_params:
                    if ep.get("name") == param.get("name"):
                        for key, value in param.items():
                            if key not in ep or (not ep[key] and value):
                                ep[key] = value

    # 合并错误响应
    existing_errors = existing["responses"].get("errors", [])
    new_errors = new["responses"].get("errors", [])
    existing_codes = {e.get("status_code") for e in existing_errors}
    for error in new_errors:
        if error.get("status_code") not in existing_codes:
            existing_errors.append(error)

    # 合并业务规则
    existing_rules = existing.get("business_rules", [])
    new_rules = new.get("business_rules", [])
    existing_descs = {r.get("description") for r in existing_rules}
    for rule in new_rules:
        if rule.get("description") not in existing_descs:
            existing_rules.append(rule)


# ─────────────────────── 文件输出 ───────────────────────

def export_to_json(definition: dict, output_path: str):
    """导出为 JSON 文件"""
    total_apis = definition["meta"]["total_apis"]

    if total_apis <= MAX_APIS_PER_SHARD:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(definition, f, ensure_ascii=False, indent=2)
    else:
        _shard_output(definition, output_path, "json")


def export_to_yaml(definition: dict, output_path: str):
    """导出为 YAML 文件"""
    if not YAML_AVAILABLE:
        print("警告: 未安装 PyYAML，将输出 JSON 格式")
        json_path = output_path.rsplit(".", 1)[0] + ".json"
        export_to_json(definition, json_path)
        return

    total_apis = definition["meta"]["total_apis"]

    if total_apis <= MAX_APIS_PER_SHARD:
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(definition, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    else:
        _shard_output(definition, output_path, "yaml")


def _shard_output(definition: dict, output_path: str, fmt: str):
    """按模块分片输出"""
    base_dir = os.path.dirname(output_path)
    base_name = os.path.splitext(os.path.basename(output_path))[0]

    # 按模块分组
    module_apis = {}
    for api in definition["apis"]:
        module = api.get("module", "未分类")
        if module not in module_apis:
            module_apis[module] = []
        module_apis[module].append(api)

    # 生成每个模块的文件
    shards = []
    for module_name, apis in module_apis.items():
        # 大模块继续分片
        for i in range(0, len(apis), MAX_APIS_PER_SHARD):
            chunk = apis[i:i + MAX_APIS_PER_SHARD]
            suffix = f"_{i // MAX_APIS_PER_SHARD + 1}" if len(apis) > MAX_APIS_PER_SHARD else ""
            safe_module = re.sub(r'[^\w\u4e00-\u9fff]', '_', module_name)
            shard_name = f"{base_name}_{safe_module}{suffix}"
            shard_file = f"{shard_name}.{fmt}"
            shard_path = os.path.join(base_dir, shard_file)

            shard_def = {
                "meta": {
                    **definition["meta"],
                    "total_apis": len(chunk),
                    "modules": [{"name": module_name, "api_count": len(chunk)}],
                },
                "apis": chunk,
                "global_rules": definition.get("global_rules", {}),
            }

            if fmt == "json":
                with open(shard_path, "w", encoding="utf-8") as f:
                    json.dump(shard_def, f, ensure_ascii=False, indent=2)
            else:
                with open(shard_path, "w", encoding="utf-8") as f:
                    yaml.dump(shard_def, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            shards.append({"file": shard_file, "module": module_name, "api_count": len(chunk)})

    # 生成索引文件
    index = {
        "index": {
            "version": SCHEMA_VERSION,
            "generated_at": definition["meta"]["generated_at"],
            "source_type": definition["meta"]["source_type"],
            "total_apis": definition["meta"]["total_apis"],
            "shards": shards,
        }
    }
    index_path = os.path.join(base_dir, f"{base_name}_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"接口数量 {definition['meta']['total_apis']} 超过 {MAX_APIS_PER_SHARD}，已按模块分片输出：")
    for shard in shards:
        print(f"  - {shard['file']} ({shard['module']}, {shard['api_count']}个接口)")
    print(f"  - {base_name}_index.json (索引文件)")


# ─────────────────────── 主入口 ───────────────────────

def parse_file(file_path: str, source_type: str = None) -> dict:
    """主解析函数"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 自动识别输入源类型
    if source_type is None:
        source_type = detect_source_type(file_path)

    print(f"检测到输入源类型: {source_type}")

    content = _read_file_content(file_path)
    if content is None:
        raise ValueError(f"无法读取文件: {file_path}")

    # 纯文本特殊处理
    if source_type == "text":
        result = parse_text(content)
        result["meta"]["source_file"] = os.path.basename(file_path)
        return result

    # 解析结构化数据
    data = _parse_content(content)
    if data is None:
        # 降级为纯文本解析
        print(f"无法解析为 JSON/YAML，尝试纯文本解析...")
        result = parse_text(content)
        result["meta"]["source_file"] = os.path.basename(file_path)
        return result

    # 根据类型分发解析
    parsers = {
        "swagger": lambda d: parse_swagger(d),
        "openapi": lambda d: parse_openapi(d),
        "postman": lambda d: parse_postman(d),
        "har": lambda d: parse_har(d),
        "yapi": lambda d: parse_yapi(d) if isinstance(d, list) else parse_text(content),
        "apifox": lambda d: parse_apifox(d),
    }

    parser = parsers.get(source_type)
    if parser is None:
        raise ValueError(f"不支持的输入源类型: {source_type}")

    result = parser(data)
    result["meta"]["source_file"] = os.path.basename(file_path)

    return result


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description="API Schema Parser - 接口定义解析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="+", help="输入文件路径（支持多个文件合并）")
    parser.add_argument("--format", "-f", choices=["json", "yaml"], default="json", help="输出格式（默认 JSON）")
    parser.add_argument("--output", "-o", help="输出文件路径（默认 api_definitions.json/yaml）")
    parser.add_argument("--type", "-t", choices=["swagger", "openapi", "postman", "har", "yapi", "apifox", "text"],
                        help="指定输入源类型（跳过自动识别）")

    args = parser.parse_args()

    # 解析每个输入文件
    definitions = []
    for input_file in args.input:
        try:
            definition = parse_file(input_file, args.type)
            definitions.append(definition)
            print(f"✓ {input_file}: 解析完成，共 {definition['meta']['total_apis']} 个接口")
        except Exception as e:
            print(f"✗ {input_file}: 解析失败 - {e}")

    if not definitions:
        print("错误: 没有成功解析的文件")
        sys.exit(1)

    # 合并多个输入
    if len(definitions) > 1:
        result = merge_definitions(definitions)
        print(f"\n合并完成，共 {result['meta']['total_apis']} 个接口")
    else:
        result = definitions[0]

    # 确定输出路径
    ext = ".yaml" if args.format == "yaml" else ".json"
    if args.output:
        output_path = args.output
    else:
        output_path = f"api_definitions{ext}"

    # 输出
    if args.format == "yaml":
        export_to_yaml(result, output_path)
    else:
        export_to_json(result, output_path)

    print(f"\n✓ 输出文件: {output_path}")

    # 统计摘要
    meta = result["meta"]
    print(f"\n{'='*50}")
    print(f"解析摘要")
    print(f"{'='*50}")
    print(f"输入源类型: {meta['source_type']}")
    print(f"接口总数: {meta['total_apis']}")
    print(f"模块统计:")
    for module in meta.get("modules", []):
        print(f"  - {module['name']}: {module['api_count']} 个接口")

    # 业务规则统计
    total_rules = sum(len(api.get("business_rules", [])) for api in result.get("apis", []))
    if total_rules > 0:
        print(f"识别业务规则: {total_rules} 条")


if __name__ == "__main__":
    main()
