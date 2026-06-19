import os
import sys

# Patch index.ts
path1 = "upgrade-frontend-master/src/lib/api/workflow/index.ts"
if os.path.exists(path1):
    with open(path1, "r") as f:
        content = f.read()
    # Keep trailing slash to avoid 307 CORS Network Errors
    # content = content.replace("`/api/v1/workflows/`", "`/api/v1/workflows`")
    with open(path1, "w") as f:
        f.write(content)
    print("Patched index.ts")

# Patch workflow.ts
path2 = "upgrade-frontend-master/src/lib/store/workflow.ts"
if os.path.exists(path2):
    with open(path2, "r") as f:
        content = f.read()
    # Keep trailing slash to avoid 307 CORS Network Errors
    # content = content.replace("`/api/v1/workflows/`", "`/api/v1/workflows`")
    
    # Also fix the URL update in saveWorkflow to navigate to the real UUID so on refresh it doesn't 422
    old_str_savedId = "set({ isCurrentExecutionSavedId: savedId, currentWorkflowName: name });"
    new_str_savedId = """set({ isCurrentExecutionSavedId: savedId, currentWorkflowName: name });
          if (typeof window !== 'undefined' && savedId && !window.location.href.includes(savedId)) {
              window.history.pushState({}, '', `/workflow/app/${savedId}`);
          }"""
    if old_str_savedId in content:
        content = content.replace(old_str_savedId, new_str_savedId)
        
    with open(path2, "w") as f:
        f.write(content)
    print("Patched workflow.ts")
