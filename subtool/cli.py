import os
import sys
import click

from .__init__ import __version__
from .parser import parse_subtitle, find_subtitle_files
from .writer import write_subtitle
from .models import SubtitleFile
from .commands.scan import scan_subtitle, generate_scan_report
from .commands.shift import shift_subtitle
from .commands.split import split_subtitle
from .commands.merge import merge_subtitles
from .commands.stats import analyze_subtitle, generate_stats_report
from .commands.batch import (
    load_config, validate_config, execute_batch,
    generate_batch_report, batch_summary_to_json
)
from .utils import (
    parse_time_string, save_report, scan_issues_to_json,
    stats_to_json, process_output, generate_filename,
    generate_scan_summary, generate_scan_summary_report,
    generate_stats_summary, generate_stats_summary_report,
    build_output_path
)


def get_input_files(input_path, recursive=True):
    if os.path.isfile(input_path):
        return [input_path]
    elif os.path.isdir(input_path):
        return find_subtitle_files(input_path, recursive)
    else:
        click.echo(f"错误: 路径不存在 - {input_path}", err=True)
        sys.exit(1)


@click.group()
@click.version_option(__version__, prog_name='subtool')
@click.option('--verbose', '-v', is_flag=True, help='显示详细输出')
def main(verbose):
    """字幕批量检查和整理工具 - 支持 scan、shift、split、merge、stats 五类命令"""
    pass


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True, help='递归扫描子目录')
@click.option('--max-chars', default=40, help='每行最大字符数')
@click.option('--max-lines', default=2, help='每条字幕最大行数')
@click.option('--min-gap', default=0, help='最小间隔时间(ms)')
@click.option('--report', 'report_path', type=click.Path(), help='详细报告输出路径')
@click.option('--summary', 'summary_path', type=click.Path(), help='汇总报告输出路径')
@click.option('--report-format', type=click.Choice(['txt', 'json']), default='txt', help='报告格式')
@click.option('--summary-only', is_flag=True, help='只显示汇总报告，不显示详细报告')
def scan(input_path, recursive, max_chars, max_lines, min_gap, report_path,
         summary_path, report_format, summary_only):
    """检查时间轴重叠、空字幕、过长行和编号断裂"""
    files = get_input_files(input_path, recursive)

    if not files:
        click.echo("未找到字幕文件")
        return

    click.echo(f"扫描 {len(files)} 个字幕文件...")
    click.echo("")

    results = []
    for file_path in files:
        try:
            subfile = parse_subtitle(file_path)
            result = scan_subtitle(
                subfile,
                max_chars_per_line=max_chars,
                max_lines=max_lines,
                min_gap_ms=min_gap
            )
            results.append(result)

            status = "OK" if not result["has_errors"] else "FAIL"
            click.echo(f"[{status}] {os.path.basename(file_path)}: "
                       f"{result['total_cues']}条字幕, "
                       f"{result['total_issues']}个问题 "
                       f"(错误:{result['severity_counts']['error']}, "
                       f"警告:{result['severity_counts']['warning']})")
        except Exception as e:
            click.echo(f"[FAIL] {os.path.basename(file_path)}: 解析失败 - {str(e)}")

    click.echo("")

    summary = generate_scan_summary(results)

    if not summary_only:
        report = generate_scan_report(results)
        click.echo(report)

    summary_report = generate_scan_summary_report(summary)
    if summary_only:
        click.echo(summary_report)
    else:
        click.echo("")
        click.echo(summary_report)

    if report_path:
        if report_format == 'json':
            content = scan_issues_to_json(results)
        else:
            content = generate_scan_report(results)

        saved_path = save_report(content, report_path, report_format)
        click.echo(f"详细报告已保存到: {saved_path}")

    if summary_path:
        if report_format == 'json':
            content = __import__('json').dumps(summary, ensure_ascii=False, indent=2)
        else:
            content = summary_report

        saved_path = save_report(content, summary_path, report_format)
        click.echo(f"汇总报告已保存到: {saved_path}")

    total_errors = sum(r["severity_counts"]["error"] for r in results)
    if total_errors > 0:
        sys.exit(1)


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.argument('offset_ms', type=int)
@click.option('--recursive/--no-recursive', default=True, help='递归扫描子目录')
@click.option('--start-time', help='区间开始时间 (HH:MM:SS.mmm)')
@click.option('--end-time', help='区间结束时间 (HH:MM:SS.mmm)')
@click.option('--cue-start', type=int, help='起始字幕编号')
@click.option('--cue-end', type=int, help='结束字幕编号')
@click.option('--output-dir', type=click.Path(), help='输出目录')
@click.option('--target-format', type=click.Choice(['srt', 'vtt']), help='目标格式')
@click.option('--inplace', is_flag=True, help='原地修改')
@click.option('--backup', 'backup_method', type=click.Choice(['copy', 'move', 'none']),
              default='copy', help='备份方式')
@click.option('--backup-dir', type=click.Path(), help='备份目录')
@click.option('--suffix', default='', help='文件名后缀')
@click.option('--prefix', default='', help='文件名前缀')
@click.option('--date-subdir', is_flag=True, help='按日期创建子目录')
@click.option('--overwrite', is_flag=True, help='允许覆盖已有文件')
def shift(input_path, offset_ms, recursive, start_time, end_time, cue_start,
          cue_end, output_dir, target_format, inplace, backup_method, backup_dir,
          suffix, prefix, date_subdir, overwrite):
    """按毫秒整体前后移动或只调整指定区间"""
    files = get_input_files(input_path, recursive)

    if not files:
        click.echo("未找到字幕文件")
        return

    options = {}
    if start_time:
        options['start_ms'] = parse_time_string(start_time)
    if end_time:
        options['end_ms'] = parse_time_string(end_time)
    if cue_start:
        options['cue_start'] = cue_start
    if cue_end:
        options['cue_end'] = cue_end

    direction = "向后" if offset_ms > 0 else "向前"
    click.echo(f"将 {len(files)} 个字幕文件 {direction} 偏移 {abs(offset_ms)}ms")
    if any([start_time, end_time, cue_start, cue_end]):
        click.echo("应用区间限制")
    if suffix or prefix:
        click.echo(f"命名规则: 前缀='{prefix}', 后缀='{suffix}'")
    if date_subdir:
        click.echo("输出到日期子目录")
    if overwrite:
        click.echo("允许覆盖已有文件")
    click.echo("")

    for file_path in files:
        try:
            subfile = parse_subtitle(file_path)
            shifted = shift_subtitle(subfile, offset_ms, **options)
            output_path = process_output(
                shifted, output_dir, target_format, inplace, backup_method,
                backup_dir, suffix=suffix, prefix=prefix, use_date_subdir=date_subdir,
                allow_overwrite=overwrite
            )
            click.echo(f"[OK] {os.path.basename(file_path)} -> {os.path.relpath(output_path, start=output_dir or '.')}")
        except Exception as e:
            click.echo(f"[FAIL] {os.path.basename(file_path)}: 处理失败 - {str(e)}")


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.option('--method', type=click.Choice(['duration', 'cue_count', 'line_count', 'speaker']),
              default='cue_count', help='拆分方式')
@click.option('--max-duration', default=600, help='最大时长(秒), duration方式使用')
@click.option('--max-cues', default=100, help='最大字幕条数, cue_count方式使用')
@click.option('--max-lines', default=200, help='最大行数, line_count方式使用')
@click.option('--output-dir', type=click.Path(), help='输出目录')
@click.option('--target-format', type=click.Choice(['srt', 'vtt']), help='目标格式')
@click.option('--backup', 'backup_method', type=click.Choice(['copy', 'move', 'none']),
              default='none', help='备份方式')
@click.option('--suffix', default='', help='文件名后缀')
@click.option('--prefix', default='', help='文件名前缀')
@click.option('--date-subdir', is_flag=True, help='按日期创建子目录')
@click.option('--overwrite', is_flag=True, help='允许覆盖已有文件')
def split(input_path, method, max_duration, max_cues, max_lines, output_dir,
          target_format, backup_method, suffix, prefix, date_subdir, overwrite):
    """按时长、行数或说话人标记拆分文件"""
    files = get_input_files(input_path, recursive=False)

    if not files:
        click.echo("未找到字幕文件")
        return

    options = {'method': method}
    if method == 'duration':
        options['max_duration_ms'] = max_duration * 1000
    elif method == 'cue_count':
        options['max_cues'] = max_cues
    elif method == 'line_count':
        options['max_lines'] = max_lines

    click.echo(f"使用 {method} 方式拆分 {len(files)} 个字幕文件")
    if suffix or prefix:
        click.echo(f"命名规则: 前缀='{prefix}', 后缀='{suffix}'")
    if date_subdir:
        click.echo("输出到日期子目录")
    if overwrite:
        click.echo("允许覆盖已有文件")
    click.echo("")

    for file_path in files:
        try:
            subfile = parse_subtitle(file_path)
            parts = split_subtitle(subfile, **options)

            for part in parts:
                final_path = process_output(
                    part, output_dir, target_format, False, backup_method,
                    suffix=suffix, prefix=prefix, use_date_subdir=date_subdir,
                    allow_overwrite=overwrite
                )
                click.echo(f"[OK] {os.path.basename(file_path)} -> {os.path.relpath(final_path, start=output_dir or '.')} "
                           f"({len(part.cues)}条字幕)")
        except Exception as e:
            click.echo(f"[FAIL] {os.path.basename(file_path)}: 处理失败 - {str(e)}")


@main.command()
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.option('--output', '-o', required=True, type=click.Path(), help='输出文件路径')
@click.option('--gap', default=0, help='文件间间隔(ms)')
@click.option('--renumber/--no-renumber', default=True, help='重新编号')
@click.option('--target-format', type=click.Choice(['srt', 'vtt']), help='目标格式')
@click.option('--suffix', default='', help='文件名后缀')
@click.option('--prefix', default='', help='文件名前缀')
@click.option('--date-subdir', is_flag=True, help='按日期创建子目录')
@click.option('--overwrite', is_flag=True, help='允许覆盖已有文件')
def merge(input_files, output, gap, renumber, target_format, suffix, prefix, date_subdir, overwrite):
    """合并多段字幕并重新编号"""
    if not input_files:
        click.echo("请指定至少一个输入文件")
        return

    final_path = build_output_path(
        output,
        suffix=suffix,
        prefix=prefix,
        use_date_subdir=date_subdir,
        target_format=target_format,
        allow_overwrite=overwrite
    )

    click.echo(f"合并 {len(input_files)} 个字幕文件 -> {final_path}")
    if suffix or prefix:
        click.echo(f"命名规则: 前缀='{prefix}', 后缀='{suffix}'")
    if date_subdir:
        click.echo("输出到日期子目录")
    if overwrite:
        click.echo("允许覆盖已有文件")
    click.echo("")

    subfiles = []
    for file_path in input_files:
        try:
            subfile = parse_subtitle(file_path)
            subfiles.append(subfile)
            click.echo(f"  读取: {os.path.basename(file_path)} ({len(subfile.cues)}条)")
        except Exception as e:
            click.echo(f"[FAIL] {os.path.basename(file_path)}: 读取失败 - {str(e)}")
            return

    if not subfiles:
        click.echo("没有有效的字幕文件可以合并")
        return

    try:
        merged = merge_subtitles(subfiles, final_path, renumber=renumber, gap_ms=gap)
        os.makedirs(os.path.dirname(os.path.abspath(final_path)) or '.', exist_ok=True)
        written_path = write_subtitle(merged, final_path, target_format)
        click.echo("")
        click.echo(f"[OK] 合并完成: {written_path} ({len(merged.cues)}条字幕)")
    except Exception as e:
        click.echo(f"[FAIL] 合并失败: {str(e)}")


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True, help='递归扫描子目录')
@click.option('--wpm-threshold', default=200, help='高风险语速阈值(词/分钟)')
@click.option('--min-duration', default=300, help='最短时长阈值(ms)')
@click.option('--report', 'report_path', type=click.Path(), help='详细报告输出路径')
@click.option('--summary', 'summary_path', type=click.Path(), help='汇总报告输出路径')
@click.option('--report-format', type=click.Choice(['txt', 'json']), default='txt', help='报告格式')
@click.option('--summary-only', is_flag=True, help='只显示汇总报告，不显示详细报告')
def stats(input_path, recursive, wpm_threshold, min_duration, report_path,
          summary_path, report_format, summary_only):
    """输出总时长、字数、每分钟字数和高风险句子"""
    files = get_input_files(input_path, recursive)

    if not files:
        click.echo("未找到字幕文件")
        return

    click.echo(f"分析 {len(files)} 个字幕文件...")
    click.echo("")

    stats_list = []
    for file_path in files:
        try:
            subfile = parse_subtitle(file_path)
            stat = analyze_subtitle(
                subfile,
                wpm_threshold=wpm_threshold,
                min_duration_ms=min_duration
            )
            stats_list.append(stat)
            click.echo(f"[OK] {os.path.basename(file_path)}: "
                       f"{stat.total_cues}条, "
                       f"{stat.total_words}词, "
                       f"{stat.words_per_minute:.1f}词/分钟, "
                       f"{len(stat.high_risk_sentences)}个高风险")
        except Exception as e:
            click.echo(f"[FAIL] {os.path.basename(file_path)}: 解析失败 - {str(e)}")

    click.echo("")

    summary = generate_stats_summary(stats_list)

    if not summary_only:
        report = generate_stats_report(stats_list)
        click.echo(report)

    summary_report = generate_stats_summary_report(summary)
    if summary_only:
        click.echo(summary_report)
    else:
        click.echo("")
        click.echo(summary_report)

    if report_path:
        if report_format == 'json':
            content = stats_to_json(stats_list)
        else:
            content = generate_stats_report(stats_list)

        saved_path = save_report(content, report_path, report_format)
        click.echo(f"详细报告已保存到: {saved_path}")

    if summary_path:
        if report_format == 'json':
            content = __import__('json').dumps(summary, ensure_ascii=False, indent=2)
        else:
            content = summary_report

        saved_path = save_report(content, summary_path, report_format)
        click.echo(f"汇总报告已保存到: {saved_path}")


@main.command()
@click.argument('config_path', type=click.Path(exists=True))
@click.option('--dry-run', is_flag=True, help='预览模式，不实际写入文件')
@click.option('--report', 'report_path', type=click.Path(), help='批处理报告输出路径')
@click.option('--report-format', type=click.Choice(['txt', 'json']), default='txt', help='报告格式')
@click.option('--verbose', '-v', is_flag=True, help='显示详细输出')
def batch(config_path, dry_run, report_path, report_format, verbose):
    """使用配置文件批量执行 scan/shift/split/merge/stats 任务"""
    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"[FAIL] 配置文件加载失败: {str(e)}", err=True)
        sys.exit(1)

    errors = validate_config(config)
    if errors:
        click.echo("[FAIL] 配置文件验证失败:", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)

    click.echo(f"加载配置: {config_path}")
    if dry_run:
        click.echo("模式: 预览 (dry-run)")
    click.echo("")

    if dry_run:
        from .commands.batch import get_input_files_from_config
        files = get_input_files_from_config(config)

        click.echo(f"待处理文件: {len(files)} 个")
        for f in files[:10]:
            click.echo(f"  - {os.path.basename(f)}")
        if len(files) > 10:
            click.echo(f"  ... 还有 {len(files) - 10} 个文件")
        click.echo("")

        actions = config.get('actions', [])
        click.echo(f"待执行动作: {len(actions)} 个")
        for i, action in enumerate(actions):
            click.echo(f"  {i+1}. {action['type']}")
            if 'params' in action:
                for k, v in action['params'].items():
                    click.echo(f"     {k}: {v}")
        click.echo("")

        output_cfg = config.get('output', {})
        naming = output_cfg.get('naming', {})
        click.echo("输出配置:")
        if output_cfg.get('dir'):
            click.echo(f"  输出目录: {output_cfg['dir']}")
        if naming.get('prefix'):
            click.echo(f"  前缀: {naming['prefix']}")
        if naming.get('suffix'):
            click.echo(f"  后缀: {naming['suffix']}")
        if naming.get('date_subdir'):
            click.echo(f"  日期子目录: 是")
        click.echo(f"  覆盖已有文件: {'是' if output_cfg.get('overwrite') else '否'}")
        click.echo("")

        click.echo("[INFO] 预览模式: 不会实际修改文件")
        return

    summary = execute_batch(config, verbose=verbose)

    report = generate_batch_report(summary, config)
    click.echo(report)

    if report_path:
        if report_format == 'json':
            content = batch_summary_to_json(summary, config)
        else:
            content = report

        saved_path = save_report(content, report_path, report_format)
        click.echo(f"批处理报告已保存到: {saved_path}")

    if summary.failed_files > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
