from django.conf import settings
from django.db import models


class Recommendation(models.Model):
    class Choice(models.TextChoices):
        CONSIDER_PROCUREMENT = "CONSIDER_PROCUREMENT", "Consider Procurement"
        CONSIDER_SCALEUP = "CONSIDER_SCALEUP", "Consider Scale-up"
        ADDITIONAL_PILOT = "ADDITIONAL_PILOT", "Request Additional Pilot"
        CLARIFICATION = "CLARIFICATION", "Request Clarification"
        DO_NOT_RECOMMEND = "DO_NOT_RECOMMEND", "Do Not Recommend"

    pilot = models.OneToOneField("pilots.Pilot", on_delete=models.CASCADE, related_name="recommendation")
    choice = models.CharField(max_length=32, choices=Choice.choices, blank=True)
    narrative = models.TextField(blank=True)
    scaleup_tips = models.JSONField(default=dict, blank=True)
    evidence_report = models.TextField(blank=True)
    officer_note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="recommendations"
    )
    ai_demo = models.BooleanField(default=False)
    ai_notice = models.TextField(blank=True)
    evidence_links = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
