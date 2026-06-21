# SubTool - 字幕批量检查和整理工具

一个为字幕翻译人员设计的命令行工具，提供字幕文件的批量检查、整理和分析功能。

## 功能特性

### 五类核心命令

1. **scan** - 检查字幕质量
   - 时间轴重叠检测
   - 空字幕检测
   - 过长行检测
   - 编号断裂检测
   - 无效时长检测

2. **shift** - 时间轴偏移
   - 整体前后移动（毫秒）
   - 按时间区间调整
   - 按字幕编号区间调整

3. **split** - 拆分字幕文件
   - 按时长拆分
   - 按字幕条数拆分
   - 按行数拆分
   - 按说话人标记拆分

4. **merge** - 合并字幕文件
   - 多文件合并
   - 自动重新编号
   - 可设置文件间间隔

5. **stats** - 统计分析
   - 总时长统计
   - 字数统计
   - 每分钟字数（语速）
   - 高风险句子识别
   - 说话人统计

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 安装包（可选）
pip install -e .
```

## 快速开始

### 1. 扫描字幕文件

```bash
# 扫描单个文件
python subtool.py scan examples/sample1.srt

# 扫描整个目录
python subtool.py scan ./subtitles

# 扫描并生成报告
python subtool.py scan ./subtitles --report scan_report.txt
```

### 2. 时间轴偏移

```bash
# 整体向后偏移 500ms
python subtool.py shift subtitle.srt 500

# 整体向前偏移 1秒
python subtool.py shift subtitle.srt -1000

# 只调整第 5-10 条字幕，向后偏移 200ms
python subtool.py shift subtitle.srt 200 --cue-start 5 --cue-end 10

# 按时间区间调整
python subtool.py shift subtitle.srt 300 --start-time 00:01:00 --end-time 00:05:00

# 原地修改并备份
python subtool.py shift subtitle.srt 500 --inplace --backup copy
```

### 3. 拆分字幕

```bash
# 按字幕条数拆分（每100条
python subtool.py split subtitle.srt --method cue_count --max-cues 100

# 按时长拆分（每10分钟）
python subtool.py split subtitle.srt --method duration --max-duration 600

# 按说话人拆分
python subtool.py split subtitle.srt --method speaker

# 按行数拆分
python subtool.py split subtitle.srt --method line_count --max-lines 200
```

### 4. 合并字幕

```bash
# 合并多个文件
python subtool.py merge part1.srt part2.srt -o merged.srt

# 合并并设置间隔
python subtool.py merge *.srt -o merged.srt --gap 1000

# 不重新编号
python subtool.py merge part1.srt part2.srt -o merged.srt --no-renumber
```

### 5. 统计分析

```bash
# 统计单个文件
python subtool.py stats subtitle.srt

# 统计目录并生成JSON报告
python subtool.py stats ./subtitles --report stats_report.json --report-format json

# 自定义语速阈值
python subtool.py stats subtitle.srt --wpm-threshold 180
```

## 常用参数说明

### 通用参数

| 参数 | 说明 |
|------|------|
| `--target-format` | 输出格式: srt, vtt |
| `--output-dir` | 输出目录 |
| `--inplace` | 原地修改 |
| `--backup` | 备份方式: copy, move, none |
| `--backup-dir` | 备份目录 |
| `--recursive/--no-recursive` | 是否递归扫描子目录 |

### 命令参数

#### scan
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--max-chars` | 每行最大字符数 | 40 |
| `--max-lines` | 每条最大行数 | 2 |
| `--min-gap` | 最小间隔(ms) | 0 |
| `--report` | 报告路径 | - |
| `--report-format` | 报告格式: txt, json | txt |

#### shift
| 参数 | 说明 |
|------|------|
| `--start-time` | 区间开始时间 |
| `--end-time` | 区间结束时间 |
| `--cue-start` | 起始字幕编号 |
| `--cue-end` | 结束字幕编号 |

#### split
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--method` | 拆分方式 | cue_count |
| `--max-duration` | 最大时长(秒) | 600 |
| `--max-cues` | 最大字幕数 | 100 |
| `--max-lines` | 最大行数 | 200 |

#### merge
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o, --output` | 输出文件 | 必填 |
| `--gap` | 文件间隔(ms) | 0 |
| `--renumber/--no-renumber` | 是否重新编号 | 是 |

#### stats
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--wpm-threshold` | 语速阈值 | 200 |
| `--min-duration` | 最小时长(ms) | 300 |

## 支持的格式

- SRT (.srt)
- WebVTT (.vtt)

## 项目结构

```
subtool/
├── __init__.py
├── __main__.py
├── cli.py           # CLI入口
├── models.py        # 数据模型
├── parser.py        # 字幕解析
├── writer.py        # 字幕写入
├── utils.py         # 工具函数
└── commands/
    ├── __init__.py
    ├── scan.py     # 扫描检查
    ├── shift.py    # 时间偏移
    ├── split.py    # 文件拆分
    ├── merge.py   # 文件合并
    └── stats.py  # 统计分析
```

## 示例

```bash
# 完整工作流程示例：

# 1. 先扫描所有字幕检查问题
python subtool.py scan ./subtitles --report issues.txt

# 2. 调整时间轴整体偏移
python subtool.py shift ./subtitles 500 --output-dir ./fixed

# 3. 统计分析
python subtool.py stats ./fixed --report stats.txt

# 4. 合并多段字幕
python subtool.py merge ./fixed/*.srt -o final.srt
```

## 许可证

MIT License
