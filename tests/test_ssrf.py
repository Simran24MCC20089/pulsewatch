from services.ssrf import UnsafeURLError, validate_public_http_url


def test_valid_https_url():
    url = validate_public_http_url("https://example.com/status")
    assert url.startswith("https://")


def test_rejects_non_http_scheme():
    try:
        validate_public_http_url("ftp://example.com")
        assert False, "expected UnsafeURLError"
    except UnsafeURLError:
        pass


def test_rejects_localhost():
    for candidate in (
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ):
        try:
            validate_public_http_url(candidate, resolve=False)
            assert False, candidate
        except UnsafeURLError:
            pass


def test_rejects_private_and_metadata():
    for candidate in (
        "http://10.0.0.4/health",
        "http://192.168.1.1/",
        "http://172.16.5.5/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
    ):
        try:
            validate_public_http_url(candidate, resolve=False)
            assert False, candidate
        except UnsafeURLError:
            pass


def test_rejects_credentials_in_url():
    try:
        validate_public_http_url("https://user:pass@example.com/")
        assert False
    except UnsafeURLError:
        pass
