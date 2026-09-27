from django.conf import settings
from django.db import models


class Complaint(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESPONSE_REQUESTED = "RESPONSE_REQUESTED", "Startup response requested"
        RESPONDED = "RESPONDED", "Startup responded"
        ACCEPTED = "ACCEPTED", "Explanation accepted"
        ESCALATED = "ESCALATED", "Escalated"
        CLOSED = "CLOSED", "Closed"

    pilot = models.ForeignKey("pilots.Pilot", on_delete=models.CASCADE, related_name="complaints")
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints_raised"
    )
    category = models.CharField(max_length=80)
    description = models.TextField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.OPEN)
    startup_response = models.TextField(blank=True)
    officer_action = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
