import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from ..models import SubtitleFile
from .scan import scan_subtitle, format_ms
from .stats import analyze_subtitle, check_high_risk
from .fix import (
    build_fix_plan, FixPlan, FixSuggestion,
    FIX_TYPE_LABELS, FIX_TYPE_RENUMBER, FIX_TYPE_REMOVE_EMPTY, FIX_TYPE_FIX_OVERLAP
)


RISK_LEVEL_HIGH = 'high'
RISK_LEVEL_MEDIUM = 'medium'
RISK_LEVEL_LOW = 'low'
RISK_LEVEL_OK = 'ok'

RISK_LEVEL_LABELS = {
    RISK_LEVEL_HIGH: '高风险',
    RISK_LEVEL_MEDIUM: '中风险',
    RISK_LEVEL_LOW: '低风险',
    RISK_LEVEL_OK: '通过'
}

QA_CATEGORY_FIXED = 'fixed'
QA_CATEGORY_SUGGESTED = 'suggested'
QA_CATEGORY_CLEAN = 'clean'
QA_CATEGORY_FAILED = 'failed'

QA_CATEGORY_LABELS = {
    QA_CATEGORY_FIXED: '已修复',
    QA_CATEGORY_SUGGESTED: '只建议',
    QA_CATEGORY_CLEAN: '无需处理',
    QA_CATEGORY_FAILED: '失败'
}


@dataclass
class QAIssue:
    issue_type: str
    severity: str
    cue_index: Optional[int]
    message: str


@dataclass
class QASuggestion:
    fix_type: str
    fix_type_label: str
    priority: str
    description: str
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None


@dataclass
class QAFileResult:
    file_path: str
    file_name: str
    risk_level: str = RISK_LEVEL_OK
    category: str = QA_CATEGORY_CLEAN
    total_cues: int = 0
    total_duration_ms: int = 0
    total_words: int = 0
    total_chars: int = 0
    errors: int = 0
    warnings: int = 0
    high_risk: int = 0
    words_per_minute: float = 0.0
    issues: List[QAIssue] = field(default_factory=list)
    suggestions: List[QASuggestion] = field(default_factory=list)
    main_problems: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def risk_level_label(self) -> str:
        return RISK_LEVEL_LABELS.get(self.risk_level, self.risk_level)

    @property
    def category_label(self) -> str:
        return QA_CATEGORY_LABELS.get(self.category, self.category)


def _compute_risk_level(errors: int, warnings: int, high_risk: int) -> str:
    if errors > 0 or high_risk > 3:
        return RISK_LEVEL_HIGH
    if warnings > 2 or high_risk > 1:
        return RISK_LEVEL_MEDIUM
    if warnings > 0 or high_risk > 0:
        return RISK_LEVEL_LOW
    return RISK_LEVEL_OK


def _compute_category(has_errors: bool, has_suggestions: bool,
                       applied: bool = False, failed: bool = False) -> str:
    if failed:
        return QA_CATEGORY_FAILED
    if applied:
        return QA_CATEGORY_FIXED
    if has_suggestions:
        return QA_CATEGORY_SUGGESTED
    if has_errors:
        return QA_CATEGORY_SUGGESTED
    return QA_CATEGORY_CLEAN


def _extract_main_problems(scan_result: Dict[str, Any]) -> List[str]:
    problems = []
    type_counts = scan_result.get('type_counts', {})
    severity = scan_result.get('severity_counts', {})

    if severity.get('error', 0) > 0:
        error_types = []
        for t in ('overlap', 'empty', 'index_gap', 'index_duplicate', 'negative_duration'):
            if type_counts.get(t, 0) > 0:
                labels = {
                    'overlap': '时间轴重叠',
                    'empty': '空字幕',
                    'index_gap': '编号断裂',
                    'index_duplicate': '编号重复',
                    'negative_duration': '无效时长'
                }
                error_types.append(f"{labels.get(t, t)}:{type_counts[t]}")
        if error_types:
            problems.append(f"错误: {', '.join(error_types)}")

    if severity.get('warning', 0) > 0:
        warning_types = []
        for t in ('long_lines', 'long_line'):
            if type_counts.get(t, 0) > 0:
                labels = {'long_lines': '行数过多', 'long_line': '行过长'}
                warning_types.append(f"{labels.get(t, t)}:{type_counts[t]}")
        if warning_types:
            problems.append(f"警告: {', '.join(warning_types)}")

    return problems


def _suggestions_from_fix_plan(plan: FixPlan) -> List[QASuggestion]:
    suggestions = []
    priority_map = {
        FIX_TYPE_RENUMBER: 'high',
        FIX_TYPE_REMOVE_EMPTY: 'high',
        FIX_TYPE_FIX_OVERLAP: 'medium'
    }
    for s in plan.suggestions:
        suggestions.append(QASuggestion(
            fix_type=s.fix_type,
            fix_type_label=s.fix_type_label,
            priority=priority_map.get(s.fix_type, 'low'),
            description=s.description,
            before=s.before,
            after=s.after
        ))
    suggestions.sort(key=lambda x: {'high': 0, 'medium': 1, 'low': 2}.get(x.priority, 3))
    return suggestions


def execute_qa(subfile: SubtitleFile,
               wpm_threshold: float = 200,
               min_duration_ms: int = 300,
               overlap_threshold_ms: int = 500,
               apply_fix: bool = False) -> QAFileResult:
    result = QAFileResult(
        file_path=subfile.path,
        file_name=os.path.basename(subfile.path)
    )

    try:
        scan_result = scan_subtitle(
            subfile,
            wpm_threshold=wpm_threshold,
            min_duration_ms=min_duration_ms
        )

        stat = analyze_subtitle(
            subfile,
            wpm_threshold=wpm_threshold,
            min_duration_ms=min_duration_ms
        )

        fix_plan = build_fix_plan(
            subfile,
            overlap_threshold_ms=overlap_threshold_ms
        )

        result.total_cues = scan_result['total_cues']
        result.total_duration_ms = scan_result.get('total_duration_ms', 0)
        result.total_words = scan_result.get('total_words', 0)
        result.total_chars = scan_result.get('total_chars', 0)
        result.errors = scan_result['severity_counts']['error']
        result.warnings = scan_result['severity_counts']['warning']
        result.high_risk = scan_result.get('high_risk_count', 0)
        result.words_per_minute = stat.words_per_minute

        for issue in scan_result['issues']:
            result.issues.append(QAIssue(
                issue_type=issue.type,
                severity=issue.severity,
                cue_index=issue.cue_index,
                message=issue.message
            ))

        result.main_problems = _extract_main_problems(scan_result)

        if scan_result.get('high_risk_count', 0) > 0 and not result.main_problems:
            result.main_problems.append(f"高风险句子: {scan_result['high_risk_count']}条")

        result.suggestions = _suggestions_from_fix_plan(fix_plan)

        result.risk_level = _compute_risk_level(
            result.errors, result.warnings, result.high_risk
        )

        has_errors = scan_result['has_errors']
        has_suggestions = fix_plan.total_suggestions > 0
        result.category = _compute_category(
            has_errors=has_errors,
            has_suggestions=has_suggestions,
            applied=apply_fix,
            failed=False
        )

    except Exception as e:
        result.error = str(e)
        result.risk_level = RISK_LEVEL_HIGH
        result.category = QA_CATEGORY_FAILED

    return result


def execute_qa_batch(files: List[str],
                     wpm_threshold: float = 200,
                     min_duration_ms: int = 300,
                     overlap_threshold_ms: int = 500,
                     apply_fix: bool = False) -> List[QAFileResult]:
    from ..parser import parse_subtitle
    results = []
    for file_path in files:
        try:
            subfile = parse_subtitle(file_path)
            qa_result = execute_qa(
                subfile,
                wpm_threshold=wpm_threshold,
                min_duration_ms=min_duration_ms,
                overlap_threshold_ms=overlap_threshold_ms,
                apply_fix=apply_fix
            )
        except Exception as e:
            qa_result = QAFileResult(
                file_path=file_path,
                file_name=os.path.basename(file_path),
                risk_level=RISK_LEVEL_HIGH,
                category=QA_CATEGORY_FAILED,
                error=str(e)
            )
        results.append(qa_result)
    return results


def generate_qa_report(qa_results: List[QAFileResult]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("字幕质量检查综合报告 (QA)")
    lines.append("=" * 80)
    lines.append("")

    total_files = len(qa_results)
    category_counts = {}
    risk_counts = {}
    for r in qa_results:
        category_counts[r.category] = category_counts.get(r.category, 0) + 1
        risk_counts[r.risk_level] = risk_counts.get(r.risk_level, 0) + 1

    lines.append(f"检查文件数: {total_files}")
    lines.append("")
    lines.append("风险分布:")
    for level in (RISK_LEVEL_HIGH, RISK_LEVEL_MEDIUM, RISK_LEVEL_LOW, RISK_LEVEL_OK):
        count = risk_counts.get(level, 0)
        if count > 0:
            label = RISK_LEVEL_LABELS[level]
            lines.append(f"  {label}: {count}个文件")
    lines.append("")
    lines.append("处理分类:")
    for cat in (QA_CATEGORY_FIXED, QA_CATEGORY_SUGGESTED, QA_CATEGORY_CLEAN, QA_CATEGORY_FAILED):
        count = category_counts.get(cat, 0)
        if count > 0:
            label = QA_CATEGORY_LABELS[cat]
            lines.append(f"  {label}: {count}个文件")
    lines.append("")

    lines.append("-" * 80)
    lines.append("文件风险总览:")
    lines.append("")

    header = (f"{'文件名':<26} {'风险':>6} {'分类':>6} {'错误':>5} {'警告':>5} "
              f"{'高风险':>6} {'时长':>11} {'字数':>6}")
    lines.append(header)
    lines.append("-" * 80)

    for r in qa_results:
        risk_short = {'high': '高', 'medium': '中', 'low': '低', 'ok': 'OK'}.get(r.risk_level, '?')
        cat_short = {'fixed': '已修', 'suggested': '建议', 'clean': '通过', 'failed': '失败'}.get(r.category, '?')
        dur_str = format_ms(r.total_duration_ms) if r.total_duration_ms > 0 else 'N/A'
        line = (f"{r.file_name:<26} {risk_short:>6} {cat_short:>6} {r.errors:>5} "
                f"{r.warnings:>5} {r.high_risk:>6} {dur_str:>11} {r.total_words:>6}")
        lines.append(line)

    lines.append("")
    lines.append("=" * 80)

    for r in qa_results:
        if r.error:
            lines.append("")
            lines.append(f"[FAIL] {r.file_name}")
            lines.append(f"  错误: {r.error}")
            continue

        if r.risk_level == RISK_LEVEL_OK and not r.suggestions:
            continue

        lines.append("")
        lines.append(f"--- {r.file_name} [{r.risk_level_label}] [{r.category_label}] ---")

        if r.main_problems:
            lines.append(f"  主要问题: {'; '.join(r.main_problems)}")

        if r.issues:
            lines.append(f"  问题详情 ({len(r.issues)}):")
            shown = 0
            for issue in r.issues:
                if shown >= 8:
                    lines.append(f"    ... 还有{len(r.issues) - shown}个问题")
                    break
                icon = {'error': '[X]', 'warning': '[!]', 'info': '[i]'}.get(issue.severity, '[?]')
                lines.append(f"    {icon} #{issue.cue_index} {issue.message}")
                shown += 1

        if r.suggestions:
            lines.append(f"  修复建议 (优先级排序):")
            for i, s in enumerate(r.suggestions, 1):
                tag = {'high': '[HIGH]', 'medium': '[MED]', 'low': '[LOW]'}.get(s.priority, '[?]')
                lines.append(f"    {i}. {tag} [{s.fix_type_label}] {s.description}")
                if s.before:
                    before_parts = [f"{k}={v}" for k, v in s.before.items()]
                    lines.append(f"       修复前: {', '.join(before_parts)}")
                if s.after:
                    after_parts = [f"{k}={v}" for k, v in s.after.items()]
                    lines.append(f"       修复后: {', '.join(after_parts)}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("建议优先处理顺序:")
    lines.append("")

    priority_files = [r for r in qa_results if r.risk_level in (RISK_LEVEL_HIGH, RISK_LEVEL_MEDIUM)]
    priority_files.sort(key=lambda x: (0 if x.risk_level == RISK_LEVEL_HIGH else 1, -x.errors))

    if priority_files:
        for i, r in enumerate(priority_files, 1):
            lines.append(f"  {i}. {r.file_name} [{r.risk_level_label}]")
            if r.main_problems:
                lines.append(f"     问题: {'; '.join(r.main_problems)}")
            if r.suggestions:
                top = r.suggestions[0]
                lines.append(f"     首选修复: [{top.fix_type_label}] {top.description}")
    else:
        lines.append("  所有文件均通过检查，无优先处理项")

    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def qa_results_to_json(qa_results: List[QAFileResult]) -> str:
    data = {
        'summary_type': 'qa',
        'total_files': len(qa_results),
        'risk_counts': {},
        'category_counts': {},
        'files': []
    }

    for r in qa_results:
        data['risk_counts'][r.risk_level] = data['risk_counts'].get(r.risk_level, 0) + 1
        data['category_counts'][r.category] = data['category_counts'].get(r.category, 0) + 1

        file_entry = {
            'file_path': r.file_path,
            'file_name': r.file_name,
            'risk_level': r.risk_level,
            'risk_level_label': r.risk_level_label,
            'category': r.category,
            'category_label': r.category_label,
            'total_cues': r.total_cues,
            'total_duration_ms': r.total_duration_ms,
            'total_duration_str': format_ms(r.total_duration_ms) if r.total_duration_ms > 0 else '00:00:00.000',
            'total_words': r.total_words,
            'total_chars': r.total_chars,
            'errors': r.errors,
            'warnings': r.warnings,
            'high_risk': r.high_risk,
            'words_per_minute': round(r.words_per_minute, 1),
            'main_problems': r.main_problems,
            'issues': [
                {
                    'type': i.issue_type,
                    'severity': i.severity,
                    'cue_index': i.cue_index,
                    'message': i.message
                } for i in r.issues
            ],
            'suggestions': [
                {
                    'fix_type': s.fix_type,
                    'fix_type_label': s.fix_type_label,
                    'priority': s.priority,
                    'description': s.description,
                    'before': s.before,
                    'after': s.after
                } for s in r.suggestions
            ]
        }
        if r.error:
            file_entry['error'] = r.error

        data['files'].append(file_entry)

    return json.dumps(data, ensure_ascii=False, indent=2)
