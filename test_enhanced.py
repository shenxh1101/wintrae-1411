import sys
import os
sys.path.insert(0, '.')

print("=" * 70)
print("字幕处理工具 - 完善功能测试")
print("=" * 70)
print()

from subtool.parser import parse_subtitle, parse_srt, parse_vtt
from subtool.writer import write_subtitle
from subtool.commands.scan import scan_subtitle, generate_scan_report
from subtool.commands.shift import shift_subtitle
from subtool.commands.split import split_subtitle
from subtool.commands.merge import merge_subtitles
from subtool.commands.stats import analyze_subtitle, generate_stats_report
from subtool.utils import (
    generate_scan_summary, generate_scan_summary_report,
    generate_stats_summary, generate_stats_summary_report,
    build_output_path, process_output, format_ms
)

TEST_DIR = 'examples'
OUTPUT_DIR = 'test_output_v2'
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("[测试 1] VTT 解析 - 完整格式支持")
print("-" * 70)
vtt_file = os.path.join(TEST_DIR, 'sample3_complete.vtt')
vtt_sub = parse_subtitle(vtt_file)
print(f"  文件: {os.path.basename(vtt_file)}")
print(f"  格式: {vtt_sub.format}")
print(f"  字幕条数: {len(vtt_sub.cues)}")
print()
print("  前5条字幕:")
for i, cue in enumerate(vtt_sub.cues[:5]):
    text_preview = cue.text.replace('\n', ' | ')[:50] if cue.text else "(空)"
    print(f"    #{cue.index} [{format_ms(cue.start_ms)} -> {format_ms(cue.end_ms)}] {text_preview}")

print()
print("  空字幕检查:")
empty_count = sum(1 for cue in vtt_sub.cues if cue.is_empty)
print(f"    空字幕数量: {empty_count}")
for cue in vtt_sub.cues:
    if cue.is_empty:
        print(f"      #{cue.index} [{format_ms(cue.start_ms)} -> {format_ms(cue.end_ms)}] (空)")

print()
print("[测试 2] SRT 空字幕解析 - 空字幕不应消失")
print("-" * 70)
srt_empty = os.path.join(TEST_DIR, 'sample1_empty.srt')
srt_sub = parse_subtitle(srt_empty)
print(f"  文件: {os.path.basename(srt_empty)}")
print(f"  字幕条数: {len(srt_sub.cues)}")
print()

empty_cues = [cue for cue in srt_sub.cues if cue.is_empty]
print(f"  空字幕数量: {len(empty_cues)}")
for cue in empty_cues:
    print(f"    #{cue.index} [{format_ms(cue.start_ms)} -> {format_ms(cue.end_ms)}] (空字幕)")

print()
print("[测试 3] scan 命令 - 空字幕和VTT检测")
print("-" * 70)

files_to_scan = [
    os.path.join(TEST_DIR, 'sample1_empty.srt'),
    os.path.join(TEST_DIR, 'sample2.srt'),
    os.path.join(TEST_DIR, 'sample3_complete.vtt'),
]

scan_results = []
for f in files_to_scan:
    sub = parse_subtitle(f)
    result = scan_subtitle(sub)
    scan_results.append(result)
    print(f"  {os.path.basename(f)}:")
    print(f"    字幕数: {result['total_cues']}")
    print(f"    问题数: {result['total_issues']}")
    print(f"    错误: {result['severity_counts']['error']}, 警告: {result['severity_counts']['warning']}")
    empty_issues = [i for i in result['issues'] if i.type == 'empty']
    print(f"    空字幕问题: {len(empty_issues)}")

print()
print("[测试 4] 批处理汇总 - scan 汇总报告")
print("-" * 70)
scan_summary = generate_scan_summary(scan_results)
scan_summary_report = generate_scan_summary_report(scan_summary)
print(scan_summary_report)

scan_summary_path = os.path.join(OUTPUT_DIR, 'scan_summary.txt')
with open(scan_summary_path, 'w', encoding='utf-8') as f:
    f.write(scan_summary_report)
print(f"  汇总报告已保存: {scan_summary_path}")

import json
scan_summary_json = os.path.join(OUTPUT_DIR, 'scan_summary.json')
with open(scan_summary_json, 'w', encoding='utf-8') as f:
    json.dump(scan_summary, f, ensure_ascii=False, indent=2)
print(f"  JSON汇总已保存: {scan_summary_json}")

print()
print("[测试 5] 批处理汇总 - stats 汇总报告")
print("-" * 70)

stats_list = []
for f in files_to_scan:
    sub = parse_subtitle(f)
    stat = analyze_subtitle(sub, wpm_threshold=150)
    stats_list.append(stat)

stats_summary = generate_stats_summary(stats_list)
stats_summary_report = generate_stats_summary_report(stats_summary)
print(stats_summary_report)

stats_summary_path = os.path.join(OUTPUT_DIR, 'stats_summary.txt')
with open(stats_summary_path, 'w', encoding='utf-8') as f:
    f.write(stats_summary_report)
print(f"  汇总报告已保存: {stats_summary_path}")

stats_summary_json = os.path.join(OUTPUT_DIR, 'stats_summary.json')
with open(stats_summary_json, 'w', encoding='utf-8') as f:
    json.dump(stats_summary, f, ensure_ascii=False, indent=2)
print(f"  JSON汇总已保存: {stats_summary_json}")

print()
print("[测试 6] 输出命名规则 - 后缀、前缀、日期子目录")
print("-" * 70)

sample_file = os.path.join(TEST_DIR, 'sample2.srt')
sample_sub = parse_subtitle(sample_file)

print("  测试 build_output_path:")
path1 = build_output_path(sample_file, suffix='_shifted')
print(f"    加后缀: {os.path.relpath(path1, start='.')}")

path2 = build_output_path(sample_file, prefix='fixed_')
print(f"    加前缀: {os.path.relpath(path2, start='.')}")

path3 = build_output_path(sample_file, output_dir=OUTPUT_DIR, suffix='_v2')
print(f"    指定目录+后缀: {os.path.relpath(path3, start='.')}")

path4 = build_output_path(sample_file, output_dir=OUTPUT_DIR, suffix='_shift', use_date_subdir=True)
print(f"    日期子目录: {os.path.relpath(path4, start='.')}")

path5 = build_output_path(sample_file, target_format='vtt', suffix='_converted')
print(f"    格式转换: {os.path.relpath(path5, start='.')}")

print()
print("  测试 process_output 实际写入:")
shifted_sub = shift_subtitle(sample_sub, 1000)

out1 = process_output(shifted_sub, output_dir=OUTPUT_DIR, suffix='_shifted_1000ms')
print(f"    shift+后缀: {os.path.relpath(out1, start='.')}")

out2 = process_output(shifted_sub, output_dir=OUTPUT_DIR, suffix='_dated', use_date_subdir=True)
print(f"    shift+日期子目录: {os.path.relpath(out2, start='.')}")

print()
print("[测试 7] VTT 写回一致性")
print("-" * 70)
vtt_original = parse_subtitle(os.path.join(TEST_DIR, 'sample3_complete.vtt'))
vtt_out_path = os.path.join(OUTPUT_DIR, 'sample3_written_back.vtt')
write_subtitle(vtt_original, vtt_out_path, 'vtt')
vtt_reparsed = parse_subtitle(vtt_out_path)
print(f"  原始条数: {len(vtt_original.cues)}")
print(f"  写回后条数: {len(vtt_reparsed.cues)}")
print(f"  一致: {len(vtt_original.cues) == len(vtt_reparsed.cues)}")

if len(vtt_original.cues) == len(vtt_reparsed.cues):
    all_match = True
    for i in range(len(vtt_original.cues)):
        orig = vtt_original.cues[i]
        reparsed = vtt_reparsed.cues[i]
        if orig.start_ms != reparsed.start_ms or orig.end_ms != reparsed.end_ms:
            all_match = False
            print(f"    第{i+1}条时间不匹配: {orig.start_ms} vs {reparsed.start_ms}")
    print(f"  时间轴匹配: {all_match}")

print()
print("[测试 8] split 和 merge 的命名规则")
print("-" * 70)
sample2_sub = parse_subtitle(os.path.join(TEST_DIR, 'sample2.srt'))

parts = split_subtitle(sample2_sub, method='cue_count', max_cues=2)
print(f"  拆分 {len(parts)} 部分:")
for i, part in enumerate(parts):
    out_path = process_output(part, output_dir=OUTPUT_DIR, suffix='_split', prefix='p')
    print(f"    {i+1}. {os.path.relpath(out_path, start='.')} ({len(part.cues)}条)")

print()
print("[测试 9] 合并文件命名规则")
print("-" * 70)
parts_for_merge = []
for i, part in enumerate(parts[:2]):
    parts_for_merge.append(part)

merged = merge_subtitles(parts_for_merge, os.path.join(OUTPUT_DIR, 'remerged.srt'))
merged_out = process_output(merged, output_dir=OUTPUT_DIR, suffix='_merged')
print(f"  合并输出: {os.path.relpath(merged_out, start='.')}")
print(f"  合并后字幕数: {len(merged.cues)}")

print()
print("=" * 70)
print("所有测试完成！输出文件保存在 test_output_v2 目录中。")
print("=" * 70)
