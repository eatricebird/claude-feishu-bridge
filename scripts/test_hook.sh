#!/bin/bash
# 测试 PermissionRequest Hook

TEST_INPUT='{
  "session_id": "test-session-123",
  "tool_name": "Bash",
  "tool_input": {
    "command": "echo Hello World",
    "description": "Test echo command"
  },
  "permission_suggestions": []
}'

echo "Testing PermissionRequest Hook..."
echo "Input: $TEST_INPUT"

# 通过管道传递输入到 hook 脚本
echo "$TEST_INPUT" | python3 src/hooks/permission_request.py

echo ""
echo "Hook test completed."
