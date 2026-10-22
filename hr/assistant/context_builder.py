"""Construction du contexte live injecté dans le prompt IA."""

from __future__ import annotations

import re
from datetime import date, timedelta

from django.urls import reverse

from hr.models import (
    Announcement,
    Contract,
    Department,
    DocumentRequest,
    Employee,
    Evaluation,
    LeaveRequest,
    Notification,
    Payslip,
    TeamSchedule,
    Training,
    TrainingEnrollment,
)
from hr.services import build_user_context


def _extract_name_tokens(question: str) -> list[str]:
    skip = {
        "le", "la", "les", "de", "du", "des", "pour", "avec", "sur", "dans", "est", "a",
        "son", "sa", "ses", "mon", "ma", "mes", "quel", "quelle", "quels", "quelles",
        "combien", "nombre", "donne", "donner", "cherche", "trouve", "information",
        "coordonnee", "coordonnées", "telephone", "téléphone", "email", "mail",
        "conge", "congé", "departement", "département", "poste", "service",
        "type", "travail", "employe", "employé", "personnel", "collaborateur",
    }
    tokens = []
    for word in re.findall(r"[\wàâäéèêëïîôùûüç\-']+", question.lower()):
        if len(word) > 2 and word not in skip and word not in tokens:
            tokens.append(word)
    return tokens[:6]


def _format_employee(emp: Employee, *, include_contact: bool = True) -> str:
    lines = [
        f"• {emp.first_name} {emp.last_name} (matricule {emp.employee_id})",
        f"  Poste : {emp.position} | Département : {emp.department.name if emp.department else 'Non affecté'}",
    ]
    if include_contact:
        lines.append(f"  Email : {emp.email}")
        if emp.phone:
            lines.append(f"  Téléphone : {emp.phone}")
    if emp.hire_date:
        lines.append(f"  Embauche : {emp.hire_date:%d/%m/%Y}")
    lines.append(f"  Statut : {'Actif' if emp.active else 'Inactif'}")
    return "\n".join(lines)


def _employee_related_data(employees: list[Employee]) -> list[str]:
    blocks = []
    for emp in employees:
        block = [_format_employee(emp)]
        leaves = LeaveRequest.objects.filter(employee=emp).order_by("-created_at")[:5]
        if leaves:
            block.append("  Congés :")
            for lv in leaves:
                block.append(
                    f"    - {lv.get_leave_type_display()} : {lv.get_status_display()} "
                    f"({lv.start_date:%d/%m/%Y} → {lv.end_date:%d/%m/%Y}, {lv.days} j)"
                )
        payslips = Payslip.objects.filter(employee=emp).order_by("-year", "-month")[:2]
        if payslips:
            ps = payslips[0]
            block.append(f"  Dernière paie : {ps.month:02d}/{ps.year} — brut {ps.gross_salary} €, net {ps.net_salary} €")
        contracts = Contract.objects.filter(employee=emp).order_by("-start_date")[:3]
        if contracts:
            block.append("  Contrats :")
            for c in contracts:
                end = c.end_date.strftime("%d/%m/%Y") if c.end_date else "Indéterminé"
                block.append(
                    f"    - {c.get_contract_type_display()} ({c.get_status_display()}) : "
                    f"{c.start_date:%d/%m/%Y} → {end}"
                )
        docs = DocumentRequest.objects.filter(employee=emp).order_by("-created_at")[:3]
        if docs:
            block.append("  Documents demandés :")
            for doc in docs:
                block.append(f"    - {doc.get_doc_type_display()} : {doc.get_status_display()}")
        evals = Evaluation.objects.filter(employee=emp).order_by("-created_at")[:2]
        if evals:
            block.append("  Évaluations :")
            for ev in evals:
                block.append(f"    - {ev.period} : {ev.score}/20")
        today = date.today()
        schedules = TeamSchedule.objects.filter(
            employee=emp, work_date__gte=today, work_date__lte=today + timedelta(days=7)
        ).order_by("work_date")[:5]
        if schedules:
            block.append("  Planning (7 prochains jours) :")
            for sch in schedules:
                block.append(f"    - {sch.work_date:%d/%m/%Y} : {sch.get_shift_display()}")
        blocks.append("\n".join(block))
    return blocks


def _search_employees(question: str, limit: int = 5) -> list[Employee]:
    tokens = _extract_name_tokens(question)
    found: list[Employee] = []
    seen: set[int] = set()

    for token in tokens:
        for emp in Employee.objects.filter(first_name__icontains=token)[:limit]:
            if emp.pk not in seen:
                seen.add(emp.pk)
                found.append(emp)
        for emp in Employee.objects.filter(last_name__icontains=token)[:limit]:
            if emp.pk not in seen:
                seen.add(emp.pk)
                found.append(emp)
        if len(found) >= limit:
            break

    if not found and any(k in question.lower() for k in ("employé", "employe", "effectif", "personnel")):
        found = list(Employee.objects.filter(active=True).order_by("last_name")[:limit])
    return found[:limit]


def _build_hr_overview(ctx: dict) -> list[str]:
    sections = [
        "Vue RH globale :",
        f"• Effectif actif : {ctx.get('employees', 0)}",
        f"• Départements : {ctx.get('departments', 0)}",
        f"• Congés en attente : {ctx.get('pending', 0)}",
        f"• Documents en attente : {ctx.get('pending_docs', 0)}",
        f"• Accès à valider : {ctx.get('pending_access', 0)}",
    ]
    pending_leaves = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).select_related("employee")[:5]
    if pending_leaves:
        sections.append("Congés à traiter (échantillon) :")
        for lv in pending_leaves:
            sections.append(
                f"  - {lv.employee} : {lv.get_leave_type_display()} "
                f"({lv.start_date:%d/%m/%Y} → {lv.end_date:%d/%m/%Y})"
            )
    pending_docs = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).select_related("employee")[:5]
    if pending_docs:
        sections.append("Documents à traiter (échantillon) :")
        for doc in pending_docs:
            sections.append(f"  - {doc.employee} : {doc.get_doc_type_display()}")
    depts = Department.objects.all()[:10]
    if depts:
        sections.append("Départements :")
        for dept in depts:
            sections.append(f"  - {dept.name} ({dept.employees.filter(active=True).count()} actifs)")
    return sections


def build_live_data_context(question: str, user) -> str:
    """Agrège les données métier pertinentes selon le rôle."""
    ctx = build_user_context(user) if user and user.is_authenticated else {}
    sections: list[str] = []
    q = question.lower()

    if ctx.get("is_hr"):
        sections.extend(_build_hr_overview(ctx))
        pending_access = Employee.objects.filter(active=True, access_status=Employee.AccessStatus.PENDING).count()
        if any(k in q for k in ("accès", "acces", "access", "valider")):
            sections.append(f"Demandes d'accès à valider : {pending_access}")
        employees = _search_employees(question)
        if employees:
            sections.append("Employés correspondant à la question :\n" + "\n\n".join(_employee_related_data(employees)))
    elif ctx.get("employee"):
        emp = ctx["employee"]
        sections.append("=== DOSSIER EMPLOYÉ CONNECTÉ (seules données autorisées) ===")
        sections.append(_format_employee(emp))
        sections.extend(_employee_related_data([emp]))
        if emp.user_id:
            unread = Notification.objects.filter(user=emp.user, read=False).count()
            sections.append(f"Notifications non lues : {unread}")
        enrollments = TrainingEnrollment.objects.filter(employee=emp).select_related("training")[:3]
        if enrollments:
            sections.append("Formations inscrites :")
            for enr in enrollments:
                sections.append(f"  - {enr.training.title} ({enr.get_status_display()})")

    if any(k in q for k in ("annonce", "actualité", "communiqué", "information")):
        anns = Announcement.objects.filter(active=True).order_by("-created_at")[:5]
        if anns:
            sections.append(
                "Annonces actives :\n"
                + "\n".join(f"• {a.title} ({a.get_priority_display()})" for a in anns)
            )

    if any(k in q for k in ("formation", "training", "cours")):
        trainings = Training.objects.all().order_by("-start_date")[:5]
        if trainings:
            sections.append(
                "Formations :\n"
                + "\n".join(
                    f"• {t.title} ({t.start_date:%d/%m/%Y} → {t.end_date:%d/%m/%Y})"
                    for t in trainings
                )
            )

    if ctx.get("is_hr") and any(k in q for k in ("document", "attestation", "certificat")):
        pending = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).count()
        sections.append(f"Demandes de documents en attente : {pending}")

    return "\n\n".join(sections) if sections else "Aucune donnée live spécifique identifiée."


def build_user_context_summary(user) -> str:
    from hr.services import _context_summary

    ctx = build_user_context(user) if user and user.is_authenticated else {}
    return _context_summary(ctx) if ctx else "Utilisateur non authentifié."


def platform_urls() -> dict[str, str]:
    return {
        "leaves": reverse("leaves"),
        "documents": reverse("document_requests"),
        "profile": reverse("profile"),
        "employees": reverse("employees"),
    }
