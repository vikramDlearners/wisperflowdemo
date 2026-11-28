"""Medical file, siblings, paperwork, the carer's day and video check-ins.

Family, under /api/families/{family_id}/care-profiles/{care_profile_id} unless noted:
GET    /medical-file?q=                 documents, newest or best match first
POST   /medical-file                    upload a PDF or photo, or type the words
GET    /api/families/{fid}/medical-file/{doc_id}/file      DELETE /api/families/{fid}/medical-file/{doc_id}
GET/POST /medical-file/links            share links for a doctor   DELETE /api/families/{fid}/medical-links/{id}
GET    /sharing                         money, visits and the last appointment
POST   /expenses   POST /visits         DELETE /api/families/{fid}/expenses/{id}
GET    /paperwork  POST /paperwork  POST /paperwork/usual
POST   /api/families/{fid}/paperwork/{id}/done              DELETE /api/families/{fid}/paperwork/{id}
GET    /carer      POST /carer/meals  POST /carer/doses  POST /carer/reports
POST   /calls                           ring the parent
GET    /api/families/{fid}/calls/{id}   POST /api/families/{fid}/calls/{id}/end

Parent: GET /api/parent/calls/incoming, POST /api/parent/calls/{id}/answer, POST /api/parent/calls/{id}/end
Doctor, no sign-in: GET /api/medical-file/{token}, GET /api/medical-file/{token}/documents/{doc_id}
"""

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.care_circle import MedicalDocument, MedicalShareLink, VideoCall
from app.models.user import User
from app.services import care_family as fam
from app.services import medical_file as mf
from app.services import video_calls as calls
from app.services.doses import today_for
from app.services.insurance_document import MAX_BYTES
from app.services.parent_context import resolve_parent

P = "/care-profiles/{care_profile_id}"
family_router = APIRouter(prefix="/api/families/{family_id}", tags=["care-family"])
parent_router = APIRouter(prefix="/api/parent/calls", tags=["care-family"])
public_router = APIRouter(prefix="/api/medical-file/{token}", tags=["care-family"])
ProfileId = Header(default=None, alias="X-Care-Profile-Id")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _bad_input():
    try:
        yield
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _doc(d: MedicalDocument, file_url: str | None, match: str | None = None) -> dict:
    return {"id": d.id, "kind": d.kind, "title": d.title, "doc_date": d.doc_date, "text": d.text,
            "has_file": d.content_type is not None, "file_name": d.file_name, "created_at": d.created_at,
            "file_url": file_url if d.content_type is not None else None, "match": match}


def _link(link: MedicalShareLink) -> dict:
    return {"id": link.id, "token": mf.token_for(link), "expires_at": link.expires_at, "created_at": link.created_at}


def _file(d: MedicalDocument) -> Response:
    name = (d.file_name or "document").replace('"', "")
    return Response(content=d.data, media_type=d.content_type,
                    headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store",
                             "X-Content-Type-Options": "nosniff"})


def _call(c: VideoCall) -> dict:
    return {"id": c.id, "status": c.status, "answer": c.answer}


def _profile_today(db: Session, family_id: str, care_profile_id: str) -> date:
    from app.services.care_circle import _profile_in

    return today_for(_profile_in(db, family_id, care_profile_id), _now())


# ---------- medical file ----------

@family_router.get(P + "/medical-file")
def list_documents(family_id: str, care_profile_id: str, q: str | None = None, db: Session = DbSession,
                   user: User = CurrentUser) -> list[dict]:
    base = f"/api/families/{family_id}/medical-file"
    return [_doc(r["doc"], f"{base}/{r['doc'].id}/file", r["match"])
            for r in mf.search(db, user.id, family_id, care_profile_id, q)]


@family_router.post(P + "/medical-file", status_code=201)
def add_document(family_id: str, care_profile_id: str, kind: str | None = Form(default=None),
                 title: str | None = Form(default=None, max_length=160), doc_date: date | None = Form(default=None),
                 text: str | None = Form(default=None, max_length=20000), file: UploadFile | None = File(default=None),
                 db: Session = DbSession, user: User = CurrentUser) -> dict:
    data = file.file.read(MAX_BYTES + 1) if file is not None else None
    with _bad_input():
        doc = mf.add_document(db, user.id, family_id, care_profile_id, kind=kind or None, title=title,
                              doc_date=doc_date, text=text, data=data,
                              mime=file.content_type if file is not None else None,
                              file_name=file.filename if file is not None else None, now=_now())
    return _doc(doc, f"/api/families/{family_id}/medical-file/{doc.id}/file")


@family_router.get("/medical-file/{doc_id}/file")
def document_file(family_id: str, doc_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    doc = mf.family_document(db, user.id, family_id, doc_id)
    if doc.content_type is None:
        raise HTTPException(status_code=404, detail="This document has no file")
    return _file(doc)


@family_router.delete("/medical-file/{doc_id}", status_code=204)
def delete_document(family_id: str, doc_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    mf.delete_document(db, user.id, family_id, doc_id)
    return Response(status_code=204)


class ShareIn(BaseModel):
    days: int = 7


@family_router.get(P + "/medical-file/links")
def list_links(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[dict]:
    return [_link(x) for x in mf.links(db, user.id, family_id, care_profile_id, _now())]


@family_router.post(P + "/medical-file/links", status_code=201)
def share_file(family_id: str, care_profile_id: str, body: ShareIn, db: Session = DbSession,
               user: User = CurrentUser) -> dict:
    with _bad_input():
        return _link(mf.share(db, user.id, family_id, care_profile_id, body.days, _now()))


@family_router.delete("/medical-links/{link_id}", status_code=204)
def revoke_link(family_id: str, link_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    mf.revoke(db, user.id, family_id, link_id, _now())
    return Response(status_code=204)


@public_router.get("")
def shared_file(token: str, db: Session = DbSession) -> dict:
    link, card, docs = mf.shared_file(db, token, _now())
    return {"card": card, "expires_at": link.expires_at,
            "documents": [_doc(d, f"/api/medical-file/{token}/documents/{d.id}") for d in docs]}


@public_router.get("/documents/{doc_id}")
def shared_document(token: str, doc_id: str, db: Session = DbSession) -> Response:
    doc = mf.shared_document(db, token, doc_id, _now())
    if doc.content_type is None:
        raise HTTPException(status_code=404, detail="This document has no file")
    return _file(doc)


# ---------- siblings ----------

class ExpenseIn(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("10000000"))
    what: str = Field(max_length=160)
    spent_on: date
    paid_by_user_id: str | None = None


class VisitIn(BaseModel):
    visit_date: date
    appointment_id: str | None = None
    note: str | None = Field(default=None, max_length=240)


@family_router.get(P + "/sharing")
def sharing(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    return fam.sharing(db, user.id, family_id, care_profile_id, _profile_today(db, family_id, care_profile_id))


@family_router.post(P + "/expenses", status_code=201)
def add_expense(family_id: str, care_profile_id: str, body: ExpenseIn, db: Session = DbSession,
                user: User = CurrentUser) -> dict:
    with _bad_input():
        row = fam.add_expense(db, user.id, family_id, care_profile_id, body.amount, body.what, body.spent_on,
                              body.paid_by_user_id)
    return {"id": row.id}


@family_router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(family_id: str, expense_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    fam.delete_expense(db, user.id, family_id, expense_id)
    return Response(status_code=204)


@family_router.post(P + "/visits", status_code=201)
def add_visit(family_id: str, care_profile_id: str, body: VisitIn, db: Session = DbSession,
              user: User = CurrentUser) -> dict:
    row = fam.add_visit(db, user.id, family_id, care_profile_id, body.visit_date, body.appointment_id, body.note)
    return {"id": row.id}


# ---------- paperwork ----------

class PaperIn(BaseModel):
    kind: str
    title: str | None = Field(default=None, max_length=160)
    due_date: date
    note: str | None = Field(default=None, max_length=1000)


@family_router.get(P + "/paperwork")
def list_paperwork(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[dict]:
    return fam.paperwork(db, user.id, family_id, care_profile_id, _profile_today(db, family_id, care_profile_id))


@family_router.post(P + "/paperwork", status_code=201)
def add_paperwork(family_id: str, care_profile_id: str, body: PaperIn, db: Session = DbSession,
                  user: User = CurrentUser) -> dict:
    with _bad_input():
        row = fam.add_paperwork(db, user.id, family_id, care_profile_id, body.kind, body.title, body.due_date,
                                body.note)
    return {"id": row.id}


@family_router.post(P + "/paperwork/usual", status_code=201)
def add_usual(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    rows = fam.add_usual(db, user.id, family_id, care_profile_id, _profile_today(db, family_id, care_profile_id))
    return {"added": len(rows)}


@family_router.post("/paperwork/{item_id}/done")
def done_paperwork(family_id: str, item_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    nxt = fam.done_paperwork(db, user.id, family_id, item_id, _now().date())
    return {"next_due": nxt.due_date if nxt else None}


@family_router.delete("/paperwork/{item_id}", status_code=204)
def delete_paperwork(family_id: str, item_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    fam.delete_paperwork(db, user.id, family_id, item_id)
    return Response(status_code=204)


# ---------- carer ----------

class MealIn(BaseModel):
    meal: str
    note: str | None = Field(default=None, max_length=500)


class DoseIn(BaseModel):
    medicine_id: str
    slot: str
    status: str


class ReportIn(BaseModel):
    kind: str
    text: str = Field(max_length=2000)


@family_router.get(P + "/carer")
def carer_day(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    return fam.carer_day(db, user.id, family_id, care_profile_id, _now())


@family_router.post(P + "/carer/meals", status_code=204)
def carer_meal(family_id: str, care_profile_id: str, body: MealIn, db: Session = DbSession,
               user: User = CurrentUser) -> Response:
    with _bad_input():
        fam.carer_meal(db, user.id, family_id, care_profile_id, body.meal, body.note, _now())
    return Response(status_code=204)


@family_router.post(P + "/carer/doses", status_code=204)
def carer_dose(family_id: str, care_profile_id: str, body: DoseIn, db: Session = DbSession,
               user: User = CurrentUser) -> Response:
    with _bad_input():
        fam.carer_dose(db, user.id, family_id, care_profile_id, body.medicine_id, body.slot, body.status, _now())
    return Response(status_code=204)


@family_router.post(P + "/carer/reports", status_code=201)
def carer_report(family_id: str, care_profile_id: str, body: ReportIn, db: Session = DbSession,
                 user: User = CurrentUser) -> dict:
    with _bad_input():
        row = fam.carer_report(db, user.id, family_id, care_profile_id, body.kind, body.text, _now())
    return {"id": row.id}


# ---------- video check-ins ----------

class SdpIn(BaseModel):
    sdp: str = Field(max_length=calls.MAX_SDP)


@family_router.post(P + "/calls", status_code=201)
def start_call(family_id: str, care_profile_id: str, body: SdpIn, db: Session = DbSession,
               user: User = CurrentUser) -> dict:
    with _bad_input():
        return _call(calls.start(db, user.id, family_id, care_profile_id, body.sdp, _now()))


@family_router.get("/calls/{call_id}")
def get_call(family_id: str, call_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    return _call(calls.family_call(db, user.id, family_id, call_id, _now()))


@family_router.post("/calls/{call_id}/end")
def end_call(family_id: str, call_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    now = _now()
    return _call(calls.hang_up(calls.family_call(db, user.id, family_id, call_id, now), db, now))


@parent_router.get("/incoming")
def incoming(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> dict | None:
    return calls.incoming(db, resolve_parent(db, user, profile_id), _now())


@parent_router.get("/{call_id}")
def parent_get_call(call_id: str, db: Session = DbSession, user: User = CurrentUser,
                    profile_id: str | None = ProfileId) -> dict:
    return _call(calls.parent_call(db, resolve_parent(db, user, profile_id), call_id))


@parent_router.post("/{call_id}/answer")
def answer_call(call_id: str, body: SdpIn, db: Session = DbSession, user: User = CurrentUser,
                profile_id: str | None = ProfileId) -> dict:
    with _bad_input():
        return _call(calls.answer(db, resolve_parent(db, user, profile_id), call_id, body.sdp, _now()))


@parent_router.post("/{call_id}/end")
def parent_end_call(call_id: str, db: Session = DbSession, user: User = CurrentUser,
                    profile_id: str | None = ProfileId) -> dict:
    call = calls.parent_call(db, resolve_parent(db, user, profile_id), call_id)
    return _call(calls.hang_up(call, db, _now()))
