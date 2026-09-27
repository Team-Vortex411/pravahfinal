from django.conf import settings
from django.db import models


class Evaluation(models.Model):
    class Decision(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVE_FOR_PILOT = "APPROVE_FOR_PILOT", "Approve for pilot"
        REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION", "Request clarification"
        REJECT = "REJECT", "Reject"

    application = models.OneToOneField("applications.Application", on_delete=models.CASCADE, related_name="evaluation")
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="evaluations"
    )
    scores = models.JSONField(default=dict)
    comments = models.TextField(blank=True)
    decision = models.CharField(max_length=32, choices=Decision.choices, default=Decision.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def composite_out_of_10(self):
        vals = [float(v) for v in (self.scores or {}).values() if v is not None and v != ""]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 2)
