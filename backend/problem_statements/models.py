from django.conf import settings
from django.db import models


class ProblemStatement(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PILOT_ACTIVE = "PILOT_ACTIVE", "Pilot active"
        PILOT_COMPLETED = "PILOT_COMPLETED", "Pilot completed"
        CLOSED = "CLOSED", "Closed"

    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=240)
    description = models.TextField()
    department = models.ForeignKey("accounts.Department", on_delete=models.PROTECT, related_name="problem_statements")
    location = models.CharField(max_length=160)
    technology_domain = models.CharField(max_length=160)
    expected_outcome = models.TextField()
    technical_requirements = models.JSONField(default=list)
    eligibility_criteria = models.JSONField(default=list)
    required_documents = models.JSONField(default=list)
    application_deadline = models.DateField()
    pilot_joining_deadline = models.DateField()
    pilot_location = models.CharField(max_length=240)
    pilot_duration_weeks = models.PositiveIntegerField(default=12)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.OPEN)
    technical_evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="evaluating_problems"
    )
    procurement_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="procuring_problems"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_problems"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.title
