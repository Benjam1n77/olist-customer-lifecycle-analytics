"""样例范围与来源校验；合成测试夹具不会写入公开样例。"""

import json
import re

import pytest

from src.build_sample_docs import FIELDS, RULE_ORDER, build_document, select_records
from src.config import PROJECT_ROOT


def fixture_rows():
    rows = []
    for index, rule in enumerate(RULE_ORDER, start=1):
        row = dict.fromkeys(FIELDS, "test-only")
        row["customer_unique_id"] = f"{index:032x}"
        row["reason_code"] = rule
        rows.append(row)
    return rows


def test_selection_is_bounded_and_order_independent():
    rows = fixture_rows()
    extra = dict(rows[0], customer_unique_id="f" * 32)
    first, count = select_records([*rows, extra])
    reversed_result, _ = select_records(reversed([*rows, extra]))
    assert first == reversed_result == rows
    assert count == 7
    assert len(first) == len(RULE_ORDER) == 6


def test_selection_rejects_duplicate_customers():
    rows = fixture_rows()
    with pytest.raises(ValueError, match="重复客户"):
        select_records([*rows, rows[0]])


def test_selection_rejects_unreviewed_fields():
    rows = fixture_rows()
    rows[0]["unreviewed_field"] = "must-not-publish"
    with pytest.raises(ValueError, match="字段"):
        select_records(rows)


def test_selection_rejects_unreviewed_rules():
    rows = fixture_rows()
    rows[0]["reason_code"] = "UNREVIEWED"
    with pytest.raises(ValueError, match="未审核"):
        select_records(rows)


def test_selection_rejects_missing_groups():
    with pytest.raises(ValueError, match="全部六类"):
        select_records(fixture_rows()[:-1])


def test_published_examples_have_only_six_reviewed_records():
    page = (PROJECT_ROOT / "docs/customer_samples.md").read_text(encoding="utf-8")
    payloads = re.findall(r"```json\n(.*?)\n```", page, flags=re.S)
    assert len(payloads) == 1
    records = json.loads(payloads[0])
    assert len(records) == 6
    assert tuple(row["reason_code"] for row in records) == RULE_ORDER
    assert len({row["customer_unique_id"] for row in records}) == 6
    assert all(tuple(row) == FIELDS for row in records)
    assert all(all(isinstance(value, str) for value in row.values()) for row in records)
    assert all(re.fullmatch(r"[0-9a-f]{32}", row["customer_unique_id"]) for row in records)
    assert re.search(r"源文件 SHA-256：`[0-9a-f]{64}`", page)
    assert "CC BY-NC-SA 4.0" in page
    assert "不是随机抽样" in page
    assert "未实施真实营销触达或 A/B 实验" in page
    assert "/Users/" not in page


def test_real_local_source_reproduces_published_examples():
    source = PROJECT_ROOT / "outputs/local/customer_campaign_target_list.csv"
    if not source.is_file():
        pytest.skip("完整名单不可用，跳过样例来源核对")
    expected = build_document(source)
    actual = (PROJECT_ROOT / "docs/customer_samples.md").read_text(encoding="utf-8")
    assert expected == actual
