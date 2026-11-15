import uuid

from httpx import AsyncClient

from tests.helpers import PASSWORD, signup


async def test_signup_login_me(client: AsyncClient) -> None:
    a = await signup(client)
    me = await client.get("/auth/me", headers=a["h"])
    assert me.status_code == 200 and me.json()["role"] == "owner"
    r = await client.post("/auth/login", json={"email": a["email"], "password": PASSWORD})
    assert r.status_code == 200 and r.json()["clinic_id"] == a["clinic_id"]
    bad = await client.post("/auth/login", json={"email": a["email"], "password": "wrong-password"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_duplicate_email_and_slug(client: AsyncClient) -> None:
    a = await signup(client)
    r = await client.post(
        "/auth/signup",
        json={
            "clinic_name": "Other",
            "slug": "other-" + uuid.uuid4().hex[:6],
            "full_name": "X Y",
            "email": a["email"],
            "password": PASSWORD,
        },
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"
    r = await client.post(
        "/auth/signup",
        json={
            "clinic_name": "Other",
            "slug": a["slug"],
            "full_name": "X Y",
            "email": f"{uuid.uuid4().hex}@example.com",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "SLUG_TAKEN"
    r = await client.post(
        "/auth/signup",
        json={
            "clinic_name": "Other",
            "slug": "admin",
            "full_name": "X Y",
            "email": f"{uuid.uuid4().hex}@example.com",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 422


async def test_refresh_rotation_and_reuse_detection(client: AsyncClient) -> None:
    a = await signup(client)
    r1 = await client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()["refresh_token"]
    assert new != a["refresh_token"]
    # replaying the OLD token = theft signal -> whole family revoked
    replay = await client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "TOKEN_REUSED"
    # the legitimately rotated token is now dead too
    dead = await client.post("/auth/refresh", json={"refresh_token": new})
    assert dead.status_code == 401


async def test_logout_revokes_refresh(client: AsyncClient) -> None:
    a = await signup(client)
    assert (
        await client.post("/auth/logout", json={"refresh_token": a["refresh_token"]})
    ).status_code == 204
    r = await client.post("/auth/refresh", json={"refresh_token": a["refresh_token"]})
    assert r.status_code == 401


async def test_unauthenticated_and_garbage_token(client: AsyncClient) -> None:
    assert (await client.get("/clinic")).status_code == 401
    r = await client.get("/clinic", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_role_rules(client: AsyncClient) -> None:
    owner = await signup(client)

    def mk(role: str) -> dict[str, str]:
        return {
            "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Staff Person",
            "password": PASSWORD,
            "role": role,
        }

    r = await client.post("/staff", json=mk("admin"), headers=owner["h"])
    assert r.status_code == 201
    doc = mk("doctor")
    assert (await client.post("/staff", json=doc, headers=owner["h"])).status_code == 201
    admin_login = await client.post(
        "/auth/login", json={"email": r.json()["email"], "password": PASSWORD}
    )
    ah = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    assert (
        await client.post("/staff", json=mk("admin"), headers=ah)
    ).status_code == 403  # admin can't mint admins
    assert (await client.post("/staff", json=mk("doctor"), headers=ah)).status_code == 201
    dl = await client.post("/auth/login", json={"email": doc["email"], "password": PASSWORD})
    dh = {"Authorization": f"Bearer {dl.json()['access_token']}"}
    assert (await client.get("/staff", headers=dh)).status_code == 403
    assert (await client.get("/clinic", headers=dh)).status_code == 200


async def test_suspend_blocks_login_and_existing_tokens(client: AsyncClient) -> None:
    a = await signup(client)
    from app.core.security import hash_password
    from app.db import system_session
    from app.models.tables import User

    async with system_session() as s:
        s.add(
            User(
                email="root@example.com",
                password_hash=hash_password(PASSWORD),
                full_name="Root",
                is_superadmin=True,
            )
        )
    sa = await client.post("/auth/login", json={"email": "root@example.com", "password": PASSWORD})
    sh = {"Authorization": f"Bearer {sa.json()['access_token']}"}
    assert (await client.get("/admin/clinics", headers=a["h"])).status_code == 403
    r = await client.post(f"/admin/clinics/{a['clinic_id']}/suspend", headers=sh)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await client.get("/clinic", headers=a["h"])).status_code == 403
    login = await client.post("/auth/login", json={"email": a["email"], "password": PASSWORD})
    assert login.status_code == 403 and login.json()["error"]["code"] == "CLINIC_SUSPENDED"
    await client.post(f"/admin/clinics/{a['clinic_id']}/activate", headers=sh)
    assert (await client.get("/clinic", headers=a["h"])).status_code == 200
