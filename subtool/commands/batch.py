import os
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from ..models import SubtitleFile
from ..parser import parse_subtitle, find_subtitle_files
from ..writer import write_subtitle
from ..commands.scan import scan_subtitle, generate_scan_report
from ..commands.shift import shift_subtitle
from ..commands.split import split_subtitle
from ..commands.merge import merge_subtitles
from ..commands.stats import analyze_subtitle, generate_stats_report
from ..utils import (
    build_output_path, process_output, parse_time_string,
    generate_scan_summary, generate_scan_summary_report,
    generate_stats_summary, generate_stats_summary_report,
    save_report
)


@dataclass
class BatchResult:
    file: str
    status: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    output_files: List[str] = field(default_factory=list)


@dataclass
class BatchSummary:
    total_files: int = 0
    success_files: int = 0
    failed_files: int = 0
    total_actions: int = 0
    results: List[BatchResult] = field(default_factory=list)
    scan_results: List[Dict[str, Any]] = field(default_factory=list)
    stats_results: List[Any] = field(default_factory=list)

    def add_result(self, result: BatchResult):
        self.results.append(result)
        self.total_files += 1
        if result.status == 'success':
            self.success_files += 1
        else:
            self.failed_files += 1


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config


def validate_config(config: Dict[str, Any]) -> List[str]:
    errors = []

    if 'input' not in config:
        errors.append("缺少 input 配置")
    else:
        if 'dir' not in config['input'] and 'files' not in config['input']:
            errors.append("input 必须包含 dir 或 files")

    if 'actions' not in config or not isinstance(config['actions'], list):
        errors.append("缺少 actions 配置或格式错误")
    else:
        valid_actions = {'scan', 'shift', 'split', 'merge', 'stats'}
        for i, action in enumerate(config['actions']):
            if 'type' not in action:
                errors.append(f"第 {i+1} 个 action 缺少 type")
            elif action['type'] not in valid_actions:
                errors.append(f"第 {i+1} 个 action 类型 '{action['type']}' 不支持")

    return errors


def get_input_files_from_config(config: Dict[str, Any]) -> List[str]:
    input_cfg = config.get('input', {})

    if 'files' in input_cfg:
        return list(input_cfg['files'])

    input_dir = input_cfg.get('dir', '.')
    recursive = input_cfg.get('recursive', True)
    return find_subtitle_files(input_dir, recursive)


def get_output_config(config: Dict[str, Any]) -> Dict[str, Any]:
    output_cfg = config.get('output', {})
    naming = output_cfg.get('naming', {})
    return {
        'output_dir': output_cfg.get('dir'),
        'target_format': output_cfg.get('format'),
        'suffix': naming.get('suffix', ''),
        'prefix': naming.get('prefix', ''),
        'use_date_subdir': naming.get('date_subdir', False),
        'allow_overwrite': output_cfg.get('overwrite', False),
        'backup_method': output_cfg.get('backup', 'none'),
        'backup_dir': output_cfg.get('backup_dir'),
        'inplace': output_cfg.get('inplace', False)
    }


def execute_scan_action(subfile: SubtitleFile, params: Dict[str, Any]) -> Dict[str, Any]:
    result = scan_subtitle(
        subfile,
        max_chars_per_line=params.get('max_chars', 40),
        max_lines=params.get('max_lines', 2),
        min_gap_ms=params.get('min_gap', 0)
    )
    return {
        'action': 'scan',
        'total_issues': result['total_issues'],
        'errors': result['severity_counts']['error'],
        'warnings': result['severity_counts']['warning'],
        'has_errors': result['has_errors'],
        'result': result
    }


def execute_shift_action(subfile: SubtitleFile, params: Dict[str, Any]) -> Dict[str, Any]:
    options = {}
    if 'start_time' in params:
        options['start_ms'] = parse_time_string(params['start_time'])
    if 'end_time' in params:
        options['end_ms'] = parse_time_string(params['end_time'])
    if 'cue_start' in params:
        options['cue_start'] = params['cue_start']
    if 'cue_end' in params:
        options['cue_end'] = params['cue_end']

    offset_ms = params.get('offset_ms', 0)
    shifted = shift_subtitle(subfile, offset_ms, **options)

    return {
        'action': 'shift',
        'offset_ms': offset_ms,
        'subfile': shifted
    }


def execute_split_action(subfile: SubtitleFile, params: Dict[str, Any]) -> Dict[str, Any]:
    method = params.get('method', 'cue_count')
    options = {'method': method}

    if method == 'duration':
        options['max_duration_ms'] = params.get('max_duration', 600) * 1000
    elif method == 'cue_count':
        options['max_cues'] = params.get('max_cues', 100)
    elif method == 'line_count':
        options['max_lines'] = params.get('max_lines', 200)

    parts = split_subtitle(subfile, **options)

    return {
        'action': 'split',
        'method': method,
        'parts_count': len(parts),
        'parts': parts
    }


def execute_stats_action(subfile: SubtitleFile, params: Dict[str, Any]) -> Dict[str, Any]:
    stat = analyze_subtitle(
        subfile,
        wpm_threshold=params.get('wpm_threshold', 200),
        min_duration_ms=params.get('min_duration', 300)
    )

    return {
        'action': 'stats',
        'total_cues': stat.total_cues,
        'total_words': stat.total_words,
        'words_per_minute': stat.words_per_minute,
        'high_risk_count': len(stat.high_risk_sentences),
        'result': stat
    }


def execute_batch(config: Dict[str, Any], verbose: bool = False) -> BatchSummary:
    summary = BatchSummary()

    files = get_input_files_from_config(config)
    output_cfg = get_output_config(config)
    actions = config.get('actions', [])

    if not files:
        return summary

    report_cfg = config.get('report', {})

    for file_path in files:
        result = BatchResult(file=file_path, status='success')
        current_subfile = None

        try:
            current_subfile = parse_subtitle(file_path)

            for action_cfg in actions:
                action_type = action_cfg['type']
                params = action_cfg.get('params', {})
                summary.total_actions += 1

                if action_type == 'scan':
                    action_result = execute_scan_action(current_subfile, params)
                    result.actions.append(action_result)
                    summary.scan_results.append(action_result['result'])

                elif action_type == 'stats':
                    action_result = execute_stats_action(current_subfile, params)
                    result.actions.append(action_result)
                    summary.stats_results.append(action_result['result'])

                elif action_type == 'shift':
                    action_result = execute_shift_action(current_subfile, params)
                    result.actions.append(action_result)
                    current_subfile = action_result['subfile']

                elif action_type == 'split':
                    action_result = execute_split_action(current_subfile, params)
                    result.actions.append(action_result)

                    for part in action_result['parts']:
                        out_path = process_output(
                            part,
                            output_dir=output_cfg['output_dir'],
                            target_format=output_cfg['target_format'],
                            suffix=output_cfg['suffix'],
                            prefix=output_cfg['prefix'],
                            use_date_subdir=output_cfg['use_date_subdir'],
                            allow_overwrite=output_cfg['allow_overwrite']
                        )
                        result.output_files.append(out_path)

                else:
                    continue

            if 'split' not in [a['action'] for a in result.actions]:
                if current_subfile is not None and any(
                    a['action'] in ('shift',) for a in result.actions
                ):
                    out_path = process_output(
                        current_subfile,
                        output_dir=output_cfg['output_dir'],
                        target_format=output_cfg['target_format'],
                        inplace=output_cfg['inplace'],
                        backup_method=output_cfg['backup_method'],
                        backup_dir=output_cfg['backup_dir'],
                        suffix=output_cfg['suffix'],
                        prefix=output_cfg['prefix'],
                        use_date_subdir=output_cfg['use_date_subdir'],
                        allow_overwrite=output_cfg['allow_overwrite']
                    )
                    result.output_files.append(out_path)

        except Exception as e:
            result.status = 'failed'
            result.error = str(e)

        summary.add_result(result)

    return summary


def generate_batch_report(summary: BatchSummary, config: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("批处理执行报告")
    lines.append("=" * 80)
    lines.append("")

    lines.append(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"总文件数: {summary.total_files}")
    lines.append(f"成功: {summary.success_files}")
    lines.append(f"失败: {summary.failed_files}")
    lines.append(f"总动作数: {summary.total_actions}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("文件执行清单:")
    lines.append("")

    for result in summary.results:
        status_icon = "[OK]" if result.status == 'success' else "[FAIL]"
        filename = os.path.basename(result.file)
        lines.append(f"{status_icon} {filename}")

        if result.status == 'failed':
            lines.append(f"       错误: {result.error}")

        for action in result.actions:
            action_name = action['action']
            if action_name == 'scan':
                lines.append(f"       - scan: {action['total_issues']}个问题 "
                           f"(错误:{action['errors']}, 警告:{action['warnings']})")
            elif action_name == 'stats':
                lines.append(f"       - stats: {action['total_cues']}条, "
                           f"{action['total_words']}词, "
                           f"{action['words_per_minute']:.1f}词/分钟, "
                           f"{action['high_risk_count']}个高风险")
            elif action_name == 'shift':
                lines.append(f"       - shift: 偏移{action['offset_ms']}ms")
            elif action_name == 'split':
                lines.append(f"       - split: 拆分为{action['parts_count']}部分")

        if result.output_files:
            lines.append(f"       输出文件:")
            for out_file in result.output_files:
                lines.append(f"         -> {out_file}")

        lines.append("")

    if summary.scan_results:
        scan_summary = generate_scan_summary(summary.scan_results)
        scan_report = generate_scan_summary_report(scan_summary)
        lines.append(scan_report)

    if summary.stats_results:
        stats_summary = generate_stats_summary(summary.stats_results)
        stats_report = generate_stats_summary_report(stats_summary)
        lines.append(stats_report)

    lines.append("=" * 80)
    return "\n".join(lines)


def batch_summary_to_json(summary: BatchSummary, config: Dict[str, Any]) -> str:
    results_json = []
    for result in summary.results:
        actions_json = []
        for action in result.actions:
            action_copy = dict(action)
            if 'result' in action_copy:
                del action_copy['result']
            if 'parts' in action_copy:
                action_copy['parts'] = [{'cues': len(p.cues)} for p in action_copy['parts']]
            if 'subfile' in action_copy:
                del action_copy['subfile']
            actions_json.append(action_copy)

        results_json.append({
            'file': result.file,
            'file_name': os.path.basename(result.file),
            'status': result.status,
            'error': result.error,
            'actions': actions_json,
            'output_files': result.output_files
        })

    data = {
        'summary_type': 'batch',
        'executed_at': datetime.now().isoformat(),
        'total_files': summary.total_files,
        'success_files': summary.success_files,
        'failed_files': summary.failed_files,
        'total_actions': summary.total_actions,
        'results': results_json
    }

    if summary.scan_results:
        scan_summary = generate_scan_summary(summary.scan_results)
        data['scan_summary'] = scan_summary

    if summary.stats_results:
        stats_summary = generate_stats_summary(summary.stats_results)
        data['stats_summary'] = stats_summary

    return json.dumps(data, ensure_ascii=False, indent=2)
