import sys

file_path = "upgrade-frontend/src/lib/store/workflow.ts"
with open(file_path, "r") as f:
    content = f.read()

old_str = "const eventSource = new EventSource(`${API_BASE_URL}/api/v1/streams?channel=exec_trace:${executionId}`);"
new_str = """const token = localStorage.getItem('upgrade-token') || '';
          const eventSource = new EventSource(`${API_BASE_URL}/api/v1/streams?channel=exec_trace:${executionId}&access_token=${token}`);"""

if old_str in content:
    content = content.replace(old_str, new_str)
    with open(file_path, "w") as f:
        f.write(content)
    print("Frontend patched successfully!")
else:
    print("Could not find the target string to replace.")