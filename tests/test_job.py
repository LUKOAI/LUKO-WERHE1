import pytest

from amazon_vat_merger import gsheets
from amazon_vat_merger.job import run_job
from tests.conftest import SAMPLE_CSV, SAMPLE_PDF_DIR
from tests.test_report import ROW_OSS, ROW_REFUND_GB, _write


@pytest.mark.skipif(not SAMPLE_CSV.exists(), reason="brak próbki CSV")
def test_run_job_end_to_end(tmp_path):
    job = run_job([SAMPLE_CSV], [SAMPLE_PDF_DIR], tmp_path / "w.xlsx", use_nbp=False)
    assert job.xlsx_path.exists() and job.result.matched == 44 and "Wszystko" in job.sheets
    assert job.nbp_error is None and "transakcje: 44" in job.summary


def test_run_job_requires_csv(tmp_path):
    with pytest.raises(ValueError):
        run_job([], [], tmp_path / "w.xlsx", use_nbp=False)


def test_run_job_push_error_keeps_xlsx_and_reports(tmp_path, monkeypatch):
    csv_path = _write(tmp_path, ROW_OSS, ROW_REFUND_GB)

    def boom(*a, **k):
        raise gsheets.GoogleSheetsError("brak dostępu do arkusza ID1 – udostępnij arkusz adresowi x@y jako Edytor")

    monkeypatch.setattr(gsheets, "push_sheets", boom)
    job = run_job([csv_path], [], tmp_path / "w.xlsx", use_nbp=False, sheet_id="ID1", credentials=tmp_path / "k.json")
    assert job.xlsx_path.exists() and not (tmp_path / "w.xlsx.tmp").exists()
    assert job.pushed_tabs == [] and "udostępnij" in job.push_error
    assert "BŁĄD Google Sheets" in job.summary and "plik Excel jest zapisany" in job.summary
    assert "DE OSS" in job.sheets and "FR Marketplace KOREKTA" in job.sheets


def test_run_job_push_success_reports_cleared_tabs(tmp_path, monkeypatch):
    csv_path = _write(tmp_path, ROW_OSS)
    monkeypatch.setattr(gsheets, "push_sheets",
                        lambda *a, **k: gsheets.PushResult(written=["Wszystko", "DE OSS"], cleared_stale=["DE OSS KOREKTA"]))
    job = run_job([csv_path], [], tmp_path / "w.xlsx", use_nbp=False, sheet_id="ID1", credentials=tmp_path / "k.json")
    assert job.push_error is None and job.pushed_tabs == ["Wszystko", "DE OSS"] and job.cleared_tabs == ["DE OSS KOREKTA"]
    assert "zapisano 2 zakładek (wyczyszczono nieaktualne: DE OSS KOREKTA)" in job.summary


def test_cli_returns_3_on_push_error(tmp_path, monkeypatch, capsys):
    from amazon_vat_merger.cli import main
    csv_path = _write(tmp_path, ROW_OSS)
    monkeypatch.setattr(gsheets, "push_sheets", lambda *a, **k: (_ for _ in ()).throw(gsheets.GoogleSheetsError("x")))
    rc = main(["--csv", str(csv_path), "--out", str(tmp_path / "w.xlsx"), "--no-nbp", "--sheet-id", "ID1", "--credentials", "k.json"])
    assert rc == 3 and (tmp_path / "w.xlsx").exists()
    assert "BŁĄD Google Sheets: x" in capsys.readouterr().err


def test_gui_config_migrates_from_old_program_name(tmp_path, monkeypatch):
    from amazon_vat_merger import gui
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "AmazonVAT" / "config.json"
    old.parent.mkdir()
    old.write_text('{"csv": "C:/raporty/r.csv", "use_nbp": false}', encoding="utf-8")
    cfg = gui.load_config()
    assert cfg == {"csv": "C:/raporty/r.csv", "use_nbp": False}
    assert (tmp_path / "LUKO-AmaFakt" / "config.json").exists()
    # od teraz liczy się nowa lokalizacja
    (tmp_path / "LUKO-AmaFakt" / "config.json").write_text('{"csv": "nowy"}', encoding="utf-8")
    assert gui.load_config() == {"csv": "nowy"}


def test_unknown_country_tab_name_is_sheet_safe(tmp_path):
    from amazon_vat_merger.report import read_report
    row = ROW_OSS.replace(",Berlin,,DE,10115,1,", ",Berlin,,,10115,1,")   # brak Ship To Country
    tx = read_report(_write(tmp_path, row))[0]
    assert tx.tab_country == "XX" and tx.tab_name == "XX OSS"
    from amazon_vat_merger.excel import safe_sheet_name
    assert safe_sheet_name(tx.tab_name, set()) == tx.tab_name
