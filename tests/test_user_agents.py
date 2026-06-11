"""Unit tests for pyproc.user_agents header rotation module."""
import unittest

from pyproc.user_agents import (
    USER_AGENTS,
    HEADER_PROFILES,
    create_session_headers,
)


class TestUserAgents(unittest.TestCase):

    def test_user_agents_not_empty(self):
        self.assertGreater(len(USER_AGENTS), 0)

    def test_header_profiles_not_empty(self):
        self.assertGreater(len(HEADER_PROFILES), 0)

    def test_create_session_headers_returns_dict(self):
        headers = create_session_headers(0)
        self.assertIsInstance(headers, dict)

    def test_create_session_headers_has_required_keys(self):
        headers = create_session_headers(0)
        self.assertIn('User-Agent', headers)
        self.assertIn('Accept', headers)
        self.assertIn('Accept-Language', headers)

    def test_different_worker_ids_get_different_user_agents(self):
        """Consecutive workers should get different User-Agent strings."""
        h0 = create_session_headers(0)['User-Agent']
        h1 = create_session_headers(1)['User-Agent']
        self.assertNotEqual(h0, h1)

    def test_different_worker_ids_get_different_profiles(self):
        """Workers should cycle through header profiles."""
        num_profiles = len(HEADER_PROFILES)
        if num_profiles > 1:
            a0 = create_session_headers(0)['Accept-Language']
            a1 = create_session_headers(1)['Accept-Language']
            self.assertNotEqual(a0, a1)

    def test_worker_cycling_wraps_around(self):
        """Worker IDs beyond the pool size should wrap around."""
        ua_first = create_session_headers(0)['User-Agent']
        ua_wrapped = create_session_headers(len(USER_AGENTS))['User-Agent']
        self.assertEqual(ua_first, ua_wrapped)

    def test_negative_worker_id_wraps(self):
        """Negative worker IDs should use Python's modulo behavior."""
        headers = create_session_headers(-1)
        self.assertIsInstance(headers, dict)
        self.assertIn('User-Agent', headers)

    def test_large_worker_id(self):
        """Large worker IDs should work fine via modulo."""
        headers = create_session_headers(99999)
        self.assertIsInstance(headers, dict)
        self.assertIn('User-Agent', headers)


if __name__ == '__main__':
    unittest.main()
