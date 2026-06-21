import sys
import os
sys.path.insert(0, '.')

print("=" * 70)
print("字幕处理工具 - 功能测试")
print("=" * 70)
print()

from subtool.parser import parse_subtitle
from subtool.writer import write_subtitle, backup_file
from subtool.commands.scan import scan_subtitle, generate_scan_report
from subtool.commands.shift import shift_subtitle
from subtool.commands.split import split_subtitle
from subtool.commands.merge import merge_subtitles
from subtool.commands.stats import analyze_subtitle, generate_stats_report
from subtool.utils import parse_time_string, save_report

TEST_DIR = 'examples'
OUTPUT_DIR = 'test_output'
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("[1/5] 测试 scan 命令...")
print("-" * 70)
subfile1 = parse_subtitle(os.path.join(TEST_DIR, 'sample1.srt'))
result1 = scan_subtitle(subfile1)
print(f"  sample1.srt: {result1['total_cues']}条字幕, {result1['total_issues']}个问题")
print(f"    错误: {result1['severity_counts']['error']}, 警告: {result1['severity_counts']['warning']}")
for issue in result1['issues'][:5]:
    print(f"    [{issue.severity.upper()}] {issue.message}")

subfile2 = parse_subtitle(os.path.join(TEST_DIR, 'sample2.srt'))
result2 = scan_subtitle(subfile2)
print(f"  sample2.srt: {result2['total_cues']}条字幕, {result2['total_issues']}个问题")

subfile3 = parse_subtitle(os.path.join(TEST_DIR, 'sample3.vtt'))
result3 = scan_subtitle(subfile3)
print(f"  sample3.vtt: {result3['total_cues']}条字幕, {result3['total_issues']}个问题")

scan_report = generate_scan_report([result1, result2, result3])
save_report(scan_report, os.path.join(OUTPUT_DIR, 'scan_report.txt'), 'txt')
print(f"  扫描报告已保存到: {OUTPUT_DIR}/scan_report.txt")
print()

print("[2/5] 测试 shift 命令...")
print("-" * 70)
subfile_shift = parse_subtitle(os.path.join(TEST_DIR, 'sample2.srt'))
original_start = subfile_shift.cues[0].start_ms
shifted = shift_subtitle(subfile_shift, 1000)
new_start = shifted.cues[0].start_ms
print(f"  偏移前: {original_start}ms, 偏移后: {new_start}ms (偏移+1000ms)")

subfile_shift2 = parse_subtitle(os.path.join(TEST_DIR, 'sample2.srt'))
shifted2 = shift_subtitle(subfile_shift2, -500, cue_start=2, cue_end=4)
print(f"  区间偏移(2-4条, -500ms):")
for cue in shifted2.cues:
    print(f"    #{cue.index}: {cue.start_ms}ms")
shift_path = write_subtitle(shifted, os.path.join(OUTPUT_DIR, 'sample2_shifted.srt'), 'srt')
print(f"  偏移后文件已保存到: {shift_path}")
print()

print("[3/5] 测试 split 命令...")
print("-" * 70)
subfile_split = parse_subtitle(os.path.join(TEST_DIR, 'sample2.srt'))
parts_cue = split_subtitle(subfile_split, method='cue_count', max_cues=2)
print(f"  按字幕条数拆分(每2条): 拆分为 {len(parts_cue)} 部分")
for i, part in enumerate(parts_cue):
    print(f"    部分{i+1}: {len(part.cues)}条字幕")
    split_path = write_subtitle(part, os.path.join(OUTPUT_DIR, f'sample2_cue_{i+1}.srt'), 'srt')

subfile_split2 = parse_subtitle(os.path.join(TEST_DIR, 'sample2.srt'))
parts_speaker = split_subtitle(subfile_split2, method='speaker')
print(f"  按说话人拆分: 拆分为 {len(parts_speaker)} 部分")
for part in parts_speaker:
    speakers = set(cue.speaker for cue in part.cues if cue.speaker)
    print(f"    {os.path.basename(part.path)}: {len(part.cues)}条, 说话人: {speakers}")
    split_path = write_subtitle(part, os.path.join(OUTPUT_DIR, os.path.basename(part.path)), 'srt')
print()

print("[4/5] 测试 merge 命令...")
print("-" * 70)
files_to_merge = [
    parse_subtitle(os.path.join(TEST_DIR, 'sample2.srt')),
    parse_subtitle(os.path.join(TEST_DIR, 'sample3.vtt'))
]
merged = merge_subtitles(files_to_merge, os.path.join(OUTPUT_DIR, 'merged.srt'), gap_ms=2000)
print(f"  合并 {len(files_to_merge)} 个文件，共 {len(merged.cues)} 条字幕")
merge_path = write_subtitle(merged, os.path.join(OUTPUT_DIR, 'merged.srt'), 'srt')
print(f"  合并后文件已保存到: {merge_path}")
print()

print("[5/5] 测试 stats 命令...")
print("-" * 70)
stats_list = []
for fname in ['sample1.srt', 'sample2.srt', 'sample3.vtt']:
    subfile = parse_subtitle(os.path.join(TEST_DIR, fname))
    stat = analyze_subtitle(subfile, wpm_threshold=150)
    stats_list.append(stat)
    print(f"  {fname}:")
    print(f"    字幕数: {stat.total_cues}")
    print(f"    总时长: {stat.total_duration_ms / 1000:.1f}秒")
    print(f"    总字数: {stat.total_words}词 / {stat.total_chars}字符")
    print(f"    语速: {stat.words_per_minute:.1f}词/分钟")
    print(f"    高风险句子: {len(stat.high_risk_sentences)}个")
    if stat.speaker_stats:
        print(f"    说话人: {list(stat.speaker_stats.keys())}")

stats_report = generate_stats_report(stats_list)
save_report(stats_report, os.path.join(OUTPUT_DIR, 'stats_report.txt'), 'txt')
print(f"  统计报告已保存到: {OUTPUT_DIR}/stats_report.txt")
print()

print("=" * 70)
print("所有测试完成！输出文件保存在 test_output 目录中。")
print("=" * 70)
