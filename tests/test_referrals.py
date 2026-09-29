import pytest

from job_hunter.connectors.base import Job
from job_hunter.referrals import (
    Connection,
    ReferralsError,
    find_referrals,
    load_connections,
    normalize_company_name,
)


def test_normalize_company_name_strips_suffix_and_case():
    assert normalize_company_name("Stripe, Inc.") == "stripe"
    assert normalize_company_name("STRIPE") == "stripe"
    assert normalize_company_name("Acme Corp") == "acme"


def test_load_connections_parses_valid_rows(tmp_path):
    csv_path = tmp_path / "connections.csv"
    csv_path.write_text("name,company,title\nJane Doe,Stripe,Engineer\n")

    connections = load_connections(csv_path)

    assert connections == [Connection(name="Jane Doe", company="Stripe", title="Engineer")]


def test_load_connections_skips_rows_missing_required_fields(tmp_path):
    csv_path = tmp_path / "connections.csv"
    csv_path.write_text("name,company,title\n,Stripe,Engineer\nJohn Smith,,Manager\nJane Doe,Stripe,Engineer\n")

    connections = load_connections(csv_path)

    assert len(connections) == 1
    assert connections[0].name == "Jane Doe"


def test_load_connections_missing_file_raises(tmp_path):
    with pytest.raises(ReferralsError, match="not found"):
        load_connections(tmp_path / "missing.csv")


def test_find_referrals_matches_normalized_company_name():
    job = Job(title="T", company="Stripe, Inc.", location="L", url="u", source="greenhouse")
    connections = [
        Connection(name="Jane Doe", company="Stripe", title="Engineer"),
        Connection(name="John Smith", company="Airbnb", title="PM"),
    ]

    result = find_referrals(job, connections)

    assert result == [connections[0]]
