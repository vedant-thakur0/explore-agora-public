#!/usr/bin/env python3
"""PreToolUse hook that blocks Read/Grep access to the hooks and .env directory."""

import json
import os
import sys


def main():
    event = json.load(sys.stdin)
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    if tool_name in ("Read", "Grep", "Glob"):
        target = tool_input.get("file_path") or tool_input.get("path") or ""
        if os.path.basename(os.path.abspath(target)) == ".env":
            json.dump({
                "decision": "block",
                "reason": "Access to .env files is not permitted.",
            }, sys.stdout)
            return

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if ".env" in command:
            json.dump({
                "decision": "block",
                "reason": "Access to .env files is not permitted.",
            }, sys.stdout)
            return
    json.dump({"decision": "approve"}, sys.stdout)


if __name__ == "__main__":
    main()
