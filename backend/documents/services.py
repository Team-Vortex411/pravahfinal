from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from common.audit import notify
from documents.models import Document


def apply_expiry_state(doc, today=None):
    today = today or timezone.localdate()
    soon = today + timedelta(days=settings.DOCUMENT_EXPIRY_SOON_DAYS)
    if doc.verification_status in {Document.Verification.REJECTED, Document.Verification.PENDING_VERIFICATION}:
        return False
    if doc.no_expiry or not doc.expiry_date:
        if doc.verification_status != Document.Verification.VERIFIED_VALID or not doc.currently_valid:
            doc.verification_status = Document.Verification.VERIFIED_VALID
            doc.currently_valid = True
            doc.save(update_fields=["verification_status", "currently_valid"])
            return True
        return False
    changed = False
    if doc.expiry_date < today:
        if doc.verification_status != Document.Verification.EXPIRED or doc.currently_valid:
            doc.verification_status = Document.Verification.EXPIRED
            doc.currently_valid = False
            changed = True
            if doc.startup_id:
                notify(
                    "Document expired",
                    f"Your {doc.get_document_type_display()} has expired and is no longer valid for a new application. Upload a renewed document for verification.",
                    category="DOCUMENT_EXPIRY",
                    link="/startup/documents",
                    recipient=doc.startup.user,
                )
    elif doc.expiry_date <= soon:
        if doc.verification_status != Document.Verification.EXPIRING_SOON:
            doc.verification_status = Document.Verification.EXPIRING_SOON
            doc.currently_valid = True
            changed = True
            if doc.startup_id:
                notify(
                    "Document expiring soon",
                    f"Your {doc.get_document_type_display()} will expire on {doc.expiry_date.isoformat()}. Please upload the renewed document.",
                    category="DOCUMENT_EXPIRY",
                    link="/startup/documents",
                    recipient=doc.startup.user,
                )
    else:
        if doc.verification_status != Document.Verification.VERIFIED_VALID or not doc.currently_valid:
            doc.verification_status = Document.Verification.VERIFIED_VALID
            doc.currently_valid = True
            changed = True
    if changed:
        doc.save(update_fields=["verification_status", "currently_valid"])
    return changed


def scan_expiries():
    today = timezone.localdate()
    count = 0
    qs = Document.objects.select_related("startup__user").exclude(
        verification_status__in=[Document.Verification.REJECTED, Document.Verification.PENDING_VERIFICATION]
    )
    for doc in qs:
        if apply_expiry_state(doc, today):
            count += 1
    return count
