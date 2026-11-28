"""Prescription photo scans for a care profile. Upload and confirm need medicines.edit; viewing needs medicines.view."""

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.prescription_scan import PrescriptionScan
from app.models.user import User
from app.schemas import PrescriptionScanConfirm, PrescriptionScanConfirmOut, PrescriptionScanOut
from app.services import prescription_scan as svc

router = APIRouter(
    prefix="/api/families/{family_id}/care-profiles/{care_profile_id}/prescription-scans",
    tags=["prescription_scans"],
)


def _out(scan: PrescriptionScan) -> PrescriptionScanOut:
    return PrescriptionScanOut(
        id=scan.id,
        document_type=scan.document_type,
        status=scan.status,
        proposed=scan.proposed,
        tracking=svc.tracking_lines(scan.proposed),
    )


@router.post("", response_model=PrescriptionScanOut, status_code=201)
def upload_prescription_scan(
    family_id: str,
    care_profile_id: str,
    file: UploadFile = File(...),
    db: Session = DbSession,
    user: User = CurrentUser,
) -> PrescriptionScanOut:
    # Read one byte past the limit so the service can reject oversized uploads.
    image_bytes = file.file.read(svc.MAX_IMAGE_BYTES + 1)
    try:
        scan = svc.create_scan(db, user.id, family_id, care_profile_id, image_bytes, file.content_type or "")
    except svc.PrescriptionScanUpstreamError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Prescription scanning is temporarily unavailable") from exc
    return _out(scan)


@router.get("/{scan_id}", response_model=PrescriptionScanOut)
def get_prescription_scan(
    family_id: str, care_profile_id: str, scan_id: str, db: Session = DbSession, user: User = CurrentUser
) -> PrescriptionScanOut:
    return _out(svc.get_scan(db, user.id, family_id, care_profile_id, scan_id))


@router.post("/{scan_id}/confirm", response_model=PrescriptionScanConfirmOut)
def confirm_prescription_scan(
    family_id: str,
    care_profile_id: str,
    scan_id: str,
    body: PrescriptionScanConfirm,
    db: Session = DbSession,
    user: User = CurrentUser,
) -> PrescriptionScanConfirmOut:
    medicine_ids, notified_user_ids = svc.confirm_scan(
        db,
        user.id,
        family_id,
        care_profile_id,
        scan_id,
        [medicine.model_dump() for medicine in body.medicines],
    )
    return PrescriptionScanConfirmOut(medicine_ids=medicine_ids, notified_user_ids=notified_user_ids)
