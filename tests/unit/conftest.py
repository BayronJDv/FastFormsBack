import sys
from unittest.mock import MagicMock

_mock_client = MagicMock()
sys.modules["supabase"] = MagicMock(create_client=lambda url, key: _mock_client)