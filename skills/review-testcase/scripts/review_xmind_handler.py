#!/usr/bin/env python3
"""
XMind测试点评审处理器
用于读取XMind测试点文件，追加评审标注和评审汇总

关键设计：
- 为每个测试点节点添加分类标签到labels（评审-可用/评审-待修改/评审-错误无效）
- 为每个测试点节点新增"评审结果"子节点，包含评分和改进建议
- 在根主题下新增"评审汇总"一级分支
- 保留原始XMind的层级结构、样式、标记、图片等
"""

import sys
import os
import json
import copy
import zipfile
import uuid
from datetime import datetime

# 评审标签前缀
REVIEW_TAG_PREFIX = '评审-'
CLASSIFICATION_LABELS = {
    '可用': '评审-可用',
    '待修改': '评审-待修改',
    '错误无效': '评审-错误无效',
}


def generate_id():
    """生成XMind节点ID"""
    return str(uuid.uuid4())


def read_xmind(file_path):
    """
    读取XMind文件，解析为结构化数据

    Args:
        file_path: XMind文件路径

    Returns:
        dict: 结构化数据
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

    for sheet in result['content']:
        sheet_data = {
            'name': sheet.get('title', 'Sheet'),
            'root_topic': sheet.get('rootTopic', {}),
            'all_topics': [],
            'sheet_ref': sheet
        }
        _flatten_topics(sheet.get('rootTopic', {}), sheet_data['all_topics'], level=0, parent_title='')
        result['sheets'].append(sheet_data)

    return result


def _flatten_topics(topic, flat_list, level=0, parent_title=''):
    """递归扁平化XMind主题树"""
    topic_info = {
        'id': topic.get('id', ''),
        'title': topic.get('title', ''),
        'level': level,
        'parent_title': parent_title,
        'labels': topic.get('labels', []),
        'markers': topic.get('markers', []),
        'notes': topic.get('notes', None),
        'topic_ref': topic,
        'children_count': 0
    }

    children = topic.get('children', {})
    attached = children.get('attached', [])
    detached = children.get('detached', [])
    topic_info['children_count'] = len(attached) + len(detached)

    flat_list.append(topic_info)

    for child in attached:
        _flatten_topics(child, flat_list, level + 1, topic.get('title', ''))
    for child in detached:
        _flatten_topics(child, flat_list, level + 1, topic.get('title', ''))


def _build_topic_id_map(topic, id_map):
    """递归构建ID到节点引用的映射"""
    topic_id = topic.get('id', '')
    if topic_id:
        id_map[topic_id] = topic

    children = topic.get('children', {})
    for child in children.get('attached', []):
        _build_topic_id_map(child, id_map)
    for child in children.get('detached', []):
        _build_topic_id_map(child, id_map)


def append_review_to_xmind(file_path, review_results, metrics_data, output_path=None):
    """
    向XMind文件追加评审标注

    Args:
        file_path: 原始XMind文件路径
        review_results: 评审结果列表，格式：
            [
                {
                    'topic_id': '节点ID',
                    'classification': '可用/待修改/错误无效',
                    'total_score': 85,
                    'scores': {
                        '逻辑完整性': 22,
                        '预期结果明确性': 18,
                        '前置条件完备性': 13,
                        'PRD覆盖度': 20,
                        '边界异常覆盖': 12
                    },
                    'deduction_reasons': '步骤跳跃-3分 | 预期结果模糊-2分',
                    'improvement_suggestions': '1. 补充第3步中间操作\n2. 明确第2步预期结果'
                },
                ...
            ]
        metrics_data: 量化指标数据（同review_excel_handler的格式）
        output_path: 输出文件路径

    Returns:
        str: 输出文件路径
    """
    data = read_xmind(file_path)

    if not output_path:
        base, ext = os.path.splitext(file_path)
        output_path = f"{base}【评审版】{ext}"

    # 构建ID到节点的映射
    for sheet_data in data['sheets']:
        id_map = {}
        _build_topic_id_map(sheet_data['root_topic'], id_map)

        # 处理每条评审结果
        for result in review_results:
            topic_id = result.get('topic_id', '')
            if topic_id not in id_map:
                continue

            topic = id_map[topic_id]
            classification = result.get('classification', '')

            # 添加分类标签到labels
            class_label = CLASSIFICATION_LABELS.get(classification, '')
            if class_label:
                labels = list(topic.get('labels', []))
                # 移除已有的评审标签（避免重复）
                labels = [l for l in labels if not l.startswith(REVIEW_TAG_PREFIX)]
                labels.insert(0, class_label)
                topic['labels'] = labels

            # 添加评审结果子节点
            if 'children' not in topic:
                topic['children'] = {}
            if 'attached' not in topic['children']:
                topic['children']['attached'] = []

            # 评审结果子节点
            scores = result.get('scores', {})
            total_score = result.get('total_score', 0)
            deduction_reasons = result.get('deduction_reasons', '')
            suggestions = result.get('improvement_suggestions', '')

            review_node = {
                'id': generate_id(),
                'class': 'topic',
                'title': f'评审: {classification} ({total_score}分)',
                'labels': ['评审结果'],
                'children': {
                    'attached': []
                }
            }

            # 5维得分子节点
            score_items = [
                ('逻辑完整性', 25),
                ('预期结果明确性', 20),
                ('前置条件完备性', 15),
                ('PRD覆盖度', 25),
                ('边界异常覆盖', 15),
            ]

            for dim_name, max_score in score_items:
                dim_value = scores.get(dim_name, 0)
                dim_node = {
                    'id': generate_id(),
                    'class': 'topic',
                    'title': f'{dim_name}: {dim_value}/{max_score}',
                    'labels': ['评分明细'],
                }
                review_node['children']['attached'].append(dim_node)

            # 扣分原因子节点
            if deduction_reasons:
                reason_node = {
                    'id': generate_id(),
                    'class': 'topic',
                    'title': f'扣分原因: {deduction_reasons}',
                    'labels': ['扣分原因'],
                }
                review_node['children']['attached'].append(reason_node)

            # 改进建议子节点
            if suggestions:
                suggest_node = {
                    'id': generate_id(),
                    'class': 'topic',
                    'title': f'改进建议: {suggestions}',
                    'labels': ['改进建议'],
                }
                review_node['children']['attached'].append(suggest_node)

            topic['children']['attached'].append(review_node)

        # 在根主题下新增"评审汇总"分支
        _add_summary_branch(sheet_data['root_topic'], metrics_data)

    # 写入新文件
    _write_xmind(data, output_path)
    print(f"Review saved to: {output_path}")
    return output_path


def _add_summary_branch(root_topic, metrics_data):
    """
    在根主题下添加"评审汇总"分支

    Args:
        root_topic: 根主题节点
        metrics_data: 量化指标数据
    """
    if 'children' not in root_topic:
        root_topic['children'] = {}
    if 'attached' not in root_topic['children']:
        root_topic['children']['attached'] = []

    summary_node = {
        'id': generate_id(),
        'class': 'topic',
        'title': '评审汇总',
        'labels': ['评审汇总'],
        'children': {
            'attached': []
        }
    }

    # 一、总体概况
    total = metrics_data.get('total_cases', 0)
    summary = metrics_data.get('classification_summary', {})
    overview_node = {
        'id': generate_id(),
        'class': 'topic',
        'title': f'总体概况 (共{total}条用例)',
        'labels': ['总体概况'],
        'children': {'attached': []}
    }

    for cls_name, count in summary.items():
        pct = f"{count / total * 100:.1f}%" if total > 0 else '0%'
        cls_node = {
            'id': generate_id(),
            'class': 'topic',
            'title': f'{cls_name}: {count}条 ({pct})',
            'labels': [f'评审-{cls_name}'],
        }
        overview_node['children']['attached'].append(cls_node)

    summary_node['children']['attached'].append(overview_node)

    # 二、量化指标达标情况
    metrics = metrics_data.get('metrics', {})
    if metrics:
        metrics_node = {
            'id': generate_id(),
            'class': 'topic',
            'title': '量化指标达标情况',
            'labels': ['量化指标'],
            'children': {'attached': []}
        }

        for metric_name, metric_info in metrics.items():
            value = metric_info.get('value', '-')
            threshold = metric_info.get('threshold', '-')
            passed = metric_info.get('passed', None)
            note = metric_info.get('note', '')

            if passed is True:
                status = '✅'
            elif passed is False:
                status = '❌'
            else:
                status = '⚠️'

            title_text = f'{status} {metric_name}: {value} (合格线: {threshold})'
            if note:
                title_text += f' [{note}]'

            metric_item = {
                'id': generate_id(),
                'class': 'topic',
                'title': title_text,
                'labels': ['指标详情'],
            }
            metrics_node['children']['attached'].append(metric_item)

        summary_node['children']['attached'].append(metrics_node)

    # 三、维度得分分布
    dim_scores = metrics_data.get('dimension_scores', {})
    if dim_scores:
        dim_node = {
            'id': generate_id(),
            'class': 'topic',
            'title': '维度得分分布',
            'labels': ['维度得分'],
            'children': {'attached': []}
        }

        for dim_name, dim_info in dim_scores.items():
            avg = dim_info.get('avg', 0)
            max_score = dim_info.get('max', 0)
            rate = dim_info.get('rate', '0%')
            dim_item = {
                'id': generate_id(),
                'class': 'topic',
                'title': f'{dim_name}: 平均{avg}分/{max_score}分 (得分率{rate})',
                'labels': ['维度明细'],
            }
            dim_node['children']['attached'].append(dim_item)

        summary_node['children']['attached'].append(dim_node)

    # 四、典型问题
    top_issues = metrics_data.get('top_issues', [])
    if top_issues:
        issues_node = {
            'id': generate_id(),
            'class': 'topic',
            'title': '典型问题 Top 10',
            'labels': ['典型问题'],
            'children': {'attached': []}
        }

        for issue in top_issues[:10]:
            issue_item = {
                'id': generate_id(),
                'class': 'topic',
                'title': f'#{issue.get("rank", "")} {issue.get("type", "")} ({issue.get("count", 0)}次)',
                'labels': ['问题详情'],
            }
            if issue.get('example'):
                issue_item['notes'] = {
                    'plain': {
                        'content': f'示例: {issue["example"]}'
                    }
                }
            issues_node['children']['attached'].append(issue_item)

        summary_node['children']['attached'].append(issues_node)

    root_topic['children']['attached'].append(summary_node)


def _write_xmind(data, output_path):
    """将修改后的数据写回XMind文件"""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        content_json = json.dumps(data['content'], ensure_ascii=False, indent=2)
        zf.writestr('content.json', content_json.encode('utf-8'))

        if data['metadata'] is not None:
            metadata_json = json.dumps(data['metadata'], ensure_ascii=False, indent=2)
            zf.writestr('metadata.json', metadata_json.encode('utf-8'))

        if data['manifest'] is not None:
            manifest_json = json.dumps(data['manifest'], ensure_ascii=False, indent=2)
            zf.writestr('manifest.json', manifest_json.encode('utf-8'))

        for name, content in data['other_files'].items():
            zf.writestr(name, content)


def xmind_to_text(data, sheet_index=0, max_level=10):
    """
    将XMind测试点转为文本格式，便于AI评审

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


def print_xmind_summary(data):
    """打印XMind文件概要信息"""
    print(f"文件: {data['file_path']}")
    for sheet in data['sheets']:
        print(f"\nSheet: {sheet['name']}")
        print(f"  总测试点数: {len(sheet['all_topics'])}")

        level_counts = {}
        for topic in sheet['all_topics']:
            lvl = topic['level']
            level_counts[lvl] = level_counts.get(lvl, 0) + 1
        for lvl in sorted(level_counts.keys()):
            label = ['根主题', '一级分支', '二级分支', '三级分支', '四级分支']
            name = label[lvl] if lvl < len(label) else f'第{lvl}级'
            print(f"  {name}: {level_counts[lvl]}个")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  python {sys.argv[0]} read <xmind_file>              - 读取并打印XMind测试点概要")
        print(f"  python {sys.argv[0]} text <xmind_file>              - 输出文本格式测试点列表")
        print(f"  python {sys.argv[0]} review <xmind_file>            - 追加示例评审结果（测试用）")
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

    elif command == 'review':
        if len(sys.argv) < 3:
            print("ERROR: Please provide XMind file path", file=sys.stderr)
            sys.exit(1)
        # 测试评审追加功能
        data = read_xmind(sys.argv[2])
        # 取第一个非根节点作为测试对象
        test_topic_id = ''
        for topic in data['sheets'][0]['all_topics']:
            if topic['level'] >= 2 and topic['title']:
                test_topic_id = topic['id']
                break

        if test_topic_id:
            test_review = [
                {
                    'topic_id': test_topic_id,
                    'classification': '可用',
                    'total_score': 85,
                    'scores': {
                        '逻辑完整性': 22,
                        '预期结果明确性': 18,
                        '前置条件完备性': 12,
                        'PRD覆盖度': 20,
                        '边界异常覆盖': 13
                    },
                    'deduction_reasons': '前置条件缺少1项-3分 | 边界异常轻微不足-2分',
                    'improvement_suggestions': '1. 前置条件补充账号权限说明\n2. 可补充1个边界值用例'
                }
            ]
            test_metrics = {
                'total_cases': 1,
                'classification_summary': {'可用': 1, '待修改': 0, '错误无效': 0},
                'metrics': {
                    '反向用例占比': {'value': '40%', 'threshold': '≥ 30%', 'passed': True},
                },
                'dimension_scores': {
                    '逻辑完整性': {'avg': 22, 'max': 25, 'rate': '88%'},
                    '预期结果明确性': {'avg': 18, 'max': 20, 'rate': '90%'},
                },
                'top_issues': [
                    {'rank': 1, 'type': '前置条件缺失', 'count': 1, 'example': '未说明账号权限'},
                ]
            }
            output = append_review_to_xmind(sys.argv[2], test_review, test_metrics)
            print(f"Output saved to: {output}")
        else:
            print("No suitable test topic found in XMind file")

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)
