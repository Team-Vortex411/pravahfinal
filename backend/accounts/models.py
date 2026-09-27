from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=160, unique=True)
    code = models.CharField(max_length=16, unique=True)
    ministry = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        GOVERNMENT_ADMIN = "GOVERNMENT_ADMIN", "Government Administrator"
        TECHNICAL_EVALUATOR = "TECHNICAL_EVALUATOR", "Technical Evaluator"
        PROCUREMENT_OFFICER = "PROCUREMENT_OFFICER", "Procurement Officer"
        FIELD_EVALUATOR = "FIELD_EVALUATOR", "Field Evaluator"
        STARTUP = "STARTUP", "Startup"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.STARTUP)
    phone = models.CharField(max_length=20, blank=True)
    employee_id = models.CharField(max_length=32, blank=True)
    designation = models.CharField(max_length=160, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.role})"

    @property
    def display_name(self):
        return self.get_full_name() or self.email
