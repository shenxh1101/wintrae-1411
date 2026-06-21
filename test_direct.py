import sys
sys.path.insert(0, '.')

print("Testing direct import...")
from subtool.parser import parse_subtitle
from subtool.commands.scan import scan_subtitle, generate_scan_report

print("Parsing subtitle file...")
subfile = parse_subtitle('examples/sample1.srt')
print(f"Found {len(subfile.cues)} cues")
for cue in subfile.cues[:3]:
    print(f"  #{cue.index}: {cue.start_ms} -> {cue.end_ms}: {cue.text[:30]}...")

print("\nScanning...")
result = scan_subtitle(subfile)
print(f"Total issues: {result['total_issues']}")
print(f"Errors: {result['severity_counts']['error']}")
print(f"Warnings: {result['severity_counts']['warning']}")

print("\nIssues:")
for issue in result['issues']:
    print(f"  [{issue.severity}] {issue.type}: {issue.message}")

print("\nGenerating report...")
report = generate_scan_report([result])
print(report)
