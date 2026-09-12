"""The catalog downloader cannot follow redirects to arbitrary hosts."""
import unittest
from urllib.request import Request
from src.plugins.network import GitHubRedirect, validate_url


class TestPluginNetwork(unittest.TestCase):
    def test_only_github_https_hosts(self):
        validate_url("https://api.github.com/repos/example/catalog")
        for url in ["file:///tmp/file", "http://api.github.com/repos/example/catalog",
                    "https://example.invalid/file", "https://api.github.com:8000/file",
                    "https://user:password@api.github.com/file"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_redirect_cannot_escape_allowed_hosts(self):
        with self.assertRaises(ValueError):
            GitHubRedirect().redirect_request(
                Request("https://api.github.com/repos/example/catalog"), None,
                302, "Found", {}, "http://localhost/private",
            )


if __name__ == "__main__":
    unittest.main()
