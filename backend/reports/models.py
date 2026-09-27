from django.conf import settings
from django.db import models


class WeeklyReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUBMITTED = "SUBMITTED", "Submitted on time"
        LATE = "LATE", "Late"
        VERIFIED = "VERIFIED", "Verified"
        NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION", "Needs clarification"
        REJECTED = "REJECTED", "Rejected"

    pilot = models.ForeignKey("pilots.Pilot", on_delete=models.CASCADE, related_name="weekly_reports")
    week = models.PositiveIntegerField()
    narrative = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    kpi_claims = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    due_date = models.DateField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    delay_reason = models.TextField(blank=True)
    delay_review = models.CharField(max_length=32, blank=True)
    delay_review_note = models.TextField(blank=True)
    verification_status = models.CharField(max_length=32, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_weekly_reports"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    observations = models.TextField(blank=True)
    ai_progress = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["week"]
        unique_together = [("pilot", "week")]


class WeeklyKPIResult(models.Model):
    report = models.ForeignKey(WeeklyReport, on_delete=models.CASCADE, related_name="results")
    kpi = models.ForeignKey("pilots.KPI", on_delete=models.CASCADE, related_name="weekly_results")
    actual = models.FloatField()
    unit = models.CharField(max_length=40, blank=True)
    evidence_ref = models.CharField(max_length=240, blank=True)
    note = models.CharField(max_length=400, blank=True)

    class Meta:
        unique_together = [("report", "kpi")]


class FinalReport(models.Model):
    pilot = models.OneToOneField("pilots.Pilot", on_delete=models.CASCADE, related_name="final_report")
    narrative = models.TextField(blank=True)
    kpi_claims = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(max_length=32, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_final_reports"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    observations = models.TextField(blank=True)
    extracted_kpis = models.JSONField(default=list, blank=True)
    extraction_demo = models.BooleanField(default=False)
    ai_analysis = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FieldVerification(models.Model):
    class Status(models.TextChoices):
        VERIFIED = "VERIFIED", "Verified"
        NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION", "Needs clarification"
        NOT_VERIFIED = "NOT_VERIFIED", "Not verified"

    pilot = models.ForeignKey("pilots.Pilot", on_delete=models.CASCADE, related_name="field_verifications")
    weekly_report = models.ForeignKey(WeeklyReport, null=True, blank=True, on_delete=models.CASCADE, related_name="verifications")
    final_report = models.ForeignKey(FinalReport, null=True, blank=True, on_delete=models.CASCADE, related_name="verifications")
    verifier = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="field_verifications"
    )
    status = models.CharField(max_length=32, choices=Status.choices)
    observations = models.TextField(blank=True)
    activity_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
