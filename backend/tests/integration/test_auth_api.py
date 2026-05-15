from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.storage.user_repo import upsert_demo_user

SESSION_COOKIE = "sift_session"


def _seed_demo_user(db_session: Session) -> None:
    upsert_demo_user(
        db_session,
        email="ap-clerk@sift.demo",
        password="letmein-demo",
    )


class TestLogin:
    def test_login_success_sets_cookie_and_returns_user(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": False,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["user"]["email"].lower() == "ap-clerk@sift.demo"
        assert SESSION_COOKIE in res.cookies

    def test_login_wrong_password_returns_401_generic(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "wrong",
                "remember": False,
            },
        )
        assert res.status_code == 401
        assert res.json() == {"detail": "Email or password incorrect."}
        assert SESSION_COOKIE not in res.cookies

    def test_login_unknown_email_returns_same_message(self, unauthed_client) -> None:
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "nobody@sift.demo",
                "password": "x",
                "remember": False,
            },
        )
        assert res.status_code == 401
        assert res.json() == {"detail": "Email or password incorrect."}

    def test_login_invalid_payload_returns_422(self, unauthed_client) -> None:
        res = unauthed_client.post(
            "/api/auth/login",
            json={"email": "not-an-email", "password": "x", "remember": False},
        )
        assert res.status_code == 422

    def test_login_remember_sets_max_age(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": True,
            },
        )
        assert res.status_code == 200
        set_cookie = res.headers["set-cookie"]
        assert "Max-Age=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie

    def test_login_without_remember_omits_max_age(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": False,
            },
        )
        assert res.status_code == 200
        set_cookie = res.headers["set-cookie"]
        assert "Max-Age=" not in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie


class TestMe:
    def test_me_without_cookie_is_401(self, unauthed_client) -> None:
        res = unauthed_client.get("/api/auth/me")
        assert res.status_code == 401

    def test_me_with_cookie_returns_clerk(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        login_res = unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": False,
            },
        )
        assert login_res.status_code == 200
        me_res = unauthed_client.get("/api/auth/me")
        assert me_res.status_code == 200
        body = me_res.json()
        assert body["email"].lower() == "ap-clerk@sift.demo"


class TestLogout:
    def test_logout_clears_cookie_and_invalidates_session(
        self, unauthed_client, db_session: Session
    ) -> None:
        _seed_demo_user(db_session)
        unauthed_client.post(
            "/api/auth/login",
            json={
                "email": "ap-clerk@sift.demo",
                "password": "letmein-demo",
                "remember": False,
            },
        )
        res = unauthed_client.post("/api/auth/logout")
        assert res.status_code == 204

        me_res = unauthed_client.get("/api/auth/me")
        assert me_res.status_code == 401

    def test_logout_without_cookie_is_204(self, unauthed_client) -> None:
        res = unauthed_client.post("/api/auth/logout")
        assert res.status_code == 204
