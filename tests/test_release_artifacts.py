"""公开展示文件与本地目录的发布边界检查。"""

import ast
import json
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def check_ignored(paths):
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        input="\n".join(paths) + "\n", cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return set(result.stdout.splitlines())


def test_local_and_legacy_files_are_ignored_regardless_of_extension():
    local_paths = [
        "outputs/local/customer_campaign_target_list.csv",
        "outputs/local/high_value_churned_customers.csv",
        "outputs/local/simulated_campaign_tasks.csv",
        "outputs/local/diagnostics/sample.txt",
        "outputs/local/tableau_staging/sample.csv",
        "outputs/local/legacy_previews/sample.png",
        "outputs/local/sample.xlsx",
        "outputs/local/sample.json",
        "tools/legacy/build_tableau_previews.py",
        "tools/legacy/README.md",
        "docs/resume/resume_full.tex",
    ]
    assert check_ignored(local_paths) == set(local_paths)
    public_paths = [
        "notebooks/01_project_showcase.ipynb", "outputs/README.md",
        "docs/customer_samples.md", "src/build_sample_docs.py",
        "docs/resume/resume_project_description.md",
        "docs/resume/resume_metrics.md",
        "outputs/tableau/Olist_Customer_Lifecycle_Dashboard.twbx",
        "outputs/tableau/dashboard_overview.png",
        "outputs/tableau/customer_segment.png",
        "outputs/tableau/delivery_analysis.png",
    ]
    assert not check_ignored(public_paths)


def test_showcase_is_executed_and_uses_only_public_aggregate_inputs():
    notebook = json.loads((ROOT / "notebooks/01_project_showcase.ipynb").read_text())
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    sources = None
    for cell in code_cells:
        assert cell["execution_count"] is not None
        assert all(out["output_type"] != "error" for out in cell["outputs"])
        for node in ast.walk(ast.parse("".join(cell["source"]))):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "SOURCES"
                for target in node.targets
            ):
                sources = ast.literal_eval(node.value)
    assert sources
    assert not check_ignored(list(sources.values()))
    for relative_path in sources.values():
        path = ROOT / relative_path
        assert path.parent in (ROOT / "outputs/tables", ROOT / "outputs/tableau")
        assert path.is_file()
        assert not any(column.endswith("_id") for column in pd.read_csv(path, nrows=0).columns)
