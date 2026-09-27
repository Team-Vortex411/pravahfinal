from notifications.models import AuditLog, Notification


def audit(actor, action, entity, entity_id="", detail=""):
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity=entity,
        entity_id=str(entity_id or ""),
        detail=detail or "",
    )


def notify(title, body, category="INFO", link="", recipient=None, role=""):
    return Notification.objects.create(
        recipient=recipient,
        role=role or "",
        title=title,
        body=body,
        category=category,
        link=link or "",
    )
