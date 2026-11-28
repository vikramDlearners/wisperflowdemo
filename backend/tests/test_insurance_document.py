"""Insurance policy documents (PDF or photo): attached to a policy, and read to fill in the Add policy form."""

import pytest

from app.core.config import settings
from app.models.membership import FamilyMember
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services import insurance_document
from app.services.auth import create_auth_session

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture()
def setup(db_session, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    manager = User(email="manager@example.com", display_name="Priya")
    viewer = User(email="viewer@example.com", display_name="Viewer")
    outsider = User(email="o@example.com", display_name="Outsider")
    db_session.add_all([manager, viewer, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    viewer_role = db_session.query(Role).filter_by(family_id=family.id, name="Viewer").one()
    db_session.add(FamilyMember(family_id=family.id, user_id=viewer.id, role_id=viewer_role.id, status="active"))
    db_session.commit()

    def h(u):
        return {"Authorization": f"Bearer {create_auth_session(db_session, u.id)}"}

    base = f"/api/families/{family.id}/insurance"
    return {"base": base, "manager": manager, "viewer": viewer, "outsider": outsider, "h": h}


def _policy(client, s):
    r = client.post(s["base"], json={"insurer": "Star Health", "renewal_date": "2026-12-15"}, headers=s["h"](s["manager"]))
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, s, policy_id, content=PDF, mime="application/pdf", name="policy.pdf", user=None):
    return client.put(
        f"{s['base']}/{policy_id}/document",
        files={"file": (name, content, mime)},
        headers=s["h"](user or s["manager"]),
    )


def test_attach_open_and_remove_a_pdf(client, setup):
    p = _policy(client, setup)
    assert p["has_document"] is False
    r = _upload(client, setup, p["id"])
    assert r.status_code == 200, r.text
    assert r.json()["has_document"] is True
    assert r.json()["document_name"] == "policy.pdf"

    got = client.get(f"{setup['base']}/{p['id']}/document", headers=setup["h"](setup["viewer"]))
    assert got.status_code == 200
    assert got.content == PDF
    assert got.headers["content-type"] == "application/pdf"

    assert client.delete(f"{setup['base']}/{p['id']}/document", headers=setup["h"](setup["manager"])).json()[
        "has_document"] is False
    assert client.get(f"{setup['base']}/{p['id']}/document", headers=setup["h"](setup["manager"])).status_code == 404


def test_a_photo_works_too(client, setup):
    p = _policy(client, setup)
    assert _upload(client, setup, p["id"], PNG, "image/png", "card.png").status_code == 200


@pytest.mark.parametrize(
    "content, mime",
    [
        (b"hello", "text/plain"),  # not a PDF or picture
        (b"not really a pdf", "application/pdf"),  # says PDF, isn't one
        (b"", "application/pdf"),
        (b"%PDF" + b"x" * (10 * 1024 * 1024), "application/pdf"),  # over 10 MB
    ],
    ids=["text", "fake-pdf", "empty", "too-big"],
)
def test_bad_files_are_refused(client, setup, content, mime):
    p = _policy(client, setup)
    assert _upload(client, setup, p["id"], content, mime).status_code == 400


def test_only_editors_can_attach_and_only_members_can_open(client, setup):
    p = _policy(client, setup)
    assert _upload(client, setup, p["id"], user=setup["viewer"]).status_code == 403
    _upload(client, setup, p["id"])
    assert client.get(f"{setup['base']}/{p['id']}/document", headers=setup["h"](setup["outsider"])).status_code == 403


def test_read_document_fills_the_form(client, setup, monkeypatch):
    seen = {}

    def fake(prompt, data, mime):
        seen["mime"] = mime
        return {
            "policy_type": "health", "insurer": "Star Health and Allied Insurance", "plan_name": "Red Carpet",
            "policy_number": "P/211/2026/001234", "sum_insured": "5,00,000", "premium": 28450.5,
            "premium_frequency": "yearly", "start_date": "2025-12-16", "renewal_date": "2026-12-15",
            "insured_name": "Lakshmi", "helpline": "1800 425 2255", "agent_name": None, "agent_phone": "bad",
        }

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(insurance_document, "ask_gemini_image", fake)
    r = client.post(f"{setup['base']}/read-document", files={"file": ("p.pdf", PDF, "application/pdf")},
                    headers=setup["h"](setup["manager"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen["mime"] == "application/pdf"
    assert body["source"] == "gemini"
    assert body["insurer"] == "Star Health and Allied Insurance"
    assert body["renewal_date"] == "2026-12-15"
    assert float(body["sum_insured"]) == 500000
    assert float(body["premium"]) == 28450.5
    assert body["helpline"] == "1800 425 2255"
    assert body["insured_name"] == "Lakshmi"


def test_read_document_without_gemini_says_so(client, setup):
    r = client.post(f"{setup['base']}/read-document", files={"file": ("p.pdf", PDF, "application/pdf")},
                    headers=setup["h"](setup["manager"]))
    assert r.status_code == 200
    assert r.json()["source"] == "none"
    assert r.json()["insurer"] is None


def test_read_document_when_gemini_fails(client, setup, monkeypatch):
    def boom(*a):
        raise RuntimeError("down")

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(insurance_document, "ask_gemini_image", boom)
    r = client.post(f"{setup['base']}/read-document", files={"file": ("p.png", PNG, "image/png")},
                    headers=setup["h"](setup["manager"]))
    assert r.status_code == 200
    assert r.json()["source"] == "none"
