
# Deploying workbench to all repos

```
 1068  python3 create_workspace.py --workspace=workbench
 1069  python3 update_default_json.py --workspace=workbench
 1070  python3 copy_template_files.py --workspace=workbench --files tests/test_responses.py --preserve
 1071  python3 copy_template_files.py --workspace=workbench --files .devcontainer/devcontainer.json 
 1072  python3 copy_template_files.py --workspace=workbench --files .github/workflows/response_tests.yml .vscode/settings.json .vscode/tasks.json .gitignore
 1073  python3 create_template_prs.py --workspace=workbench --branch=workbench --message="Add workbench and fix python3 invocation"
```
