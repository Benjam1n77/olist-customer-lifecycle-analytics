"""导出路由测试：合成夹具仅验证文件位置与保真，不代表业务结果。"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src import config as config_module
from src import export_outputs


def test_local_path_is_available_in_defaults_and_example(monkeypatch):
    example = config_module.load_config(
        config_module.PROJECT_ROOT / "config/config.example.yaml"
    )
    assert example["paths"]["output_local_dir"] == "outputs/local"
    # 旧本地配置未声明新增键时，仍应继承默认本地路径。
    monkeypatch.setattr(config_module, "_load_yaml", lambda _: {"paths": {}})
    config = config_module.load_config()
    assert config_module.get_path(config, "output_local_dir") == (
        config_module.PROJECT_ROOT / "outputs/local"
    )


@pytest.mark.parametrize(
    ("exporter", "filename"),
    [
        (export_outputs.export_campaign_list, "customer_campaign_target_list.csv"),
        (export_outputs.export_simulated_tasks, "simulated_campaign_tasks.csv"),
        (export_outputs.export_high_value_churned, "high_value_churned_customers.csv"),
    ],
)
def test_customer_exports_only_write_to_local(tmp_path, monkeypatch, exporter, filename):
    local_dir = tmp_path / "local"
    public_dir = tmp_path / "tables"
    config = {
        "paths": {
            "output_local_dir": str(local_dir),
            "output_tables_dir": str(public_dir),
        }
    }
    sample = pd.DataFrame({
        "customer_unique_id": ["test-customer-a", "test-customer-b"],
        "reason_code": ["SERVICE_RECOVERY", "SECOND_PURCHASE"],
        "campaign_priority": ["high", "medium"],
        "recommended_action": ["test-action-a", "test-action-b"],
        "recommended_channel": ["test-channel", "test-channel"],
        "total_payment": [80.0, 20.0],
    })
    totals = pd.DataFrame({"all_customers": [2], "all_payment": [100.0]})
    engine = MagicMock()
    monkeypatch.setattr(export_outputs, "_get_engine", lambda _: engine)
    results = [sample.copy(), totals] if exporter is export_outputs.export_high_value_churned else [sample.copy()]
    monkeypatch.setattr(export_outputs.pd, "read_sql", MagicMock(side_effect=results))

    path = exporter(config)

    assert path == local_dir / filename
    assert not public_dir.exists()
    saved = pd.read_csv(path)
    assert saved["customer_unique_id"].tolist() == sample["customer_unique_id"].tolist()
    if exporter is export_outputs.export_simulated_tasks:
        assert saved["task_status"].eq("SIMULATED").all()
        assert saved["simulated_send_date"].tolist() == ["2018-08-31", "2018-09-06"]
    else:
        pd.testing.assert_frame_equal(saved, sample)
    engine.dispose.assert_called_once()


def test_tableau_intermediates_are_separate_from_final_csvs(tmp_path, monkeypatch):
    local_dir = tmp_path / "local"
    public_dir = tmp_path / "tableau"
    config = {"paths": {
        "output_local_dir": str(local_dir),
        "output_tableau_dir": str(public_dir),
    }}
    # 合成的微型数据库返回值仅用于路由/勾稽测试，不进入项目产物。
    metrics = pd.DataFrame({
        "metric": ["total_customers", "valid_delivered_orders", "total_payment_brl",
                   "repeat_buyer_pct", "one_time_buyer_pct"],
        "value": [2, 3, 100, 50, 50],
    })
    segments = pd.DataFrame({
        "final_segment": ["group-a", "group-b"],
        "customer_count": [1, 1],
        "total_payment": [80.0, 20.0],
        "avg_aov": [40.0, 20.0],
    })
    cohort = pd.DataFrame({
        "cohort_month": ["2020-01-01"], "activity_month": ["2020-02-01"],
        "month_index": [1], "cohort_size": [2],
        "retained_customers": [1], "retention_pct": [50.0],
    })
    delivery = pd.DataFrame({
        "grain": ["delay_bucket"], "dim_value": ["on_time"],
        "orders": [3], "delay_rate_pct": [0.0], "avg_score": [4.0],
    })
    category = pd.DataFrame({
        "main_category": ["test-category"], "delivered_orders": [3],
        "revenue": [100.0], "avg_score": [4.0], "delay_rate_pct": [0.0],
    })
    campaigns = pd.DataFrame({
        "reason_code": ["SECOND_PURCHASE"], "campaign_priority": ["medium"],
        "customer_count": [1], "total_payment": [20.0], "avg_recency_days": [30.0],
    })
    engine = MagicMock()
    monkeypatch.setattr(export_outputs, "_get_engine", lambda _: engine)
    monkeypatch.setattr(export_outputs.pd, "read_sql", MagicMock(
        side_effect=[metrics, segments, cohort, delivery, category, campaigns]
    ))

    paths = export_outputs.export_tableau_csvs(config)

    assert {p.name for p in public_dir.iterdir()} == {
        "customer_overview.csv", "customer_segment_dashboard.csv", "cohort_dashboard.csv",
        "delivery_dashboard.csv", "category_performance.csv", "campaign_dashboard.csv",
    }
    staging = local_dir / "tableau_staging"
    assert {p.name for p in staging.iterdir()} == {
        "customer_overview_metrics.csv", "customer_segments.csv", "cohort_retention.csv",
        "delivery_experience.csv", "campaign_targets.csv",
    }
    assert len(paths) == 11
    for name, expected in [
        ("cohort_dashboard.csv", cohort), ("delivery_dashboard.csv", delivery),
        ("category_performance.csv", category), ("campaign_dashboard.csv", campaigns),
    ]:
        pd.testing.assert_frame_equal(pd.read_csv(public_dir / name), expected)
    overview = pd.read_csv(public_dir / "customer_overview.csv").iloc[0]
    assert overview["customer_count"] == 2
    assert overview["payment_amount"] == 100
    exported_segments = pd.read_csv(public_dir / "customer_segment_dashboard.csv")
    assert exported_segments["customer_count"].sum() == 2
    assert exported_segments["payment_share"].sum() == 100
    engine.dispose.assert_called_once()
