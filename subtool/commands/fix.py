from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from copy import deepcopy

from ..models import SubtitleFile, SubtitleCue
from .scan import (
    scan_subtitle, ScanIssue, format_ms,
    check_overlaps, check_empty_cues, check_index_gaps
)


FIX_TYPE_RENUMBER = 'renumber'
FIX_TYPE_REMOVE_EMPTY = 'remove_empty'
FIX_TYPE_FIX_OVERLAP = 'fix_overlap'

FIX_TYPE_LABELS = {
    FIX_TYPE_RENUMBER: '重新编号',
    FIX_TYPE_REMOVE_EMPTY: '删除空字幕',
    FIX_TYPE_FIX_OVERLAP: '修复时间轴重叠'
}

SKIP_REASON_NO_SUGGESTIONS = 'no_suggestions'
SKIP_REASON_USER_CANCEL = 'user_cancel'
SKIP_REASON_WRITE_FAILED = 'write_failed'

SKIP_REASON_LABELS = {
    SKIP_REASON_NO_SUGGESTIONS: '无修复建议',
    SKIP_REASON_USER_CANCEL: '用户取消',
    SKIP_REASON_WRITE_FAILED: '写入失败'
}


@dataclass
class FixSuggestion:
    fix_type: str
    cue_index: Optional[int]
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None

    @property
    def fix_type_label(self) -> str:
        return FIX_TYPE_LABELS.get(self.fix_type, self.fix_type)


@dataclass
class FixPlan:
    file: str
    original_cues: int
    suggestions: List[FixSuggestion] = field(default_factory=list)

    @property
    def total_suggestions(self) -> int:
        return len(self.suggestions)

    @property
    def by_type_counts(self) -> Dict[str, int]:
        counts = {}
        for s in self.suggestions:
            counts[s.fix_type] = counts.get(s.fix_type, 0) + 1
        return counts


@dataclass
class FixItemDetail:
    fix_type: str
    cue_index: Optional[int]
    before: Dict[str, Any] = field(default_factory=dict)
    after: Dict[str, Any] = field(default_factory=dict)

    @property
    def fix_type_label(self) -> str:
        return FIX_TYPE_LABELS.get(self.fix_type, self.fix_type)


def _detect_index_issues(subfile: SubtitleFile) -> List[FixSuggestion]:
    suggestions = []
    issues = check_index_gaps(subfile)
    if issues:
        has_issue = False
        missing_total = 0
        gap_details = []
        for issue in issues:
            if issue.type == 'index_gap':
                missing_total += issue.details.get('missing_count', 0)
                has_issue = True
                gap_details.append(f"#{issue.details['expected']}->#{issue.details['actual']}")
            elif issue.type == 'index_duplicate':
                has_issue = True
                gap_details.append(f"#{issue.details['index']}重复")
        if has_issue:
            desc = f"检测到编号问题"
            if missing_total > 0:
                desc += f"，缺失{missing_total}个编号"
            desc += "，建议重新从1开始顺序编号"
            before_indices = [c.index for c in subfile.cues[:5]]
            if len(subfile.cues) > 5:
                before_indices.append('...')
            suggestions.append(FixSuggestion(
                fix_type=FIX_TYPE_RENUMBER,
                cue_index=None,
                description=desc,
                details={
                    'total_missing': missing_total,
                    'issue_count': len(issues),
                    'gap_details': gap_details
                },
                before={'index_sequence': before_indices},
                after={'index_sequence': f'1..{len(subfile.cues)} (连续)'}
            ))
    return suggestions


def _detect_empty_cues(subfile: SubtitleFile) -> List[FixSuggestion]:
    suggestions = []
    empty_issues = check_empty_cues(subfile)
    for issue in empty_issues:
        suggestions.append(FixSuggestion(
            fix_type=FIX_TYPE_REMOVE_EMPTY,
            cue_index=issue.cue_index,
            description=f"第{issue.cue_index}条字幕内容为空，建议删除",
            details={
                'start_time': issue.details['start_time'],
                'end_time': issue.details['end_time'],
                'duration_ms': issue.details['duration_ms']
            },
            before={
                'index': issue.cue_index,
                'time': f"{issue.details['start_time']} --> {issue.details['end_time']}",
                'text': '(空)'
            },
            after={
                'action': '删除',
                'reason': '内容为空'
            }
        ))
    return suggestions


def _detect_overlaps(subfile: SubtitleFile, threshold_ms: int = 500) -> List[FixSuggestion]:
    suggestions = []
    overlap_issues = check_overlaps(subfile)
    for issue in overlap_issues:
        overlap_ms = issue.details['overlap_ms']
        if overlap_ms <= threshold_ms:
            cue1_idx = issue.details['cue1_index']
            cue2_idx = issue.details['cue2_index']
            cue2_start = issue.details['cue2_start']
            cue1_end_old = issue.details['cue1_end']
            suggestions.append(FixSuggestion(
                fix_type=FIX_TYPE_FIX_OVERLAP,
                cue_index=cue1_idx,
                description=(f"第{cue1_idx}条与第{cue2_idx}条重叠{overlap_ms}ms（<=阈值{threshold_ms}ms），"
                             f"建议将第{cue1_idx}条结束时间从{cue1_end_old}调整为{cue2_start}"),
                details={
                    'cue1_index': cue1_idx,
                    'cue2_index': cue2_idx,
                    'cue1_end_old': cue1_end_old,
                    'cue1_end_new': cue2_start,
                    'overlap_ms': overlap_ms
                },
                before={
                    'cue_index': cue1_idx,
                    'end_time': cue1_end_old
                },
                after={
                    'cue_index': cue1_idx,
                    'end_time': cue2_start,
                    'overlap_resolved': f'{overlap_ms}ms重叠已消除'
                }
            ))
    return suggestions


def build_fix_plan(subfile: SubtitleFile, overlap_threshold_ms: int = 500,
                   skip_renumber: bool = False,
                   skip_empty: bool = False,
                   skip_overlap: bool = False) -> FixPlan:
    plan = FixPlan(file=subfile.path, original_cues=len(subfile.cues))

    if not skip_renumber:
        plan.suggestions.extend(_detect_index_issues(subfile))
    if not skip_empty:
        plan.suggestions.extend(_detect_empty_cues(subfile))
    if not skip_overlap:
        plan.suggestions.extend(_detect_overlaps(subfile, overlap_threshold_ms))

    return plan


def _apply_renumber(subfile: SubtitleFile) -> Tuple[SubtitleFile, List[FixItemDetail]]:
    fixed = deepcopy(subfile)
    before_indices = [c.index for c in fixed.cues]
    fixed.renumber()
    after_indices = [c.index for c in fixed.cues]
    details = [FixItemDetail(
        fix_type=FIX_TYPE_RENUMBER,
        cue_index=None,
        before={'index_sequence': before_indices},
        after={'index_sequence': after_indices}
    )]
    return fixed, details


def _apply_remove_empty(subfile: SubtitleFile) -> Tuple[SubtitleFile, List[FixItemDetail]]:
    fixed = deepcopy(subfile)
    details = []
    empty_cues = [(c.index, format_ms(c.start_ms), format_ms(c.end_ms)) for c in fixed.cues if c.is_empty]
    for idx, start, end in empty_cues:
        details.append(FixItemDetail(
            fix_type=FIX_TYPE_REMOVE_EMPTY,
            cue_index=idx,
            before={'index': idx, 'time': f'{start} --> {end}', 'text': '(空)'},
            after={'action': '已删除', 'reason': '内容为空'}
        ))
    fixed.cues = [cue for cue in fixed.cues if not cue.is_empty]
    fixed.renumber()
    return fixed, details


def _apply_fix_overlaps(subfile: SubtitleFile, threshold_ms: int = 500) -> Tuple[SubtitleFile, List[FixItemDetail]]:
    fixed = deepcopy(subfile)
    details = []
    cues = fixed.cues

    i = 0
    while i < len(cues) - 1:
        current = cues[i]
        next_cue = cues[i + 1]
        if current.end_ms > next_cue.start_ms:
            overlap_ms = current.end_ms - next_cue.start_ms
            if overlap_ms <= threshold_ms:
                old_end = format_ms(current.end_ms)
                new_end = format_ms(next_cue.start_ms)
                details.append(FixItemDetail(
                    fix_type=FIX_TYPE_FIX_OVERLAP,
                    cue_index=current.index,
                    before={'cue_index': current.index, 'end_time': old_end},
                    after={'cue_index': current.index, 'end_time': new_end, 'overlap_resolved': f'{overlap_ms}ms'}
                ))
                current.end_ms = next_cue.start_ms
        i += 1

    return fixed, details


def apply_fix_plan(subfile: SubtitleFile, plan: FixPlan,
                   overlap_threshold_ms: int = 500) -> Tuple[SubtitleFile, List[FixItemDetail]]:
    current = subfile
    all_details = []

    types_in_plan = set(s.fix_type for s in plan.suggestions)

    if FIX_TYPE_REMOVE_EMPTY in types_in_plan:
        current, details = _apply_remove_empty(current)
        all_details.extend(details)

    if FIX_TYPE_FIX_OVERLAP in types_in_plan:
        current, details = _apply_fix_overlaps(current, overlap_threshold_ms)
        all_details.extend(details)

    if FIX_TYPE_RENUMBER in types_in_plan:
        current, details = _apply_renumber(current)
        all_details.extend(details)

    return current, all_details


def generate_fix_plan_report(plans: List[FixPlan]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("字幕自动修复预览报告 (Dry-Run)")
    lines.append("=" * 80)
    lines.append("")

    total_files = len(plans)
    total_suggestions = sum(p.total_suggestions for p in plans)
    files_with_issues = sum(1 for p in plans if p.total_suggestions > 0)

    lines.append(f"扫描文件数: {total_files}")
    lines.append(f"有修复建议文件: {files_with_issues}")
    lines.append(f"总修复建议数: {total_suggestions}")
    lines.append("")

    for plan in plans:
        lines.append("-" * 80)
        lines.append(f"文件: {plan.file}")
        lines.append(f"  原字幕数: {plan.original_cues}")
        lines.append(f"  建议数: {plan.total_suggestions}")
        if plan.by_type_counts:
            type_strs = []
            for t, c in plan.by_type_counts.items():
                type_strs.append(f"{FIX_TYPE_LABELS.get(t, t)}:{c}")
            lines.append(f"  分类: {', '.join(type_strs)}")
        lines.append("")

        if not plan.suggestions:
            lines.append("  [OK] 未检测到需要修复的问题")
            lines.append("")
            continue

        for i, suggestion in enumerate(plan.suggestions, 1):
            tag = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(
                "high" if suggestion.fix_type == FIX_TYPE_RENUMBER else "medium", "[?]"
            )
            lines.append(f"  {i:>2}. {tag} [{suggestion.fix_type_label}] {suggestion.description}")
            if suggestion.before:
                before_parts = [f"{k}={v}" for k, v in suggestion.before.items()]
                lines.append(f"      修复前: {', '.join(before_parts)}")
            if suggestion.after:
                after_parts = [f"{k}={v}" for k, v in suggestion.after.items()]
                lines.append(f"      修复后: {', '.join(after_parts)}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("说明:")
    lines.append("  - 重新编号: 解决编号缺失、重复或混乱问题（从1开始重新编号）")
    lines.append("  - 删除空字幕: 移除文本为空的字幕条目（保留的条目会自动重新编号）")
    lines.append("  - 修复时间轴重叠: 对 <=阈值(默认500ms) 的轻微重叠，将前一条结束时间调为后一条开始时间")
    lines.append("  - 确认写入时默认加 _fixed 后缀，原文件不被覆盖")
    lines.append("=" * 80)
    return "\n".join(lines)


def generate_fix_result_report(results: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("字幕自动修复执行报告")
    lines.append("=" * 80)
    lines.append("")

    total_files = len(results)
    status_counts = {}
    for r in results:
        s = r['status']
        status_counts[s] = status_counts.get(s, 0) + 1

    lines.append(f"处理文件数: {total_files}")
    for s, c in status_counts.items():
        label = {'success': '已修复', 'skipped': '跳过', 'failed': '失败'}.get(s, s)
        lines.append(f"  {label}: {c}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("文件详情:")
    lines.append("")

    for r in results:
        status_icon = {'success': '[OK]', 'skipped': '[SKIP]', 'failed': '[FAIL]'}.get(r['status'], '[?]')
        lines.append(f"{status_icon} {r['file_name']}")

        if r['status'] == 'success':
            lines.append(f"       字幕数: {r['original_cues']} -> {r['fixed_cues']}")
            lines.append(f"       输出文件: {r['output_path']}")
            fix_items = r.get('fix_items', [])
            if fix_items:
                lines.append(f"       修复条目 ({len(fix_items)}):")
                for item in fix_items:
                    label = FIX_TYPE_LABELS.get(item['fix_type'], item['fix_type'])
                    cue_str = f"#{item['cue_index']}" if item.get('cue_index') is not None else '(全局)'
                    before_parts = [f"{k}={v}" for k, v in item.get('before', {}).items()]
                    after_parts = [f"{k}={v}" for k, v in item.get('after', {}).items()]
                    lines.append(f"         - [{label}] {cue_str}")
                    if before_parts:
                        lines.append(f"           修复前: {', '.join(before_parts)}")
                    if after_parts:
                        lines.append(f"           修复后: {', '.join(after_parts)}")
            skipped_types = r.get('skipped_types', [])
            if skipped_types:
                skip_strs = [f"{FIX_TYPE_LABELS.get(t, t)}" for t in skipped_types]
                lines.append(f"       跳过类型: {', '.join(skip_strs)}")

        elif r['status'] == 'skipped':
            reason = r.get('skip_reason', '')
            reason_label = SKIP_REASON_LABELS.get(reason, reason)
            lines.append(f"       跳过原因: {reason_label}")

        else:
            lines.append(f"       错误: {r.get('error', '未知错误')}")

        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)
