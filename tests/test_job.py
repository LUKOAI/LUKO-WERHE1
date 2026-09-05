import pytest

from amazon_vat_merger.job import run_job
from tests.conftest import SAMPLE_CSV, SAMPLE_PDF_DIR


@pytest.mark.skipif(not SAMPLE_CSV.exists(), reason="brak próbki CSV")
def test_run_job_end_to_end(tmp_path):
    job = run_job([SAMPLE_CSV], [SAMPLE_PDF_DIR], tmp_path / "w.xlsx", use_nbp=False)
    assert job.xlsx_path.exists() and job.result.matched == 44 and "Wszystko" in job.sheets
    assert job.nbp_error is None and "transakcje: 44" in job.summary


def test_run_job_requires_csv(tmp_path):
    with pytest.raises(ValueError):
        run_job([], [], tmp_path / "w.xlsx", use_nbp=False)
