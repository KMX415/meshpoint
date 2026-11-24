"""HTTPS-only GitHub downloads, including redirect destination validation."""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOSTS = frozenset({"api.github.com", "raw.githubusercontent.com", "codeload.github.com"})


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.port not in (None, 443) or parsed.username or parsed.password):
        raise ValueError("Plugin downloads must use approved GitHub HTTPS hosts")


class GitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_github(url, timeout):
    validate_url(url)
    request = Request(url, headers={"User-Agent": "Meshpoint"})
    return build_opener(GitHubRedirect()).open(request, timeout=timeout)
