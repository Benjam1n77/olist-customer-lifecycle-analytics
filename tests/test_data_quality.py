"""数据质量检查逻辑测试：用合成数据验证质量规则的检测能力。

这些测试不依赖数据库，验证质量检查规则本身的正确性
（对应 sql/03_data_quality_checks.sql 中同类逻辑的 Python 镜像）。
"""

import pandas as pd
import pytest


def find_duplicate_ids(df: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """找出主键重复的行（对应质量检查 A 系列）。"""
    return df[df.duplicated(id_col, keep=False)]


def detect_time_inversions(orders: pd.DataFrame) -> dict[str, int]:
    """检测时间倒挂（对应质量检查 D 系列）。

    规则：购买 > 审批、审批 > 承运、承运 > 签收、签收 < 购买。
    """
    orders = orders.copy()
    for col in ["purchase", "approved", "carrier", "delivered"]:
        orders[col] = pd.to_datetime(orders[col], errors="coerce")
    return {
        "purchase_after_approved": int(
            (orders["purchase"] > orders["approved"]).sum()
        ),
        "approved_after_carrier": int((orders["approved"] > orders["carrier"]).sum()),
        "carrier_after_delivered": int((orders["carrier"] > orders["delivered"]).sum()),
        "delivered_before_purchase": int(
            (orders["delivered"] < orders["purchase"]).sum()
        ),
    }


def find_orphan_records(child: pd.DataFrame, parent: pd.DataFrame, key: str) -> pd.DataFrame:
    """找出孤立记录（对应质量检查 F 系列：LEFT JOIN 父表为 NULL）。"""
    merged = child.merge(parent[[key]], on=key, how="left", indicator=True)
    return merged[merged["_merge"] == "left_only"]


@pytest.fixture()
def synthetic_orders() -> pd.DataFrame:
    """合成订单数据：3 条正常 + 各类异常各 1 条。"""
    return pd.DataFrame(
        {
            "order_id": ["o1", "o2", "o3", "o4", "o5", "o6"],
            "purchase": [
                "2018-01-01", "2018-01-01", "2018-01-01",
                "2018-01-05", "2018-01-01", "2018-01-01",
            ],
            "approved": [
                "2018-01-02", "2018-01-01", "2018-01-02",
                "2018-01-06", "2018-01-02", "2018-01-02",
            ],
            "carrier": [
                "2018-01-03", "2018-01-03", "2018-01-01",
                "2018-01-07", "2018-01-03", "2018-01-03",
            ],
            "delivered": [
                "2018-01-05", "2018-01-05", "2018-01-05",
                "2018-01-02", "2018-01-05", "2018-01-05",
            ],
        }
    )


class TestDuplicateDetection:
    def test_detects_duplicates(self) -> None:
        df = pd.DataFrame({"review_id": ["a", "b", "a", "c"]})
        dups = find_duplicate_ids(df, "review_id")
        assert len(dups) == 2
        assert set(dups["review_id"]) == {"a"}

    def test_no_duplicates(self) -> None:
        df = pd.DataFrame({"review_id": ["a", "b", "c"]})
        assert len(find_duplicate_ids(df, "review_id")) == 0


class TestTimeInversions:
    def test_clean_data_has_no_inversions(self, synthetic_orders: pd.DataFrame) -> None:
        inv = detect_time_inversions(synthetic_orders.iloc[[0]])
        assert all(v == 0 for v in inv.values())

    def test_purchase_after_approved(self, synthetic_orders: pd.DataFrame) -> None:
        # o2：购买与审批同日为正常；构造倒挂行
        bad = pd.DataFrame(
            {"purchase": ["2018-01-05"], "approved": ["2018-01-02"],
             "carrier": ["2018-01-06"], "delivered": ["2018-01-08"]}
        )
        inv = detect_time_inversions(bad)
        assert inv["purchase_after_approved"] == 1

    def test_delivered_before_purchase(self, synthetic_orders: pd.DataFrame) -> None:
        inv = detect_time_inversions(synthetic_orders)
        # o5 签收早于购买
        assert inv["delivered_before_purchase"] == 1

    def test_carrier_after_delivered(self, synthetic_orders: pd.DataFrame) -> None:
        inv = detect_time_inversions(synthetic_orders)
        # o4 承运晚于签收
        assert inv["carrier_after_delivered"] == 1


class TestOrphanRecords:
    def test_finds_orphans(self) -> None:
        payments = pd.DataFrame({"order_id": ["o1", "o2", "o3"]})
        orders = pd.DataFrame({"order_id": ["o1", "o2"]})
        orphans = find_orphan_records(payments, orders, "order_id")
        assert list(orphans["order_id"]) == ["o3"]

    def test_no_orphans(self) -> None:
        payments = pd.DataFrame({"order_id": ["o1", "o2"]})
        orders = pd.DataFrame({"order_id": ["o1", "o2", "o3"]})
        assert len(find_orphan_records(payments, orders, "order_id")) == 0


class TestCsvRecordCount:
    """CSV 记录数必须用解析器而非物理行数（项目真实踩坑经验）。"""

    def test_embedded_newline_counts_as_one_record(self, tmp_path) -> None:
        csv_path = tmp_path / "reviews.csv"
        # 第二条记录的评论含内嵌换行：物理 4 行，实际 2 条记录
        csv_path.write_text(
            'review_id,comment\nr1,"ok"\nr2,"line one\nline two"\n',
            encoding="utf-8",
        )
        physical_lines = len(csv_path.read_text(encoding="utf-8").splitlines())
        df = pd.read_csv(csv_path)
        assert physical_lines == 4
        assert len(df) == 2
