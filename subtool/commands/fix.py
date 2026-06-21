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


@dataclass
class FixSuggestion:
    fix_type: str
    cue_index: Optional[int]
    description: str
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def fix_type_label(self) -> str:
        return FIX_TYPE_LABELS.get(self.fix_type, self.fix_type)


@dataclass
class FixPlan:
    file: str
    original_cues: int
    suggestions: List[FixSuggestion] = field(default_factory=list)
    fixed_cues_count: int = 0

    @property
    def total_suggestions(self) -> int:
        return len(self.suggestions)

    @property
    def by_type_counts(self) -> Dict[str, int]:
        counts = {}
        for s in self.suggestions:
            counts[s.fix_type] = counts.get(s.fix_type, 0) + 1
        return counts


def _detect_index_issues(subfile: SubtitleFile) -> List[FixSuggestion]:
    suggestions = []
    issues = check_index_gaps(subfile)
    if issues:
        has_issue = False
        missing_total = 0
        for issue in issues:
            if issue.type == 'index_gap':
                missing_total += issue.details.get('missing_count', 0)
                has_issue = True
            elif issue.type == 'index_duplicate':
                has_issue = True
        if has_issue:
            desc = f"检测到编号问题"
            if missing_total > 0:
                desc += f"，缺失{missing_total}个编号"
            desc += "，建议重新从1开始顺序编号"
            suggestions.append(FixSuggestion(
                fix_type=FIX_TYPE_RENUMBER,
                cue_index=None,
                description=desc,
                details={
                    'total_missing': missing_total,
                    'issue_count': len(issues)
                }
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
            suggestions.append(FixSuggestion(
                fix_type=FIX_TYPE_FIX_OVERLAP,
                cue_index=cue1_idx,
                description=(f"第{cue1_idx}条与第{cue2_idx}条重叠{overlap_ms}ms（<=阈值{threshold_ms}ms），"
                             f"建议将第{cue1_idx}条结束时间调整为{cue2_start}"),
                details={
                    'cue1_index': cue1_idx,
                    'cue2_index': cue2_idx,
                    'cue1_end_old': issue.details['cue1_end'],
                    'cue1_end_new': cue2_start,
                    'overlap_ms': overlap_ms
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


def _apply_renumber(subfile: SubtitleFile) -> Tuple[SubtitleFile, int]:
    fixed = deepcopy(subfile)
    fixed.renumber()
    return fixed, len(fixed.cues)


def _apply_remove_empty(subfile: SubtitleFile) -> Tuple[SubtitleFile, int]:
    fixed = deepcopy(subfile)
    original_count = len(fixed.cues)
    fixed.cues = [cue for cue in fixed.cues if not cue.is_empty]
    removed = original_count - len(fixed.cues)
    fixed.renumber()
    return fixed, removed


def _apply_fix_overlaps(subfile: SubtitleFile, threshold_ms: int = 500) -> Tuple[SubtitleFile, int]:
    fixed = deepcopy(subfile)
    fixed_count = 0
    cues = fixed.cues

    i = 0
    while i < len(cues) - 1:
        current = cues[i]
        next_cue = cues[i + 1]
        if current.end_ms > next_cue.start_ms:
            overlap_ms = current.end_ms - next_cue.start_ms
            if overlap_ms <= threshold_ms:
                current.end_ms = next_cue.start_ms
                fixed_count += 1
        i += 1

    return fixed, fixed_count


def apply_fix_plan(subfile: SubtitleFile, plan: FixPlan,
                   overlap_threshold_ms: int = 500) -> Tuple[SubtitleFile, Dict[str, int]]:
    current = subfile
    applied_counts = {
        FIX_TYPE_RENUMBER: 0,
        FIX_TYPE_REMOVE_EMPTY: 0,
        FIX_TYPE_FIX_OVERLAP: 0
    }

    types_in_plan = set(s.fix_type for s in plan.suggestions)

    if FIX_TYPE_REMOVE_EMPTY in types_in_plan:
        current, removed = _apply_remove_empty(current)
        applied_counts[FIX_TYPE_REMOVE_EMPTY] = removed

    if FIX_TYPE_FIX_OVERLAP in types_in_plan:
        current, fixed = _apply_fix_overlaps(current, overlap_threshold_ms)
        applied_counts[FIX_TYPE_FIX_OVERLAP] = fixed

    if FIX_TYPE_RENUMBER in types_in_plan:
        current, count = _apply_renumber(current)
        applied_counts[FIX_TYPE_RENUMBER] = count

    return current, applied_counts


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
            if suggestion.cue_index is not None:
                lines.append(f"      涉及字幕: #{suggestion.cue_index}")
            for k, v in suggestion.details.items():
                if k not in ('cue1_index', 'cue2_index'):
                    lines.append(f"      {k}: {v}")
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
    success_files = sum(1 for r in results if r['status'] == 'success')
    failed_files = total_files - success_files

    lines.append(f"处理文件数: {total_files}")
    lines.append(f"成功: {success_files}")
    lines.append(f"失败: {failed_files}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("文件详情:")
    lines.append("")

    for r in results:
        status_icon = "[OK]" if r['status'] == 'success' else "[FAIL]"
        lines.append(f"{status_icon} {r['file_name']}")
        if r['status'] == 'success':
            lines.append(f"       原字幕数: {r['original_cues']} -> 修复后: {r['fixed_cues']}")
            applied = r.get('applied_counts', {})
            if applied:
                parts = []
                for t, c in applied.items():
                    if c > 0:
                        parts.append(f"{FIX_TYPE_LABELS.get(t, t)}:{c}")
                if parts:
                    lines.append(f"       已修复: {', '.join(parts)}")
            lines.append(f"       输出文件: {r['output_path']}")
        else:
            lines.append(f"       错误: {r.get('error', '未知错误')}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)
