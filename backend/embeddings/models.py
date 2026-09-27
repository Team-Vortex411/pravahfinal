from django.db import models


class Embedding(models.Model):
    """384-d vector stored for pgvector-compatible similarity search.

    In DEMO_MODE / SQLite the vector is a JSON array and cosine similarity is
    computed in the embedding service. When USE_PGVECTOR is enabled against
    Neon PostgreSQL, the same rows can be migrated to a pgvector column.
    """

    class Entity(models.TextChoices):
        PROBLEM = "problem", "Problem statement"
        STARTUP = "startup", "Startup"

    entity_type = models.CharField(max_length=16, choices=Entity.choices)
    entity_id = models.PositiveIntegerField()
    vector = models.JSONField()
    source_text = models.TextField()
    model_name = models.CharField(max_length=160)
    dimensions = models.PositiveIntegerField(default=384)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("entity_type", "entity_id")]
