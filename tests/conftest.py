import pytest

from sources import httpclient, nextdata, progress


@pytest.fixture(autouse=True)
def _fresh_scan_state():
    """The stop flag, the partial results and the HTTP numbers are process-wide: every test starts clean."""
    progress.reset()
    httpclient.reset_stats()
    nextdata.reset_blocks()
    yield
    progress.reset()
    nextdata.reset_blocks()
