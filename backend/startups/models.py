from django.conf import settings
from django.db import models


class Startup(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="startup")
    company_name = models.CharField(max_length=200)
    domain = models.CharField(max_length=160)
    technologies = models.CharField(max_length=400)
    dpiit_number = models.CharField(max_length=64, blank=True)
    gstin = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    experience_years = models.PositiveIntegerField(default=0)
    team_size = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    capabilities = models.TextField(blank=True)
    relevant_experience = models.TextField(blank=True)
    contact_person = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_name"]

    def __str__(self):
        return self.company_name
