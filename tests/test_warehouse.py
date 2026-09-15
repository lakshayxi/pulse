import pytest

pytest.importorskip("duckdb")
from pulse.simulation import generate_dataset
from pulse.simulation.generator import write_dataset
from pulse.warehouse import build_warehouse


def test_duckdb_load(tmp_path):
    write_dataset(generate_dataset(40), tmp_path)
    con = build_warehouse(tmp_path)
    assert con.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 40
    assert con.execute("SELECT COUNT(*) FROM transactions WHERE amount < 0").fetchone()[0] == 0
