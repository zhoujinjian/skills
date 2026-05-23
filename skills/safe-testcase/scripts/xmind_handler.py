#!/usr/bin/env python3
"""
XMind测试点文件处理器
用于读取XMind测试点文件，追加补全测试点，生成场景补全版文件

XMind 8+ 文件格式：ZIP压缩包，内部核心文件 content.json
结构：Sheet → RootTopic → Children(attached) → SubTopics → ...
"""

import sys
import os
import json
import copy
import zipfile
import tempfile
import shutil
import uuid
from datetime import datetime

# AI补全标识常量（用于XMind的labels，不在标题中添加）
AI_SUPPLEMENT_TAG = 'AI补全-场景遗漏'


def generate_id():
    """生成XMind节点ID（格式：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx）"""
    return str(uuid.uuid4())


def read_xmind(file_path):
    """
    读取XMind文件，解析为结构化数据

    Args:
        file_path: XMind文件路径

    Returns:
        dict: {
            'file_path': 文件路径,
            'content': content.json 解析后的Python对象,
            'metadata': metadata.json 解析后的Python对象,
            'manifest': manifest.json 解析后的Python对象,
            'other_files': {文件名: 文件内容bytes} 其他文件(图片等),
            'sheets': [
                {
                    'name': sheet标题,
                    'root_topic': 根主题字典,
                    'all_topics': [所有测试点(扁平化)],
                    'max_topic_index': 最大测试点序号
                }
            ]
        }
    """
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    result = {
        'file_path': file_path,
        'content': None,
        'metadata': None,
        'manifest': None,
        'other_files': {},
        'sheets': []
    }

    with zipfile.ZipFile(file_path, 'r') as zf:
        for name in zf.namelist():
            if name == 'content.json':
                result['content'] = json.loads(zf.read(name).decode('utf-8'))
            elif name == 'metadata.json':
                result['metadata'] = json.loads(zf.read(name).decode('utf-8'))
            elif name == 'manifest.json':
                result['manifest'] = json.loads(zf.read(name).decode('utf-8'))
            else:
                result['other_files'][name] = zf.read(name)

    if result['content'] is None:
        print("ERROR: content.json not found in XMind file", file=sys.stderr)
        sys.exit(1)

    # 解析每个sheet
    for sheet in result['content']:
        sheet_data = {
            'name': sheet.get('title', 'Sheet'),
            'root_topic': sheet.get('rootTopic', {}),
            'all_topics': [],
            'max_topic_index': 0,
            'sheet_ref': sheet
        }

        # 扁平化遍历所有节点
        root_topic = sheet.get('rootTopic', {})
        _flatten_topics(root_topic, sheet_data['all_topics'], level=0, parent_title='')

        # 计算最大编号
        sheet_data['max_topic_index'] = _get_max_topic_index(sheet_data['all_topics'])

        result['sheets'].append(sheet_data)

    return result


def _flatten_topics(topic, flat_list, level=0, parent_title=''):
    """
    递归扁平化XMind主题树

    Args:
        topic: 主题节点字典
        flat_list: 输出的扁平列表
        level: 当前层级（0=根主题，1=一级分支，2=二级分支...）
        parent_title: 父节点标题
    """
    topic_info = {
        'id': topic.get('id', ''),
        'title': topic.get('title', ''),
        'level': level,
        'parent_title': parent_title,
        'labels': topic.get('labels', []),
        'markers': topic.get('markers', []),
        'notes': topic.get('notes', None),
        'href': topic.get('href', ''),
        'topic_ref': topic,  # 保留原始引用，用于后续修改
        'children_count': 0
    }

    # 计算子节点数
    children = topic.get('children', {})
    attached = children.get('attached', [])
    detached = children.get('detached', [])
    topic_info['children_count'] = len(attached) + len(detached)

    flat_list.append(topic_info)

    # 递归处理子节点
    for child in attached:
        _flatten_topics(child, flat_list, level + 1, topic.get('title', ''))

    for child in detached:
        _flatten_topics(child, flat_list, level + 1, topic.get('title', ''))


def _get_max_topic_index(topics):
    """
    获取测试点列表中最大编号

    XMind测试点编号通常在标题中以数字编号形式出现，如：
    - "1.1 登录功能"
    - "TC001 登录验证"
    - "测试点1：正常登录"

    Returns:
        int: 最大编号数字
    """
    max_num = 0
    for topic in topics:
        title = topic['title']
        if not title:
            continue
        # 尝试多种编号格式
        import re
        patterns = [
            r'^(\d+)[.、\s]',          # "1. xxx" "1、xxx" "1 xxx"
            r'^TC(\d+)',                # "TC001 xxx"
            r'^测试点(\d+)',            # "测试点1 xxx"
            r'^#(\d+)',                 # "#1 xxx"
            r'^\[(\d+)\]',             # "[1] xxx"
            r'^（(\d+)）',              # "（1）xxx"
        ]
        for pattern in patterns:
            match = re.match(pattern, title)
            if match:
                try:
                    num = int(match.group(1))
                    max_num = max(max_num, num)
                except ValueError:
                    continue
                break
    return max_num


def print_xmind_summary(data):
    """打印XMind文件概要信息"""
    print(f"文件: {data['file_path']}")
    for sheet in data['sheets']:
        print(f"\nSheet: {sheet['name']}")
        print(f"  总测试点数: {len(sheet['all_topics'])}")
        print(f"  最大编号: {sheet['max_topic_index']}")

        # 按层级统计
        level_counts = {}
        for topic in sheet['all_topics']:
            lvl = topic['level']
            level_counts[lvl] = level_counts.get(lvl, 0) + 1
        for lvl in sorted(level_counts.keys()):
            label = ['根主题', '一级分支', '二级分支', '三级分支', '四级分支']
            name = label[lvl] if lvl < len(label) else f'第{lvl}级'
            print(f"  {name}: {level_counts[lvl]}个")

        # 打印前10个测试点标题
        print("  测试点示例:")
        shown = 0
        for topic in sheet['all_topics']:
            if topic['title'] and shown < 10:
                indent = '    ' + '  ' * topic['level']
                labels_str = f" [{','.join(topic['labels'])}]" if topic['labels'] else ''
                print(f"{indent}- {topic['title']}{labels_str}")
                shown += 1


def find_topic_by_keyword(data, keyword, sheet_index=0):
    """
    在指定sheet中按关键词搜索测试点

    Args:
        data: read_xmind返回的数据
        keyword: 搜索关键词
        sheet_index: sheet索引

    Returns:
        list: 匹配的测试点列表
    """
    if sheet_index >= len(data['sheets']):
        return []

    results = []
    for topic in data['sheets'][sheet_index]['all_topics']:
        if keyword.lower() in topic['title'].lower():
            results.append(topic)
    return results


def append_topics_to_xmind(file_path, new_topics_by_parent, output_path=None):
    """
    向XMind文件追加补全测试点

    XMind测试点补全采用"在对应父节点下追加子节点"的方式：
    - 找到与补全场景相关的父节点
    - 在该父节点的children.attached末尾追加新测试点
    - 新测试点的labels中包含"AI补全-场景遗漏"标记（不在标题中添加标记）
    - 标题保持干净的语义描述，便于阅读和搜索

    Args:
        file_path: 原始XMind文件路径
        new_topics_by_parent: 按父节点标题分组的补全测试点，格式：
            {
                '父节点标题': [
                    {
                        'title': '测试点标题（不含标识标记）',
                        'labels': ['P1'],
                        'notes': '详细说明/测试步骤'
                    },
                    ...
                ],
                ...
            }
            如果父节点标题为空字符串''，则追加到根主题下
            标识"AI补全-场景遗漏"会自动添加到labels中，无需手动填写
        output_path: 输出文件路径，默认为 原文件名+【场景补全版】.xmind

    Returns:
        str: 输出文件路径
    """
    data = read_xmind(file_path)

    if not output_path:
        base, ext = os.path.splitext(file_path)
        output_path = f"{base}【场景补全版】{ext}"

    total_added = 0

    # 遍历每个sheet
    for sheet_data in data['sheets']:
        root_topic = sheet_data['root_topic']

        # 构建标题到节点引用的映射
        title_to_topic = {}
        _build_title_map(root_topic, title_to_topic)

        for parent_title, new_topics in new_topics_by_parent.items():
            # 查找父节点
            if parent_title == '':
                # 追加到根主题下
                parent_topic = root_topic
            elif parent_title in title_to_topic:
                parent_topic = title_to_topic[parent_title]
            else:
                # 模糊匹配：找到标题包含关键词的节点
                parent_topic = None
                for title_key, topic_ref in title_to_topic.items():
                    if parent_title in title_key or title_key in parent_title:
                        parent_topic = topic_ref
                        break

                if parent_topic is None:
                    # 找不到父节点，追加到根主题下
                    parent_topic = root_topic

            # 确保children结构存在
            if 'children' not in parent_topic:
                parent_topic['children'] = {}
            if 'attached' not in parent_topic['children']:
                parent_topic['children']['attached'] = []

            # 追加新测试点
            for new_topic in new_topics:
                # 自动在labels中添加AI补全标识
                topic_labels = list(new_topic.get('labels', []))
                if AI_SUPPLEMENT_TAG not in topic_labels:
                    topic_labels.insert(0, AI_SUPPLEMENT_TAG)

                topic_node = {
                    'id': generate_id(),
                    'class': 'topic',
                    'title': new_topic.get('title', ''),
                    'labels': topic_labels,
                }

                # 添加备注（详细测试步骤/预期结果）
                if 'notes' in new_topic and new_topic['notes']:
                    topic_node['notes'] = {
                        'plain': {
                            'content': new_topic['notes']
                        }
                    }

                # 添加标记（优先级）
                if 'markers' in new_topic and new_topic['markers']:
                    topic_node['markers'] = new_topic['markers']
                elif 'labels' in new_topic:
                    # 将优先级标签转为marker
                    for label in new_topic.get('labels', []):
                        if label.startswith('P') and label[1:].isdigit():
                            marker_id = _priority_to_marker_id(label)
                            if marker_id:
                                if 'markers' not in topic_node:
                                    topic_node['markers'] = []
                                topic_node['markers'].append({
                                    'markerId': marker_id
                                })
                                break

                parent_topic['children']['attached'].append(topic_node)
                total_added += 1

    # 写入新文件
    _write_xmind(data, output_path)
    print(f"Added {total_added} topics, saved to: {output_path}")
    return output_path


def append_topics_to_xmind_by_dimension(file_path, dimension_topics, output_path=None):
    """
    按维度向XMind文件追加补全测试点

    当无法确定具体父节点时，在根主题下创建维度分组节点，
    每个维度分组下放置该维度的补全测试点。

    补全标识通过labels标记"AI补全-场景遗漏"，不在标题中添加标记。
    维度分组节点的labels标记"AI补全"。

    Args:
        file_path: 原始XMind文件路径
        dimension_topics: 按维度分组的补全测试点，格式：
            {
                '维度名称': [
                    {
                        'title': '测试点标题（不含标识标记）',
                        'labels': ['P1'],
                        'notes': '详细说明'
                    },
                    ...
                ],
                ...
            }
            标识"AI补全-场景遗漏"会自动添加到labels中
        output_path: 输出文件路径

    Returns:
        str: 输出文件路径
    """
    data = read_xmind(file_path)

    if not output_path:
        base, ext = os.path.splitext(file_path)
        output_path = f"{base}【场景补全版】{ext}"

    total_added = 0

    for sheet_data in data['sheets']:
        root_topic = sheet_data['root_topic']

        # 确保根主题有children
        if 'children' not in root_topic:
            root_topic['children'] = {}
        if 'attached' not in root_topic['children']:
            root_topic['children']['attached'] = []

        # 为每个维度创建一级分支节点
        for dim_name, topics in dimension_topics.items():
            dim_node = {
                'id': generate_id(),
                'class': 'topic',
                'title': f'{dim_name}【AI补全】',
                'children': {
                    'attached': []
                },
                'labels': ['AI补全']
            }

            for new_topic in topics:
                # 自动在labels中添加AI补全标识
                topic_labels = list(new_topic.get('labels', []))
                if AI_SUPPLEMENT_TAG not in topic_labels:
                    topic_labels.insert(0, AI_SUPPLEMENT_TAG)

                topic_node = {
                    'id': generate_id(),
                    'class': 'topic',
                    'title': new_topic.get('title', ''),
                    'labels': topic_labels,
                }

                if 'notes' in new_topic and new_topic['notes']:
                    topic_node['notes'] = {
                        'plain': {
                            'content': new_topic['notes']
                        }
                    }

                if 'markers' in new_topic and new_topic['markers']:
                    topic_node['markers'] = new_topic['markers']

                dim_node['children']['attached'].append(topic_node)
                total_added += 1

            root_topic['children']['attached'].append(dim_node)

    _write_xmind(data, output_path)
    print(f"Added {total_added} topics in dimension groups, saved to: {output_path}")
    return output_path


def _build_title_map(topic, title_map):
    """递归构建标题到节点引用的映射"""
    title = topic.get('title', '')
    if title:
        # 如果有重复标题，保留最后一个
        title_map[title] = topic

    children = topic.get('children', {})
    for child in children.get('attached', []):
        _build_title_map(child, title_map)
    for child in children.get('detached', []):
        _build_title_map(child, title_map)


def _priority_to_marker_id(priority_label):
    """将优先级标签转为XMind marker ID"""
    mapping = {
        'P0': 'priority-1',  # 红色旗帜 - 最高优先级
        'P1': 'priority-2',  # 橙色旗帜
        'P2': 'priority-3',  # 黄色旗帜
        'P3': 'priority-4',  # 绿色旗帜
        'P4': 'priority-5',  # 蓝色旗帜
    }
    return mapping.get(priority_label, '')


def _write_xmind(data, output_path):
    """将修改后的数据写回XMind文件"""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 写入content.json
        content_json = json.dumps(data['content'], ensure_ascii=False, indent=2)
        zf.writestr('content.json', content_json.encode('utf-8'))

        # 写入metadata.json
        if data['metadata'] is not None:
            metadata_json = json.dumps(data['metadata'], ensure_ascii=False, indent=2)
            zf.writestr('metadata.json', metadata_json.encode('utf-8'))

        # 写入manifest.json
        if data['manifest'] is not None:
            manifest_json = json.dumps(data['manifest'], ensure_ascii=False, indent=2)
            zf.writestr('manifest.json', manifest_json.encode('utf-8'))

        # 写入其他文件（图片等资源）
        for name, content in data['other_files'].items():
            zf.writestr(name, content)


def xmind_to_text(data, sheet_index=0, max_level=10):
    """
    将XMind测试点转为文本格式，便于AI分析和补全

    Args:
        data: read_xmind返回的数据
        sheet_index: sheet索引
        max_level: 最大展示层级

    Returns:
        str: 文本格式的测试点列表
    """
    if sheet_index >= len(data['sheets']):
        return ''

    lines = []
    for topic in data['sheets'][sheet_index]['all_topics']:
        if topic['level'] > max_level:
            continue
        indent = '  ' * topic['level']
        labels_str = f" [{','.join(topic['labels'])}]" if topic['labels'] else ''
        notes_str = ''
        if topic.get('notes'):
            note_content = ''
            if isinstance(topic['notes'], dict):
                plain = topic['notes'].get('plain', {})
                note_content = plain.get('content', '')
            elif isinstance(topic['notes'], str):
                note_content = topic['notes']
            if note_content:
                notes_str = f"  备注: {note_content}"
        lines.append(f"{indent}- {topic['title']}{labels_str}{notes_str}")

    return '\n'.join(lines)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  python {sys.argv[0]} read <xmind_file>              - 读取并打印XMind测试点概要")
        print(f"  python {sys.argv[0]} text <xmind_file>              - 输出文本格式测试点列表")
        print(f"  python {sys.argv[0]} search <xmind_file> <keyword>  - 搜索测试点")
        print(f"  python {sys.argv[0]} append <xmind_file>            - 追加示例测试点（测试用）")
        sys.exit(0)

    command = sys.argv[1]

    if command == 'read':
        if len(sys.argv) < 3:
            print("ERROR: Please provide XMind file path", file=sys.stderr)
            sys.exit(1)
        data = read_xmind(sys.argv[2])
        print_xmind_summary(data)

    elif command == 'text':
        if len(sys.argv) < 3:
            print("ERROR: Please provide XMind file path", file=sys.stderr)
            sys.exit(1)
        data = read_xmind(sys.argv[2])
        print(xmind_to_text(data))

    elif command == 'search':
        if len(sys.argv) < 4:
            print("ERROR: Please provide XMind file path and keyword", file=sys.stderr)
            sys.exit(1)
        data = read_xmind(sys.argv[2])
        results = find_topic_by_keyword(data, sys.argv[3])
        for r in results:
            indent = '  ' * r['level']
            print(f"{indent}- {r['title']} (level={r['level']})")

    elif command == 'append':
        if len(sys.argv) < 3:
            print("ERROR: Please provide XMind file path", file=sys.stderr)
            sys.exit(1)
        # 测试追加功能 - 按维度追加
        # 注意：标题中不包含标识，标识通过labels自动添加
        dimension_topics = {
            '边界场景补全': [
                {
                    'title': '手机号输入10位数字',
                    'labels': ['P1'],
                    'notes': '输入10位数字手机号，预期提示格式错误'
                },
                {
                    'title': '密码输入1位字符',
                    'labels': ['P1'],
                    'notes': '输入1位密码，预期提示密码长度不足'
                }
            ]
        }
        output = append_topics_to_xmind_by_dimension(sys.argv[2], dimension_topics)
        print(f"Output saved to: {output}")

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)
