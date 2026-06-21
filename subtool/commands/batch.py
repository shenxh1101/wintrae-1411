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


STAGE_PARSE = 'parse'
STAGE_SCAN = 'scan'
STAGE_STATS = 'stats'
STAGE_SHIFT = 'shift'
STAGE_SPLIT = 'split'
STAGE_MERGE = 'merge'
STAGE_WRITE = 'write'

ERROR_STAGE_MAP = {
    STAGE_PARSE: '解析失败',
    STAGE_SCAN: '扫描失败',
    STAGE_STATS: '统计失败',
    STAGE_SHIFT: '时间偏移失败',
    STAGE_SPLIT: '拆分失败',
    STAGE_MERGE: '合并失败',
    STAGE_WRITE: '写文件失败'
}


@dataclass
class BatchActionResult:
    action: str
    stage: str
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class BatchResult:
    file: str
    status: str
    error_stage: Optional[str] = None
    actions: List[BatchActionResult] = field(default_factory=list)
    error: Optional[str] = None
    output_files: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status == 'success'

    @property
    def error_stage_label(self) -> str:
        if not self.error_stage:
            return '-'
        return ERROR_STAGE_MAP.get(self.error_stage, self.error_stage)


@dataclass
class BatchSummary:
    total_files: int = 0
    success_files: int = 0
    failed_files: int = 0
    total_actions: int = 0
    results: List[BatchResult] = field(default_factory=list)
    scan_results: List[Dict[str, Any]] = field(default_factory=list)
    stats_results: List[Any] = field(default_factory=list)
    merge_outputs: List[str] = field(default_factory=list)
    error_stage_counts: Dict[str, int] = field(default_factory=dict)

    def add_result(self, result: BatchResult):
        self.results.append(result)
        self.total_files += 1
        if result.is_success:
            self.success_files += 1
        else:
            self.failed_files += 1
            if result.error_stage:
                self.error_stage_counts[result.error_stage] = \
                    self.error_stage_counts.get(result.error_stage, 0) + 1


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
            elif action['type'] == 'merge':
                if 'output' not in action:
                    errors.append(f"第 {i+1} 个 action (merge) 缺少 output 参数")

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


def execute_scan_action(subfile: SubtitleFile, params: Dict[str, Any]) -> BatchActionResult:
    try:
        result = scan_subtitle(
            subfile,
            max_chars_per_line=params.get('max_chars', 40),
            max_lines=params.get('max_lines', 2),
            min_gap_ms=params.get('min_gap', 0),
            wpm_threshold=params.get('wpm_threshold', 200),
            min_duration_ms=params.get('min_duration', 300)
        )
        return BatchActionResult(
            action='scan',
            stage=STAGE_SCAN,
            success=True,
            details={
                'total_issues': result['total_issues'],
                'errors': result['severity_counts']['error'],
                'warnings': result['severity_counts']['warning'],
                'total_duration_ms': result.get('total_duration_ms', 0),
                'total_words': result.get('total_words', 0),
                'total_chars': result.get('total_chars', 0),
                'high_risk': result.get('high_risk_count', 0),
                'has_errors': result['has_errors'],
                'raw_result': result
            }
        )
    except Exception as e:
        return BatchActionResult(
            action='scan',
            stage=STAGE_SCAN,
            success=False,
            error=str(e)
        )


def execute_shift_action(subfile: SubtitleFile, params: Dict[str, Any]) -> BatchActionResult:
    try:
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

        return BatchActionResult(
            action='shift',
            stage=STAGE_SHIFT,
            success=True,
            details={
                'offset_ms': offset_ms,
                'subfile': shifted
            }
        )
    except Exception as e:
        return BatchActionResult(
            action='shift',
            stage=STAGE_SHIFT,
            success=False,
            error=str(e)
        )


def execute_split_action(subfile: SubtitleFile, params: Dict[str, Any],
                          output_cfg: Dict[str, Any]) -> tuple:
    outputs = []
    try:
        method = params.get('method', 'cue_count')
        options = {'method': method}

        if method == 'duration':
            options['max_duration_ms'] = params.get('max_duration', 600) * 1000
        elif method == 'cue_count':
            options['max_cues'] = params.get('max_cues', 100)
        elif method == 'line_count':
            options['max_lines'] = params.get('max_lines', 200)

        parts = split_subtitle(subfile, **options)

        for part in parts:
            try:
                out_path = process_output(
                    part,
                    output_dir=output_cfg['output_dir'],
                    target_format=output_cfg['target_format'],
                    suffix=output_cfg['suffix'],
                    prefix=output_cfg['prefix'],
                    use_date_subdir=output_cfg['use_date_subdir'],
                    allow_overwrite=output_cfg['allow_overwrite']
                )
                outputs.append(out_path)
            except Exception as we:
                return BatchActionResult(
                    action='split',
                    stage=STAGE_WRITE,
                    success=False,
                    error=f"写入失败: {str(we)}"
                ), outputs

        return BatchActionResult(
            action='split',
            stage=STAGE_SPLIT,
            success=True,
            details={
                'method': method,
                'parts_count': len(parts)
            }
        ), outputs
    except Exception as e:
        return BatchActionResult(
            action='split',
            stage=STAGE_SPLIT,
            success=False,
            error=str(e)
        ), outputs


def execute_merge_action(subfiles: List[SubtitleFile], params: Dict[str, Any],
                          output_cfg: Dict[str, Any], output_path: str) -> BatchActionResult:
    try:
        gap_ms = params.get('gap', 0)
        renumber = params.get('renumber', True)

        merged = merge_subtitles(subfiles, output_path, renumber=renumber, gap_ms=gap_ms)

        target_format = output_cfg.get('target_format')
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
        written_path = write_subtitle(merged, output_path, target_format)

        return BatchActionResult(
            action='merge',
            stage=STAGE_MERGE,
            success=True,
            details={
                'output': written_path,
                'cues_count': len(merged.cues),
                'input_count': len(subfiles),
                'gap_ms': gap_ms,
                'renumber': renumber
            }
        )
    except Exception as e:
        return BatchActionResult(
            action='merge',
            stage=STAGE_MERGE,
            success=False,
            error=str(e)
        )


def execute_stats_action(subfile: SubtitleFile, params: Dict[str, Any]) -> BatchActionResult:
    try:
        stat = analyze_subtitle(
            subfile,
            wpm_threshold=params.get('wpm_threshold', 200),
            min_duration_ms=params.get('min_duration', 300)
        )

        return BatchActionResult(
            action='stats',
            stage=STAGE_STATS,
            success=True,
            details={
                'total_cues': stat.total_cues,
                'total_words': stat.total_words,
                'total_duration_ms': stat.total_duration_ms,
                'words_per_minute': stat.words_per_minute,
                'high_risk_count': len(stat.high_risk_sentences),
                'raw_result': stat
            }
        )
    except Exception as e:
        return BatchActionResult(
            action='stats',
            stage=STAGE_STATS,
            success=False,
            error=str(e)
        )


def write_output_file(subfile: SubtitleFile, output_cfg: Dict[str, Any]) -> tuple:
    try:
        out_path = process_output(
            subfile,
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
        return True, out_path, None
    except Exception as e:
        return False, None, str(e)


def execute_batch(config: Dict[str, Any], verbose: bool = False) -> BatchSummary:
    summary = BatchSummary()

    files = get_input_files_from_config(config)
    output_cfg = get_output_config(config)
    actions = config.get('actions', [])

    if not files:
        return summary

    merge_actions = [(i, a) for i, a in enumerate(actions) if a['type'] == 'merge']

    for file_path in files:
        result = BatchResult(file=file_path, status='success')
        current_subfile = None
        processed_subfile = None
        file_outputs = []

        try:
            try:
                current_subfile = parse_subtitle(file_path)
                processed_subfile = current_subfile
            except Exception as pe:
                result.status = 'failed'
                result.error_stage = STAGE_PARSE
                result.error = str(pe)
                summary.add_result(result)
                continue

            for action_idx, action_cfg in enumerate(actions):
                action_type = action_cfg['type']
                params = action_cfg.get('params', {})
                summary.total_actions += 1

                if action_type == 'scan':
                    action_result = execute_scan_action(current_subfile, params)
                    result.actions.append(action_result)
                    if not action_result.success:
                        result.status = 'failed'
                        result.error_stage = action_result.stage
                        result.error = action_result.error
                        break
                    summary.scan_results.append(action_result.details['raw_result'])

                elif action_type == 'stats':
                    action_result = execute_stats_action(current_subfile, params)
                    result.actions.append(action_result)
                    if not action_result.success:
                        result.status = 'failed'
                        result.error_stage = action_result.stage
                        result.error = action_result.error
                        break
                    summary.stats_results.append(action_result.details['raw_result'])

                elif action_type == 'shift':
                    action_result = execute_shift_action(current_subfile, params)
                    result.actions.append(action_result)
                    if not action_result.success:
                        result.status = 'failed'
                        result.error_stage = action_result.stage
                        result.error = action_result.error
                        break
                    current_subfile = action_result.details['subfile']
                    processed_subfile = current_subfile

                elif action_type == 'split':
                    action_result, split_outputs = execute_split_action(
                        current_subfile, params, output_cfg
                    )
                    result.actions.append(action_result)
                    file_outputs.extend(split_outputs)
                    if not action_result.success:
                        result.status = 'failed'
                        result.error_stage = action_result.stage
                        result.error = action_result.error
                        break

                elif action_type == 'merge':
                    continue

            if result.status != 'success':
                result.output_files.extend(file_outputs)
                summary.add_result(result)
                continue

            has_write_action = any(
                a.action in ('shift',) for a in result.actions
            ) and 'split' not in [a.action for a in result.actions]

            if has_write_action and processed_subfile is not None:
                write_ok, out_path, write_err = write_output_file(processed_subfile, output_cfg)
                if not write_ok:
                    result.status = 'failed'
                    result.error_stage = STAGE_WRITE
                    result.error = write_err
                else:
                    file_outputs.append(out_path)

            result.output_files.extend(file_outputs)

        except Exception as ue:
            result.status = 'failed'
            result.error_stage = result.error_stage or 'unknown'
            if not result.error:
                result.error = f"未预期错误: {str(ue)}"

        summary.add_result(result)

    for merge_idx, merge_action in merge_actions:
        merge_params = merge_action.get('params', {})
        raw_output = merge_action.get('output')

        inputs_for_merge = []
        for res in summary.results:
            if not res.is_success:
                continue
            for out_file in res.output_files:
                try:
                    sub = parse_subtitle(out_file)
                    inputs_for_merge.append(sub)
                except Exception:
                    continue

        if not inputs_for_merge:
            for file_path in files:
                try:
                    sub = parse_subtitle(file_path)
                    inputs_for_merge.append(sub)
                except Exception:
                    continue

        if not inputs_for_merge:
            dummy_result = BatchResult(
                file=f"[merge:{os.path.basename(raw_output)}]",
                status='failed',
                error_stage=STAGE_MERGE,
                error='没有可用的输入文件用于合并'
            )
            summary.add_result(dummy_result)
            continue

        merge_final_path = build_output_path(
            raw_output,
            output_dir=output_cfg.get('output_dir'),
            suffix=output_cfg.get('suffix', ''),
            prefix=output_cfg.get('prefix', ''),
            use_date_subdir=output_cfg.get('use_date_subdir', False),
            target_format=output_cfg.get('target_format'),
            allow_overwrite=output_cfg.get('allow_overwrite', False)
        )

        merge_result = execute_merge_action(
            inputs_for_merge, merge_params, output_cfg, merge_final_path
        )

        merge_res = BatchResult(
            file=f"[merge:{os.path.basename(raw_output)}]",
            status='success' if merge_result.success else 'failed',
            error_stage=merge_result.stage if not merge_result.success else None,
            error=merge_result.error
        )
        merge_res.actions.append(merge_result)

        if merge_result.success:
            written_path = merge_result.details['output']
            merge_res.output_files.append(written_path)
            summary.merge_outputs.append(written_path)
            merge_result.details.pop('raw_result', None)

        summary.add_result(merge_res)

    return summary


def format_action_detail(action: BatchActionResult) -> str:
    a = action
    if a.action == 'scan':
        dur = a.details.get('total_duration_ms', 0)
        from .scan import format_ms
        dur_str = format_ms(dur)
        return (f"scan: {a.details.get('total_issues', 0)}个问题 "
                f"(错误:{a.details.get('errors', 0)}, 警告:{a.details.get('warnings', 0)}, "
                f"高风险:{a.details.get('high_risk', 0)}) "
                f"{dur_str}/{a.details.get('total_words', 0)}词")
    elif a.action == 'stats':
        wpm = a.details.get('words_per_minute', 0)
        return (f"stats: {a.details.get('total_cues', 0)}条, "
                f"{a.details.get('total_words', 0)}词, "
                f"{wpm:.1f}词/分钟, "
                f"{a.details.get('high_risk_count', 0)}个高风险")
    elif a.action == 'shift':
        return f"shift: 偏移{a.details.get('offset_ms', 0)}ms"
    elif a.action == 'split':
        return f"split: 拆分为{a.details.get('parts_count', 0)}部分"
    elif a.action == 'merge':
        cues = a.details.get('cues_count', 0)
        inp = a.details.get('input_count', 0)
        out = os.path.basename(a.details.get('output', ''))
        return f"merge: 合并{inp}个文件 -> {out} ({cues}条)"
    return f"{a.action}: 执行{'成功' if a.success else '失败'}"


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
    if summary.error_stage_counts:
        lines.append("失败分类:")
        for stage, count in summary.error_stage_counts.items():
            lines.append(f"  - {ERROR_STAGE_MAP.get(stage, stage)}: {count}")
    if summary.merge_outputs:
        lines.append(f"合并输出: {len(summary.merge_outputs)}个文件")
    lines.append("")

    lines.append("-" * 80)
    lines.append("文件执行清单:")
    lines.append("")

    for result in summary.results:
        status_icon = "[OK]" if result.is_success else "[FAIL]"
        filename = os.path.basename(result.file)
        header = f"{status_icon} {filename}"
        if not result.is_success and result.error_stage:
            header += f" [{ERROR_STAGE_MAP.get(result.error_stage, result.error_stage)}]"
        lines.append(header)

        if result.status == 'failed':
            lines.append(f"       错误阶段: {result.error_stage_label}")
            lines.append(f"       错误信息: {result.error}")

        for action in result.actions:
            if action.success:
                detail = format_action_detail(action)
                lines.append(f"       - {detail}")
            else:
                stage_label = ERROR_STAGE_MAP.get(action.stage, action.stage)
                lines.append(f"       - {action.action} [失败: {stage_label}]: {action.error}")

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
            d = {
                'action': action.action,
                'stage': action.stage,
                'success': action.success,
            }
            if action.error:
                d['error'] = action.error
            details = {}
            for k, v in action.details.items():
                if k == 'raw_result':
                    continue
                if k == 'subfile':
                    continue
                details[k] = v
            if details:
                d['details'] = details
            actions_json.append(d)

        results_json.append({
            'file_path': result.file,
            'file_name': os.path.basename(result.file),
            'status': result.status,
            'error_stage': result.error_stage,
            'error_stage_label': result.error_stage_label,
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
        'error_stage_counts': {
            ERROR_STAGE_MAP.get(k, k): v for k, v in summary.error_stage_counts.items()
        },
        'merge_outputs': summary.merge_outputs,
        'results': results_json
    }

    if summary.scan_results:
        scan_summary = generate_scan_summary(summary.scan_results)
        data['scan_summary'] = scan_summary

    if summary.stats_results:
        stats_summary = generate_stats_summary(summary.stats_results)
        data['stats_summary'] = stats_summary

    return json.dumps(data, ensure_ascii=False, indent=2)
