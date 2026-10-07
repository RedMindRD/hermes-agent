import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "https://crm.test"


@pytest.fixture(autouse=True)
def crm_env(monkeypatch):
    monkeypatch.setenv("CRM_BASE_URL", BASE)
    monkeypatch.setenv("CRM_API_TOKEN", "1|test-token")
    monkeypatch.setenv("CRM_TIMEOUT", "5")
