from django.db import models


class Application(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        ELIGIBILITY_CHECK = "ELIGIBILITY_CHECK", "Eligibility check"
        REJECTED_DEADLINE = "REJECTED_DEADLINE", "Rejected — cannot meet pilot deadline"
        UNDER_TECHNICAL_EVALUATION = "UNDER_TECHNICAL_EVALUATION", "Under technical evaluation"
        CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED", "Clarification required"
        APPROVED_FOR_PILOT = "APPROVED_FOR_PILOT", "Approved for pilot"
        REJECTED = "REJECTED", "Rejected"
        CONTRACT_PENDING = "CONTRACT_PENDING", "Contract pending"
        PILOT_ACTIVE = "PILOT_ACTIVE", "Pilot active"
        PILOT_COMPLETED = "PILOT_COMPLETED", "Pilot completed"
        PILOT_CANCELLED = "PILOT_CANCELLED", "Pilot cancelled"

    class Readiness(models.TextChoices):
        YES = "YES", "Yes"
        NO = "NO", "No"

    code = models.CharField(max_length=32, unique=True)
    startup = models.ForeignKey("startups.Startup", on_delete=models.CASCADE, related_name="applications")
    problem_statement = models.ForeignKey(
        "problem_statements.ProblemStatement", on_delete=models.CASCADE, related_name="applications"
    )
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.SUBMITTED)
    eligibility_confirmed = models.BooleanField(default=False)
    eligibility_checks = models.JSONField(default=dict)
    pilot_readiness = models.CharField(max_length=8, choices=Readiness.choices, blank=True)
    proposal_text = models.TextField(blank=True)
    ai_analysis = models.JSONField(default=dict, blank=True)
    clarification_request = models.TextField(blank=True)
    clarification_response = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        unique_together = [("startup", "problem_statement")]

    def __str__(self):
        return self.code
