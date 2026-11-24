"""HTTP-only requests for explicitly configured feeds and notifications."""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("An HTTP or HTTPS URL is required")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not supported")


class HTTPRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_request(request, timeout):
    validate_url(request.full_url)
    return build_opener(HTTPRedirect()).open(request, timeout=timeout)
