def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy", "service": "PulseWatch"}


def test_landing_is_public(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"PULSEWATCH" in response.data
    assert b"Know when your services go silent." in response.data


def test_login_success(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_login_failure(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid username or password." in response.data


def test_protected_routes_redirect(client):
    for path in ("/dashboard", "/monitors", "/incidents", "/analytics", "/settings"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_session_and_logout(admin_client):
    response = admin_client.get("/dashboard")
    assert response.status_code == 200
    assert b"PulseWatch Control Center" in response.data

    logout = admin_client.get("/logout", follow_redirects=False)
    assert logout.status_code == 302
    assert logout.headers["Location"].endswith("/")

    blocked = admin_client.get("/dashboard", follow_redirects=False)
    assert blocked.status_code == 302
    assert "/login" in blocked.headers["Location"]
