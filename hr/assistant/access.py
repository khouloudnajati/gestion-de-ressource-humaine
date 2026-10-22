"""Contrôle d'accès et navigation pour l'assistant selon le rôle."""

from __future__ import annotations

import re

from django.urls import reverse

MENU_LABELS = {
    "dashboard": "Tableau de bord",
    "leaves": "Congés",
    "leave_create": "Congés → + Nouvelle demande",
    "document_requests": "Documents administratifs",
    "document_request_create": "Documents → Nouvelle demande",
    "profile": "Mon profil",
    "employees": "Employés",
    "employee_add": "Employés → Ajouter",
    "departments": "Départements",
    "hr_actions": "Centre d'actions RH",
    "announcements": "Annonces RH",
    "job_offers": "Offres d'emploi",
    "report": "Rapports RH",
    "documents": "Documents RH (corpus IA)",
    "contracts": "Contrats",
    "my_contracts": "Mes contrats",
    "trainings": "Formations",
    "evaluations": "Évaluations",
    "my_evaluations": "Mes évaluations",
    "planning": "Planning",
    "payslips": "Fiches de paie",
    "password_change": "Changer mon mot de passe",
    "password_reset": "Mot de passe oublié",
    "chatbot": "Assistant RH",
    "notifications": "Notifications",
}

EMPLOYEE_DENIED = (
    "En tant qu'employé, je ne peux consulter que vos propres informations "
    "(profil, congés, paie, contrats, documents, planning, formations, évaluations). "
    "Pour les données d'autres collaborateurs, contactez le service RH."
)


def menu_hint(url_name: str) -> str:
    return MENU_LABELS.get(url_name, url_name.replace("_", " ").title())


def page_path(url_name: str) -> str:
    try:
        return reverse(url_name)
    except Exception:
        return ""


def is_self_reference(question: str) -> bool:
    q = f" {question.lower()} "
    if any(p in q for p in ("donne moi", "donne-moi", "donne moi les", "donne-moi les")):
        return False
    markers = (
        " mon ", " ma ", " mes ",
        "mon profil", "mes cong", "ma paie", "mon salaire", "mon contrat",
        "mes document", "mon planning", "mes éval", "mes eval", "mon poste",
        "mon département", "mon departement", "mon email", "mon mail", "mon téléphone",
        " mes informations", " mon dossier",
    )
    return any(m in q for m in markers)


def guard_employee_access(ctx: dict, target_employee) -> str | None:
    if not target_employee:
        return None
    if ctx.get("is_hr"):
        return None
    own = ctx.get("employee")
    if own and target_employee.pk == own.pk:
        return None
    return EMPLOYEE_DENIED


def employee_access_denial(question: str, ctx: dict) -> str | None:
    """Bloque les questions employé sur les données d'autres personnes."""
    if ctx.get("is_hr") or not ctx.get("employee"):
        return None
    if is_self_reference(question):
        return None

    from hr.models import Employee

    own: Employee = ctx["employee"]
    q = question.lower()

    for emp in Employee.objects.filter(active=True).exclude(pk=own.pk):
        first = emp.first_name.lower().strip()
        last = emp.last_name.lower().strip()
        if len(first) >= 3 and first in q:
            return EMPLOYEE_DENIED
        if len(last) >= 3 and last in q:
            return EMPLOYEE_DENIED
        if len(first) >= 3 and len(last) >= 3 and first in q and last in q:
            return EMPLOYEE_DENIED

    skip = {
        "le", "la", "les", "de", "du", "des", "pour", "avec", "sur", "dans", "est",
        "quel", "quelle", "email", "mail", "telephone", "téléphone", "conge", "congé", "conges", "congés",
        "salaire", "paie", "contrat", "employe", "employé", "collaborateur", "donne", "donner", "moi",
    }
    tokens = [
        t for t in re.findall(r"[\wàâäéèêëïîôùûüç\-']+", q)
        if len(t) > 2 and t not in skip
    ]
    own_tokens = {own.first_name.lower(), own.last_name.lower()}
    if own.user_id:
        own_tokens.add(own.user.username.lower())

    for token in tokens[:6]:
        if token in own_tokens:
            continue
        if Employee.objects.filter(first_name__iexact=token).exclude(pk=own.pk).exists():
            return EMPLOYEE_DENIED
        if Employee.objects.filter(last_name__iexact=token).exclude(pk=own.pk).exists():
            return EMPLOYEE_DENIED
    return None
