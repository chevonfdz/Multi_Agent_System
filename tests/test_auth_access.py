"""User management and access control (UM-1..UM-9, NFR-5..NFR-10)."""
import sys

from app.auth.security import create_token
from tests.conftest import PASSWORD, chat, login_headers, register


def test_register_rules(client, services):                                     # TC-26, TC-27
    data = register(client, "bob@example.com", "Bob")
    assert data["role"] == "customer"
    again = client.post("/api/auth/register", json={"name": "Bob", "email": "BOB@example.com", "password": PASSWORD})
    assert again.status_code == 409 and again.json()["detail"] == "Email already registered"
    stored = services.users.get_by_email("bob@example.com")
    assert stored.password_hash.startswith("$2") and PASSWORD not in stored.password_hash

    short = client.post("/api/auth/register", json={"name": "X", "email": "x@example.com", "password": "short"})
    assert short.status_code == 422
    bad_email = client.post("/api/auth/register", json={"name": "X", "email": "not-an-email", "password": PASSWORD})
    assert bad_email.status_code == 422


def test_public_registration_cannot_create_admin(client):                     # TC-35, UM-7
    res = client.post("/api/auth/register",
                      json={"name": "Eve", "email": "eve@example.com", "password": PASSWORD, "role": "admin"})
    assert res.status_code == 201 and res.json()["role"] == "customer"


def test_login_errors_are_generic(client):
    register(client, "carol@example.com")
    wrong = client.post("/api/auth/login", json={"email": "carol@example.com", "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == "Invalid email or password"


def test_chat_requires_login(client):                                         # TC-29
    assert client.post("/api/chat", json={"message": "rice"}).status_code == 401
    assert client.get("/api/conversations").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_expired_token_is_rejected(client, services, settings):               # TC-28
    user = services.users.get_by_email(register(client, "dan@example.com")["email"])
    expired = create_token(user.user_id, user.role, settings.jwt_secret, hours=-1)
    res = client.get("/api/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401 and "expired" in res.json()["detail"]


def test_customers_cannot_see_each_others_conversations(client, customer):    # TC-30
    first = chat(client, customer, "Cheapest rice?")
    register(client, "mallory@example.com")
    other = login_headers(client, "mallory@example.com")
    assert client.get(f"/api/conversations/{first['conversation_id']}", headers=other).status_code == 403
    assert client.delete(f"/api/conversations/{first['conversation_id']}", headers=other).status_code == 403
    res = client.post("/api/chat", json={"message": "hi", "conversation_id": first["conversation_id"]}, headers=other)
    assert res.status_code == 403
    assert client.get("/api/conversations", headers=other).json() == []


def test_customers_cannot_use_admin_endpoints(client, customer):              # TC-31
    for method, path in [("get", "/api/admin/users"), ("get", "/api/admin/audit"), ("get", "/api/admin/sources"),
                         ("post", "/api/admin/refresh"), ("patch", "/api/admin/users/1")]:
        kwargs = {"json": {"is_active": False}} if method == "patch" else {}
        assert getattr(client, method)(path, headers=customer, **kwargs).status_code == 403


def test_admin_can_review_history_and_is_audited(client, customer, admin, services):   # TC-32, TC-33
    first = chat(client, customer, "A rain jacket and a power bank")
    alice = services.users.get_by_email("alice@example.com")
    users = client.get("/api/admin/users?search=alice", headers=admin).json()
    assert [u["email"] for u in users] == ["alice@example.com"]

    convs = client.get(f"/api/admin/users/{alice.user_id}/conversations", headers=admin).json()
    assert convs["conversations"][0]["conversation_id"] == first["conversation_id"]
    detail = client.get(f"/api/admin/conversations/{first['conversation_id']}", headers=admin).json()
    reply = [m for m in detail["messages"] if m["sender"] == "assistant"][0]
    assert {c["agent"] for c in reply["agent_calls"]} == {"clothes", "electronics"}

    audit = client.get("/api/admin/audit", headers=admin).json()
    assert len(audit) == 2 and {a["viewed_user_email"] for a in audit} == {"alice@example.com"}
    assert audit[0]["conversation_id"] == first["conversation_id"]


def test_deactivated_user_is_locked_out(client, customer, admin, services):   # TC-34, UM-6
    alice = services.users.get_by_email("alice@example.com")
    res = client.patch(f"/api/admin/users/{alice.user_id}", json={"is_active": False}, headers=admin)
    assert res.status_code == 200 and res.json()["is_active"] is False
    assert client.get("/api/me", headers=customer).status_code == 401       # old token rejected
    login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert login.status_code == 403 and login.json()["detail"] == "Account disabled"

    client.patch(f"/api/admin/users/{alice.user_id}", json={"is_active": True}, headers=admin)
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200


def test_admin_cannot_deactivate_themselves(client, admin, services):
    me = services.users.get_by_email("admin@example.com")
    res = client.patch(f"/api/admin/users/{me.user_id}", json={"is_active": False}, headers=admin)
    assert res.status_code == 400


def test_history_survives_logout_and_login(client, customer):                 # TC-36
    first = chat(client, customer, "Cheapest rice?")
    assert client.post("/api/auth/logout", headers=customer).status_code == 204
    again = login_headers(client, "alice@example.com")
    convs = client.get("/api/conversations", headers=again).json()
    assert [c["conversation_id"] for c in convs] == [first["conversation_id"]]
    data = chat(client, again, "and milk", first["conversation_id"])
    assert data["conversation_id"] == first["conversation_id"]


def test_deleted_conversation_is_hidden_but_kept_for_admins(client, customer, admin, services):   # TC-37
    first = chat(client, customer, "Cheapest rice?")
    cid = first["conversation_id"]
    assert client.delete(f"/api/conversations/{cid}", headers=customer).status_code == 204
    assert client.get("/api/conversations", headers=customer).json() == []
    assert client.get(f"/api/conversations/{cid}", headers=customer).status_code == 404
    alice = services.users.get_by_email("alice@example.com")
    convs = client.get(f"/api/admin/users/{alice.user_id}/conversations", headers=admin).json()["conversations"]
    assert convs[0]["is_deleted"] is True


def test_create_admin_script(settings, monkeypatch, capsys):                  # UM-7
    import importlib.util
    from pathlib import Path

    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("LOG_DIR", str(settings.log_dir))
    path = Path(__file__).resolve().parent.parent / "scripts" / "create_admin.py"
    spec = importlib.util.spec_from_file_location("create_admin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["create_admin.py", "--email", "root@example.com", "--name", "Root",
                                      "--password", PASSWORD])
    assert module.main() == 0
    from app.users.user_repository import UserRepository
    user = UserRepository(settings.app_db_path).get_by_email("root@example.com")
    assert user.role == "admin" and user.is_active
