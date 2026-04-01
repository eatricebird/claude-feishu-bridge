#!/usr/bin/env python3
"""
Claude Code AskUserQuestion PreToolUse Hook

返回 {} 让终端正常显示选择框。
飞书交互由 PermissionRequest hook 处理。
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    print(json.dumps({}))
    sys.exit(0)


if __name__ == "__main__":
    main()
