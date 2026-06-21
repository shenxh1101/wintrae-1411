import sys
sys.path.insert(0, '.')
from subtool.cli import main

sys.argv = ['subtool', 'scan', 'examples/sample1.srt']
try:
    main()
except SystemExit as e:
    print(f"Exit code: {e.code}")
