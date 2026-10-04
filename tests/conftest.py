import pytest

from sources import httpclient, progress


@pytest.fixture(autouse=True)
def _fresh_scan_state():
    """The stop flag, the partial results and the HTTP numbers are process-wide: every test starts clean."""
    progress.reset()
    httpclient.reset_stats()
    yield
    progress.reset()
