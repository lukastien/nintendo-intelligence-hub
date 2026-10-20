"""Ingestion: source catalogs, official downloads, and parsers.

`nih init-db` still does not insert official measures. `nih ingest` downloads
public Nintendo files, parses them, and can load the warehouse. A source that
cannot be retrieved is reported unavailable. Synthetic rows are not written
in its place.
"""

__all__ = ["load_metric_catalog", "load_source_catalog"]
