import os
import sys
import click

from .__init__ import __version__
from .parser import parse_subtitle, find_subtitle_files
from .commands.scan import scan_subtitle, generate_scan_report
from .commands.shift import shift_subtitle
from .commands.split import split_subtitle
from .commands.merge import merge_subtitles
from .commands.stats import analyze_subtitle, generate_stats_report
from .utils import (
    parse_time_string, save_report, scan_issues_to_json,
    stats_to_json, process_output, generate_filename
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
@click.option('--report', 'report_path', type=click.Path(), help='问题报告输出路径')
@click.option('--report-format', type=click.Choice(['txt', 'json']), default='txt', help='报告格式')
def scan(input_path, recursive, max_chars, max_lines, min_gap, report_path, report_format):
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
    report = generate_scan_report(results)
    click.echo(report)

    if report_path:
        if report_format == 'json':
            content = scan_issues_to_json(results)
        else:
            content = report

        saved_path = save_report(content, report_path, report_format)
        click.echo(f"报告已保存到: {saved_path}")

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
def shift(input_path, offset_ms, recursive, start_time, end_time, cue_start,
          cue_end, output_dir, target_format, inplace, backup_method, backup_dir):
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
    click.echo("")

    for file_path in files:
        try:
            subfile = parse_subtitle(file_path)
            shifted = shift_subtitle(subfile, offset_ms, **options)
            output_path = process_output(
                shifted, output_dir, target_format, inplace, backup_method, backup_dir
            )
            click.echo(f"[OK] {os.path.basename(file_path)} -> {os.path.basename(output_path)}")
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
def split(input_path, method, max_duration, max_cues, max_lines, output_dir,
          target_format, backup_method):
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
    click.echo("")

    for file_path in files:
        try:
            subfile = parse_subtitle(file_path)
            parts = split_subtitle(subfile, **options)

            base_output_dir = output_dir or os.path.dirname(file_path)
            os.makedirs(base_output_dir, exist_ok=True)

            for part in parts:
                output_path = process_output(
                    part, base_output_dir, target_format, False, backup_method
                )
                click.echo(f"[OK] {os.path.basename(file_path)} -> {os.path.basename(output_path)} "
                           f"({len(part.cues)}条字幕)")
        except Exception as e:
            click.echo(f"[FAIL] {os.path.basename(file_path)}: 处理失败 - {str(e)}")


@main.command()
@click.argument('input_files', nargs=-1, type=click.Path(exists=True))
@click.option('--output', '-o', required=True, type=click.Path(), help='输出文件路径')
@click.option('--gap', default=0, help='文件间间隔(ms)')
@click.option('--renumber/--no-renumber', default=True, help='重新编号')
@click.option('--target-format', type=click.Choice(['srt', 'vtt']), help='目标格式')
def merge(input_files, output, gap, renumber, target_format):
    """合并多段字幕并重新编号"""
    if not input_files:
        click.echo("请指定至少一个输入文件")
        return

    click.echo(f"合并 {len(input_files)} 个字幕文件 -> {output}")
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
        merged = merge_subtitles(subfiles, output, renumber=renumber, gap_ms=gap)
        output_path = process_output(merged, None, target_format, False, 'none')
        click.echo("")
        click.echo(f"[OK] 合并完成: {output_path} ({len(merged.cues)}条字幕)")
    except Exception as e:
        click.echo(f"[FAIL] 合并失败: {str(e)}")


@main.command()
@click.argument('input_path', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True, help='递归扫描子目录')
@click.option('--wpm-threshold', default=200, help='高风险语速阈值(词/分钟)')
@click.option('--min-duration', default=300, help='最短时长阈值(ms)')
@click.option('--report', 'report_path', type=click.Path(), help='统计报告输出路径')
@click.option('--report-format', type=click.Choice(['txt', 'json']), default='txt', help='报告格式')
def stats(input_path, recursive, wpm_threshold, min_duration, report_path, report_format):
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
    report = generate_stats_report(stats_list)
    click.echo(report)

    if report_path:
        if report_format == 'json':
            content = stats_to_json(stats_list)
        else:
            content = report

        saved_path = save_report(content, report_path, report_format)
        click.echo(f"报告已保存到: {saved_path}")


if __name__ == '__main__':
    main()
