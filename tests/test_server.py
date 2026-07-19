import os
import sys
import unittest
from unittest.mock import patch

# Ensure shared auth middleware is available
sys.path.insert(0, os.path.expanduser("~/clawd/meok-labs-engine/shared"))
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")


class TestMCPImport(unittest.TestCase):
    def test_import_server(self):
        """Server module must import without errors."""
        import server  # noqa: F401

    def test_mcp_or_server_object_exists(self):
        """FastMCP servers export 'mcp'; low-level servers export 'server'."""
        import server as srv
        self.assertTrue(
            hasattr(srv, "mcp") or hasattr(srv, "server"),
            "Expected 'mcp' or 'server' object in server.py",
        )


class TestAuthMiddleware(unittest.TestCase):
    def test_check_access_allows_empty_key_as_free_tier(self):
        """Empty API key maps to FREE tier and is allowed."""
        from auth_middleware import check_access
        allowed, msg, tier = check_access("")
        self.assertTrue(allowed)
        self.assertEqual(tier, "free")
        self.assertIsInstance(msg, str)

    def test_check_access_returns_tuple(self):
        """check_access must return a 3-tuple."""
        from auth_middleware import check_access
        result = check_access("")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)


class TestHealthEndpoint(unittest.TestCase):
    def test_health_url_resolves(self):
        """Wrapper must expose /health."""
        import urllib.request
        # Note: this test requires the wrapper to be running on port 8000.
        # It is skipped in CI unless the server is active.
        try:
            resp = urllib.request.urlopen("http://localhost:8000/health", timeout=2)
            self.assertEqual(resp.status, 200)
        except Exception as e:
            self.skipTest(f"Server not running: {e}")


class TestServerMetering(unittest.TestCase):
    def test_metering_decodes_live_verification_response(self):
        """Live verification responses must not silently fall through."""
        import server

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"allowed":false,"tier":"free","remaining":0}'

        with patch("server.urllib.request.urlopen", return_value=FakeResponse()):
            result = server._server_meter_check("test-key")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["remaining"], 0)


class TestXquikTweetMetrics(unittest.TestCase):
    def test_missing_xquik_key_returns_error(self):
        """Xquik metric fetch requires an explicit Xquik API key."""
        import server
        server._request_log.clear()
        with patch.dict(os.environ, {}, clear=True):
            with patch("server.check_access", return_value=(True, "OK", "free")):
                result = server.fetch_x_tweet_metrics("1234567890123456789")
        self.assertEqual(result["error"], "Set XQUIK_API_KEY in the server environment.")

    def test_invalid_tweet_id_is_rejected_before_request(self):
        """Only canonical numeric tweet IDs may reach the API."""
        import server
        server._request_log.clear()
        with patch("server.urllib.request.urlopen") as urlopen:
            result = server.fetch_x_tweet_metrics("../../credentials")
        self.assertEqual(result["error"], "Provide a valid 15 to 20 digit tweet_id.")
        urlopen.assert_not_called()

    def test_fetch_x_tweet_metrics_maps_engagement_input(self):
        """Xquik tweet metrics should match analyze_engagement input keys."""
        import server
        server._request_log.clear()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return (
                    b'{"tweet":{"id":"1234567890123456789","text":"Launch note","createdAt":"2026-06-06T12:00:00Z",'
                    b'"likeCount":10,"replyCount":2,"retweetCount":3,"quoteCount":1,'
                    b'"viewCount":200,"bookmarkCount":4},"author":{"username":"xquik"}}'
                )

        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["timeout"] = timeout
            return FakeResponse()

        with patch.dict(os.environ, {"XQUIK_API_KEY": "xq_test"}):
            with patch("server.check_access", return_value=(True, "OK", "free")):
                with patch("server.urllib.request.urlopen", fake_urlopen):
                    result = server.fetch_x_tweet_metrics("1234567890123456789")

        self.assertEqual(captured["url"], "https://xquik.com/api/v1/x/tweets/1234567890123456789")
        self.assertEqual(captured["headers"]["X-api-key"], "xq_test")
        self.assertEqual(captured["timeout"], 20)
        post = result["analyze_engagement_input"][0]
        self.assertEqual(post["platform"], "twitter")
        self.assertEqual(post["content"], "Launch note")
        self.assertEqual(post["likes"], 10)
        self.assertEqual(post["comments"], 2)
        self.assertEqual(post["shares"], 4)
        self.assertEqual(post["impressions"], 200)
        self.assertEqual(post["bookmarks"], 4)
        self.assertEqual(post["url"], "https://x.com/xquik/status/1234567890123456789")


class TestContentCalendar(unittest.TestCase):
    def test_empty_topics_returns_validation_error(self):
        """Empty topics must return an error instead of dividing by zero."""
        import server
        server._request_log.clear()
        with patch("server.check_access", return_value=(True, "OK", "free")):
            result = server.plan_content_calendar(["twitter"], [])
        self.assertEqual(result["error"], "Provide at least one content topic.")


if __name__ == "__main__":
    unittest.main()
