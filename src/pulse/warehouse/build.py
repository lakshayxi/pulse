from __future__ import annotations

import argparse
from pathlib import Path

try:
    import duckdb
except ImportError:  # Optional at import time; declared runtime dependency.
    duckdb = None

TABLES = [
    "customers",
    "customer_events",
    "transactions",
    "product_holdings",
    "marketing_exposures",
    "experiment_assignments",
    "experiment_outcomes",
    "campaign_assignments",
]
MODEL_DIRS = ("staging", "marts")
VALIDATION_DIR = "validation"


def build_warehouse(
    data_dir: str | Path, database: str | Path = ":memory:"
) -> duckdb.DuckDBPyConnection:
    if duckdb is None:
        raise RuntimeError("duckdb is required; install project dependencies with uv sync")
    con = duckdb.connect(str(database))
    for table in TABLES:
        file = Path(data_dir) / f"{table}.parquet"
        con.execute(
            f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet(?)", [str(file)]
        )
    return con


def run_models(con: duckdb.DuckDBPyConnection, sql_root: str | Path = "sql") -> None:
    """Execute staging and mart SQL in dependency order on an existing connection."""
    root = Path(sql_root)
    for layer in MODEL_DIRS:
        for query in sorted((root / layer).glob("*.sql")):
            con.execute(query.read_text(encoding="utf-8"))


def run_validation(con: duckdb.DuckDBPyConnection, sql_root: str | Path = "sql") -> list[dict]:
    """Run validation queries and raise when any named check fails."""
    failures: list[dict] = []
    root = Path(sql_root)
    for query in sorted((root / VALIDATION_DIR).glob("*.sql")):
        result = con.execute(query.read_text(encoding="utf-8")).fetchdf()
        if "passed" in result.columns:
            failures.extend(result.loc[~result["passed"].astype(bool)].to_dict("records"))
    if failures:
        names = ", ".join(str(item.get("check_name", "unknown")) for item in failures)
        raise RuntimeError(f"warehouse validation failed: {names}")
    return []


def run_analysis(con: duckdb.DuckDBPyConnection, sql_root: str | Path = "sql") -> dict[str, object]:
    """Execute analysis SQL and return each named query as a dataframe."""
    root = Path(sql_root) / "analysis"
    return {
        query.stem: con.execute(query.read_text(encoding="utf-8")).fetchdf()
        for query in sorted(root.glob("*.sql"))
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default=None, help="retained for Makefile/CLI compatibility")
    p.add_argument("--data-dir", default="data/generated")
    p.add_argument("--output", default="data/pulse.duckdb")
    p.add_argument("--sql-root", default="sql")
    args = p.parse_args()
    con = build_warehouse(args.data_dir, args.output)
    try:
        run_models(con, args.sql_root)
        run_validation(con, args.sql_root)
    finally:
        con.close()
