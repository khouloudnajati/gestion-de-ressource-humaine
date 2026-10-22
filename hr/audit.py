"""Journal de traçabilité des actions importantes (cahier des charges §6.8)."""
from .models import AuditLog


def log_action(user, action, details=""):
    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        details=details,
    )
