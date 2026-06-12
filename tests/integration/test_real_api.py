import os

import pytest

from ncepu_cloud_client.app.bootstrap import bootstrap


pytestmark = pytest.mark.skipif(os.environ.get("RUN_REAL_API_TESTS") != "1", reason="real API tests are opt-in")


def test_real_api_quota_opt_in():
    _, client = bootstrap()
    quota = client.get_quota()
    assert quota.total >= 0

