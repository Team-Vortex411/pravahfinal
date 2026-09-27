from django.conf import settings
from django.db import models


class Document(models.Model):
    class Type(models.TextChoices):
        DPIIT = "DPIIT", "DPIIT Recognition Certificate"
        GST = "GST", "GST Certificate"
        INCORPORATION = "INCORPORATION", "Company Incorporation / CIN"
        ISO_27001 = "ISO_27001", "ISO 27001"
        ISO_9001 = "ISO_9001", "ISO 9001"
        PAN = "PAN", "PAN"
        TECHNICAL_PROPOSAL = "TECHNICAL_PROPOSAL", "Technical Proposal (PPT)"
        SOLUTION = "SOLUTION", "Solution / PS document"
        SIGNED_CONTRACT = "SIGNED_CONTRACT", "Signed pilot contract"
        UNSIGNED_CONTRACT = "UNSIGNED_CONTRACT", "Unsigned pilot contract"
        WEEKLY_EVIDENCE = "WEEKLY_EVIDENCE", "Weekly report evidence"
        FINAL_EVIDENCE = "FINAL_EVIDENCE", "Final report evidence"
        OTHER = "OTHER", "Other"

    class Verification(models.TextChoices):
        VERIFIED_VALID = "VERIFIED_VALID", "Verified & valid"
        EXPIRING_SOON = "EXPIRING_SOON", "Expiring soon"
        EXPIRED = "EXPIRED", "Expired"
        PENDING_VERIFICATION = "PENDING_VERIFICATION", "Pending verification"
        REJECTED = "REJECTED", "Rejected"

    startup = models.ForeignKey("startups.Startup", null=True, blank=True, on_delete=models.CASCADE, related_name="documents")
    application = models.ForeignKey(
        "applications.Application", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
    pilot = models.ForeignKey("pilots.Pilot", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    name = models.CharField(max_length=240)
    document_type = models.CharField(max_length=40, choices=Type.choices)
    object_key = models.CharField(max_length=400)
    file_name = models.CharField(max_length=240)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    verification_status = models.CharField(
        max_length=32, choices=Verification.choices, default=Verification.PENDING_VERIFICATION
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_documents"
    )
    verified_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    no_expiry = models.BooleanField(default=False)
    currently_valid = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    replaces = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replacements")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
