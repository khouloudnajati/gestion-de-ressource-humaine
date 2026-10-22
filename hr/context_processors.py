def user_role(request):
    if not request.user.is_authenticated:
        return {}
    profile = getattr(request.user, "profile", None)
    role = getattr(profile, "role", None)
    is_hr = request.user.is_superuser or role in {"HR", "ADMIN"}
    unread = 0
    try:
        from .models import Notification
        unread = Notification.objects.filter(user=request.user, read=False).count()
    except Exception:
        pass
    return {
        "user_is_hr": is_hr,
        "user_is_admin": request.user.is_superuser or role == "ADMIN",
        "user_role": role,
        "unread_notifications": unread,
    }
