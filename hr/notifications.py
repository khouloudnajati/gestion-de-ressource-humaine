"""Notifications in-app et e-mail pour RHziz."""
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Q

from .models import Notification, Profile


def _hr_users():
    return User.objects.filter(
        Q(is_superuser=True) | Q(profile__role__in=[Profile.Role.HR, Profile.Role.ADMIN])
    ).distinct()


def notify_user(user, title, message, *, send_email=True, category=None, priority=None):
    if not user:
        return
    notif = Notification.objects.create(
        user=user, 
        title=title, 
        message=message,
        category=category or Notification.Category.SYSTEM,
        priority=priority or Notification.Priority.NORMAL
    )
    if send_email and user.email:
        try:
            send_mail(
                subject=f"[RHziz] {title}",
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@peopleflow.local"),
                recipient_list=[user.email],
                fail_silently=True,
            )
            notif.email_sent = True
            notif.save(update_fields=["email_sent"])
        except Exception:
            pass
    return notif


def notify_employee(employee, title, message, category=None, priority=None):
    user = getattr(employee, "user", None)
    if user:
        notify_user(user, title, message, category=category, priority=priority)
    elif employee.email:
        try:
            send_mail(
                subject=f"[RHziz] {title}",
                message=message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@peopleflow.local"),
                recipient_list=[employee.email],
                fail_silently=True,
            )
        except Exception:
            pass


def notify_hr_team(title, message, **kwargs):
    for user in _hr_users():
        notify_user(user, title, message, **kwargs)


def send_welcome_email(user):
    """E-mail de bienvenue envoyé après l'inscription."""
    if not user.email:
        return False
    from django.template.loader import render_to_string
    from django.core.mail import EmailMultiAlternatives

    context = {
        "user": user,
        "first_name": user.first_name or user.username,
        "platform_name": "Plateforme de Ziz",
    }
    
    try:
        subject = render_to_string("registration/welcome_subject.txt", context).strip()
    except Exception:
        subject = f"Bienvenue sur RHziz, {context['first_name']} !"
        
    try:
        text_body = render_to_string("registration/welcome_email.txt", context)
    except Exception:
        text_body = f"Bonjour {context['first_name']},\n\nBienvenue sur RHziz !\nVotre compte a été créé avec succès."
        
    try:
        html_body = render_to_string("registration/welcome_email.html", context)
        has_html = True
    except Exception:
        html_body = ""
        has_html = False

    try:
        if has_html:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@peopleflow.local"),
                to=[user.email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)
        else:
            send_mail(
                subject=subject,
                message=text_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@peopleflow.local"),
                recipient_list=[user.email],
                fail_silently=False,
            )
        return True
    except Exception:
        try:
            send_mail(
                subject=subject,
                message=text_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@peopleflow.local"),
                recipient_list=[user.email],
                fail_silently=True,
            )
            return True
        except Exception:
            return False
