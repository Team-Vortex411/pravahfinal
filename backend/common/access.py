from rest_framework.response import Response


def user_of(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return user


def require(request, *roles):
    user = user_of(request)
    if not user:
        return None, Response({"detail": "Authentication required."}, status=401)
    if roles and user.role not in roles:
        return None, Response({"detail": "You do not have access to this action."}, status=403)
    return user, None


def owns_startup(user, startup):
    return user and startup and startup.user_id == user.id


def can_view_application(user, app):
    if not user:
        return False
    if user.role == "GOVERNMENT_ADMIN":
        return True
    if user.role == "STARTUP":
        return app.startup.user_id == user.id
    if user.role == "TECHNICAL_EVALUATOR":
        return app.problem_statement.technical_evaluator_id in (None, user.id)
    if user.role == "PROCUREMENT_OFFICER":
        return app.problem_statement.procurement_officer_id in (None, user.id)
    if user.role == "FIELD_EVALUATOR":
        pilot = getattr(app, "pilot", None)
        try:
            pilot = app.pilot
        except Exception:
            pilot = None
        return bool(pilot and pilot.field_evaluator_id == user.id)
    return False


def can_view_pilot(user, pilot):
    if not user:
        return False
    if user.role == "GOVERNMENT_ADMIN":
        return True
    if user.role == "STARTUP":
        return pilot.startup.user_id == user.id
    if user.role == "PROCUREMENT_OFFICER":
        return pilot.procurement_officer_id in (None, user.id)
    if user.role == "FIELD_EVALUATOR":
        return pilot.field_evaluator_id == user.id
    if user.role == "TECHNICAL_EVALUATOR":
        return pilot.problem_statement.technical_evaluator_id in (None, user.id)
    return False


def can_view_document(user, doc):
    if not user:
        return False
    if user.role in {"GOVERNMENT_ADMIN", "TECHNICAL_EVALUATOR", "PROCUREMENT_OFFICER"}:
        if user.role == "TECHNICAL_EVALUATOR" and doc.application_id:
            return can_view_application(user, doc.application)
        return True
    if user.role == "FIELD_EVALUATOR":
        if doc.pilot_id:
            return doc.pilot.field_evaluator_id == user.id
        return False
    if user.role == "STARTUP":
        return doc.startup_id and doc.startup.user_id == user.id
    return False
