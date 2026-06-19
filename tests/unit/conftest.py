import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("SUPABASE_URL", "https://fake-project.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key-for-testing")

_mock_client = MagicMock()
sys.modules["supabase"] = MagicMock(create_client=lambda url, key: _mock_client)