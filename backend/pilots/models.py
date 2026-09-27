from django.conf import settings
from django.db import models


class Pilot(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONTRACT_PENDING = "CONTRACT_PENDING", "Contract pending"
        CONTRACT_ACCEPTED = "CONTRACT_ACCEPTED", "Contract accepted"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    code = models.CharField(max_length=32, unique=True)
    application = models.OneToOneField("applications.Application", on_delete=models.CASCADE, related_name="pilot")
    startup = models.ForeignKey("startups.Startup", on_delete=models.CASCADE, related_name="pilots")
    problem_statement = models.ForeignKey(
        "problem_statements.ProblemStatement", on_delete=models.CASCADE, related_name="pilots"
    )
    procurement_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_pilots"
    )
    field_evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="field_pilots"
    )
    location = models.CharField(max_length=240)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    joining_deadline = models.DateField(null=True, blank=True)
    duration_weeks = models.PositiveIntegerField(default=12)
    responsibilities = models.TextField(blank=True)
    government_support = models.TextField(blank=True)
    payment_conditions = models.TextField(blank=True)
    reporting_frequency = models.CharField(max_length=80, default="Weekly")
    security_requirements = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    kpi_locked = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="cancelled_pilots"
    )
    score_cache = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code


class Contract(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        CONTRACT_ACCEPTED = "CONTRACT_ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    class KPIMethod(models.TextChoices):
        MANUAL = "MANUAL", "Manual KPI entry"
        EXTRACT = "EXTRACT", "Extract KPIs from signed contract"

    pilot = models.OneToOneField(Pilot, on_delete=models.CASCADE, related_name="contract")
    contract_no = models.CharField(max_length=48, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    kpi_method = models.CharField(max_length=16, choices=KPIMethod.choices, default=KPIMethod.MANUAL)
    body_text = models.TextField(blank=True)
    unsigned_key = models.CharField(max_length=400, blank=True)
    signed_key = models.CharField(max_length=400, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    replacement_log = models.JSONField(default=list, blank=True)
    extracted_kpis = models.JSONField(default=list, blank=True)
    extraction_demo = models.BooleanField(default=False)
    extraction_notice = models.TextField(blank=True)
    kpis_finalized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Milestone(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETE = "COMPLETE", "Complete"
        DELAYED = "DELAYED", "Delayed"

    pilot = models.ForeignKey(Pilot, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_week = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "due_week"]


class KPI(models.Model):
    class Priority(models.TextChoices):
        MUST_HAVE = "MUST_HAVE", "MUST HAVE"
        BETTER_TO_HAVE = "BETTER_TO_HAVE", "BETTER TO HAVE"
        NICE_TO_HAVE = "NICE_TO_HAVE", "NICE TO HAVE"

    class Direction(models.TextChoices):
        HIGHER_IS_BETTER = "HIGHER_IS_BETTER", "Higher is better"
        LOWER_IS_BETTER = "LOWER_IS_BETTER", "Lower is better"

    pilot = models.ForeignKey(Pilot, on_delete=models.CASCADE, related_name="kpis")
    name = models.CharField(max_length=160)
    target = models.FloatField()
    unit = models.CharField(max_length=40)
    weight = models.FloatField()
    priority = models.CharField(max_length=24, choices=Priority.choices, default=Priority.MUST_HAVE)
    direction = models.CharField(max_length=24, choices=Direction.choices, default=Direction.HIGHER_IS_BETTER)
    max_score = models.FloatField(default=120)
    source = models.CharField(max_length=16, default="MANUAL")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
