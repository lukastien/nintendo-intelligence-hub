import pytest

from ingestion.registry import load_metric_catalog, load_source_catalog
from ingestion.urls import assert_official_url, assert_simulated_url
from nih.config import Settings, describe_target
from nih.errors import ConfigurationError, ProvenanceError
from nih.provenance import SourceClass


def test_catalogs_separate_official_reference_and_simulated_sources():
    sources = load_source_catalog()
    classes = {source.source_class for source in sources}
    assert classes == {
        SourceClass.OFFICIAL_IR,
        SourceClass.PUBLIC_REFERENCE,
        SourceClass.SIMULATED_OPERATIONAL,
    }
    official = [source for source in sources if source.source_class is SourceClass.OFFICIAL_IR]
    assert official
    assert all(source.loads_measures_in_foundation is False for source in official)
    simulated = [source for source in sources if source.source_class is SourceClass.SIMULATED_OPERATIONAL]
    assert simulated
    assert all(source.publisher == "SYNTHETIC" for source in simulated)


def test_metrics_cover_flows_and_a_balance_sheet_stock():
    metrics = {metric.metric_code: metric for metric in load_metric_catalog()}
    assert metrics["hw_units_sell_in"].additive_flow is True
    assert metrics["sw_units_sell_in"].sales_basis == "sell_in"
    assert metrics["net_sales_jpy"].native_unit == "jpy"
    assert metrics["total_assets_jpy"].additive_flow is False


def test_official_urls_stay_on_the_nintendo_ir_host():
    assert_official_url("https://www.nintendo.co.jp/ir/en/finance/index.html")
    with pytest.raises(ProvenanceError):
        assert_official_url("https://example.com/estimate")
    with pytest.raises(ProvenanceError):
        assert_simulated_url("https://www.nintendo.co.jp/ir/en/index.html")


def test_default_target_is_local_postgres():
    settings = Settings(warehouse_target="postgres")
    described = describe_target(settings)
    assert described.startswith("postgres://")
    assert f":{settings.postgres_port}/" in described


def test_bigquery_without_a_project_fails_closed():
    settings = Settings(warehouse_target="bigquery", bigquery_project=None)
    with pytest.raises(ConfigurationError):
        describe_target(settings)
