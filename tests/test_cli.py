"""The command line, offline: bundled data for the demo, stubs for the network."""

import unbundle.cli as cli
from unbundle import load_factors, load_sample


def test_demo_runs_offline(capsys, tmp_path):
    out = tmp_path / "demo.html"
    assert cli.main(["demo", "--report", str(out)]) == 0
    text = capsys.readouterr().out
    assert "size-momentum" in text and "carhart" in text and "Health care" in text
    assert out.exists() and out.stat().st_size > 10_000


def _sample_factors(model, start=None, end=None, **_):
    return load_factors(model, source="sample", start=start, end=end)


def test_csv_command(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_factors", _sample_factors)
    s = load_sample().loc["2000-01":"2016-12", ["Hlth", "Utils"]]
    path = tmp_path / "mine.csv"
    s.rename_axis("month").to_csv(path)
    assert cli.main(["csv", str(path), "--model", "ff3", "--start", "2005-01"]) == 0
    text = capsys.readouterr().out
    assert "Hlth" in text and "Utils" in text and "AlphaTest" in text


def test_fund_command_with_prices_stubbed(monkeypatch, capsys, tmp_path):
    s = load_sample().loc["2010-01":"2016-12", ["Hlth"]].rename(columns={"Hlth": "XLV"})
    monkeypatch.setattr(cli, "fetch_yahoo", lambda tickers, start=None, end=None: s)
    monkeypatch.setattr(cli, "load_factors", _sample_factors)
    report = tmp_path / "xlv.html"
    assert cli.main(["fund", "XLV", "--model", "carhart", "--report", str(report)]) == 0
    assert "XLV" in capsys.readouterr().out and report.exists()


def test_errors_are_one_line_messages(capsys, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no prices returned for ZZZZ")

    monkeypatch.setattr(cli, "fetch_yahoo", boom)
    assert cli.main(["fund", "ZZZZ"]) == 1
    assert "unbundle: no prices returned for ZZZZ" in capsys.readouterr().err
