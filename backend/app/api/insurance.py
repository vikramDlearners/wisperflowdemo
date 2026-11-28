"""Insurance policies of a family and their renewals (see services/insurance.py for who may do what)."""

from fastapi import APIRouter, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.insurance import InsurancePolicy
from app.models.user import User
from app.schemas import InsuranceDocumentRead, InsuranceIn, InsuranceOut, InsuranceRenewIn, InsuranceUpdate
from app.services import insurance as svc
from app.services import insurance_document as docs

router = APIRouter(prefix="/api/families/{family_id}/insurance", tags=["insurance"])


def _out(p: InsurancePolicy) -> InsuranceOut:
    return InsuranceOut(
        id=p.id, care_profile_id=p.care_profile_id, policy_type=p.policy_type, insurer=p.insurer,
        plan_name=p.plan_name, policy_number=p.policy_number, sum_insured=p.sum_insured, premium=p.premium,
        premium_frequency=p.premium_frequency, start_date=p.start_date, renewal_date=p.renewal_date,
        last_renewed_on=p.last_renewed_on, agent_name=p.agent_name, agent_phone=p.agent_phone,
        helpline=p.helpline, notes=p.notes, responsible_user_id=p.responsible_user_id,
        has_document=p.document_content_type is not None, document_name=p.document_name,
        document_type=p.document_content_type,
    )


def _read(file: UploadFile) -> bytes:
    return file.file.read(docs.MAX_BYTES + 1)  # one byte over, so a too-big file is refused


@router.get("", response_model=list[InsuranceOut])
def list_policies(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[InsuranceOut]:
    return [_out(p) for p in svc.list_policies(db, user.id, family_id)]


@router.post("", response_model=InsuranceOut, status_code=201)
def create_policy(
    family_id: str, body: InsuranceIn, db: Session = DbSession, user: User = CurrentUser
) -> InsuranceOut:
    return _out(svc.create_policy(db, user.id, family_id, body.model_dump()))


@router.post("/read-document", response_model=InsuranceDocumentRead)
def read_document(
    family_id: str, file: UploadFile = File(...), db: Session = DbSession, user: User = CurrentUser
) -> InsuranceDocumentRead:
    """Read a policy PDF or photo to fill in the Add policy form. Nothing is saved."""
    return InsuranceDocumentRead(
        **docs.read_document(db, user.id, family_id, _read(file), file.content_type or "")
    )


@router.get("/{policy_id}", response_model=InsuranceOut)
def get_policy(family_id: str, policy_id: str, db: Session = DbSession, user: User = CurrentUser) -> InsuranceOut:
    return _out(svc.get_policy(db, user.id, family_id, policy_id))


@router.patch("/{policy_id}", response_model=InsuranceOut)
def update_policy(
    family_id: str, policy_id: str, body: InsuranceUpdate, db: Session = DbSession, user: User = CurrentUser
) -> InsuranceOut:
    return _out(svc.update_policy(db, user.id, family_id, policy_id, body.model_dump(exclude_unset=True)))


@router.post("/{policy_id}/renew", response_model=InsuranceOut)
def renew_policy(
    family_id: str, policy_id: str, body: InsuranceRenewIn, db: Session = DbSession, user: User = CurrentUser
) -> InsuranceOut:
    """Mark the premium paid: the renewal date moves on one period (or to the date given)."""
    return _out(svc.renew_policy(db, user.id, family_id, policy_id, body.renewal_date, body.premium))


@router.put("/{policy_id}/document", response_model=InsuranceOut)
def attach_document(
    family_id: str, policy_id: str, file: UploadFile = File(...),
    db: Session = DbSession, user: User = CurrentUser,
) -> InsuranceOut:
    return _out(docs.attach(db, user.id, family_id, policy_id, _read(file), file.content_type or "", file.filename))


@router.get("/{policy_id}/document")
def get_document(family_id: str, policy_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    data, content_type, name = docs.get_document(db, user.id, family_id, policy_id)
    safe = "".join(c for c in name if c.isprintable() and c not in '"\\')[:150] or "policy-document"
    return Response(
        content=data, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{safe}"', "Cache-Control": "private, no-store",
                 "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{policy_id}/document", response_model=InsuranceOut)
def remove_document(family_id: str, policy_id: str, db: Session = DbSession, user: User = CurrentUser) -> InsuranceOut:
    return _out(docs.detach(db, user.id, family_id, policy_id))


@router.delete("/{policy_id}", status_code=204)
def delete_policy(family_id: str, policy_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    svc.delete_policy(db, user.id, family_id, policy_id)
    return Response(status_code=204)
