import os
from pathlib import Path
from django.conf import settings
from django.urls import reverse
from .models import Department, Employee, LeaveRequest, RHDocument, DocumentRequest, Profile

def metrics():
    employees = Employee.objects.filter(active=True)
    leaves = LeaveRequest.objects.all()
    distribution = [{"name": d.name, "count": d.employees.filter(active=True).count()} for d in Department.objects.all()]
    return {
        "employees": employees.count(), "departments": Department.objects.count(),
        "pending": leaves.filter(status=LeaveRequest.Status.PENDING).count(),
        "approved": leaves.filter(status=LeaveRequest.Status.APPROVED).count(),
        "rejected": leaves.filter(status=LeaveRequest.Status.REJECTED).count(), "distribution": distribution,
    }

def _is_hr(user):
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)
    return user.is_superuser or role in {Profile.Role.HR, Profile.Role.ADMIN}

def build_user_context(user):
    """Contexte personnalisé injecté dans les réponses de l'assistant."""
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)
    is_hr = _is_hr(user)
    employee = getattr(user, "employee_profile", None)
    ctx = {
        "is_hr": is_hr,
        "is_admin": user.is_superuser or role == Profile.Role.ADMIN,
        "role": role,
        "employee": employee,
        "name": user.first_name or user.username,
    }
    if employee:
        leaves = LeaveRequest.objects.filter(employee=employee)
        docs = DocumentRequest.objects.filter(employee=employee)
        ctx["leaves_pending"] = leaves.filter(status=LeaveRequest.Status.PENDING).count()
        ctx["leaves_approved"] = leaves.filter(status=LeaveRequest.Status.APPROVED).count()
        ctx["leaves_total"] = leaves.count()
        ctx["docs_pending"] = docs.filter(status=DocumentRequest.Status.PENDING).count()
        ctx["docs_total"] = docs.count()
        last = leaves.first()
        if last:
            ctx["last_leave"] = f"{last.get_status_display()} du {last.start_date:%d/%m/%Y} au {last.end_date:%d/%m/%Y}"
    if is_hr:
        ctx.update(metrics())
        ctx["pending_docs"] = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).count()
        ctx["pending_access"] = Employee.objects.filter(
            active=True, access_status=Employee.AccessStatus.PENDING
        ).count()
    return ctx

def get_quick_links(user):
    """Liens directs vers les services de la plateforme."""
    links = [{"label": "Tableau de bord", "url": reverse("dashboard"), "icon": "🏠"}]
    if _is_hr(user):
        links += [
            {"label": "Centre d'actions", "url": reverse("hr_actions"), "icon": "⚡"},
            {"label": "Employés", "url": reverse("employees"), "icon": "👥"},
            {"label": "Départements", "url": reverse("departments"), "icon": "🏢"},
            {"label": "Gestion des congés", "url": reverse("leaves"), "icon": "📅"},
            {"label": "Demandes documents", "url": reverse("document_requests"), "icon": "📄"},
            {"label": "Annonces RH", "url": reverse("announcements"), "icon": "📢"},
            {"label": "Recrutement", "url": reverse("job_offers"), "icon": "💼"},
            {"label": "Rapports RH", "url": reverse("report"), "icon": "📊"},
            {"label": "Documents RH (corpus IA)", "url": reverse("documents"), "icon": "📁"},
            {"label": "Contrats", "url": reverse("contracts"), "icon": "📋"},
            {"label": "Formations", "url": reverse("trainings"), "icon": "🎓"},
            {"label": "Évaluations", "url": reverse("evaluations"), "icon": "⭐"},
            {"label": "Planning", "url": reverse("planning"), "icon": "🗓️"},
            {"label": "Fiches de paie", "url": reverse("payslips"), "icon": "💰"},
        ]
    else:
        links += [
            {"label": "Mon profil", "url": reverse("profile"), "icon": "👤"},
            {"label": "Mes contrats", "url": reverse("my_contracts"), "icon": "📋"},
            {"label": "Mes congés", "url": reverse("leaves"), "icon": "📅"},
            {"label": "Mes documents", "url": reverse("document_requests"), "icon": "📄"},
            {"label": "Mon mot de passe", "url": reverse("password_change"), "icon": "🔒"},
            {"label": "Offres d'emploi", "url": reverse("job_offers"), "icon": "💼"},
            {"label": "Mon planning", "url": reverse("planning"), "icon": "🗓️"},
            {"label": "Mes fiches de paie", "url": reverse("payslips"), "icon": "💰"},
            {"label": "Formations", "url": reverse("trainings"), "icon": "🎓"},
            {"label": "Mes évaluations", "url": reverse("my_evaluations"), "icon": "⭐"},
            {"label": "Notifications", "url": reverse("notifications"), "icon": "🔔"},
        ]
    return links

def get_suggestions(user):
    """Questions suggérées adaptées au rôle."""
    common = [
        {"label": "Services disponibles", "question": "Quels services sont disponibles sur PeopleFlow ?"},
        {"label": "Horaires", "question": "Quels sont les horaires de travail en production ?"},
        {"label": "Règlement", "question": "Quelle est la procédure pour demander un congé selon le règlement ?"},
    ]
    if _is_hr(user):
        return [
            {"label": "Congés en attente", "question": "Combien de demandes de congé sont en attente ?"},
            {"label": "Effectif", "question": "Quel est l'effectif actuel de l'entreprise ?"},
            {"label": "Documents en attente", "question": "Y a-t-il des demandes de documents en attente ?"},
            {"label": "Centre d'actions", "question": "Comment traiter toutes les demandes en attente ?"},
            {"label": "Annonces", "question": "Comment publier une annonce aux employés ?"},
            {"label": "Recrutement", "question": "Comment créer une offre d'emploi ?"},
            {"label": "Générer un rapport", "question": "Comment générer un rapport RH ?"},
        ] + common
    return [
        {"label": "Demander un congé", "question": "Comment déposer une demande de congé ?"},
        {"label": "Suivi congés", "question": "Quel est le statut de mes demandes de congé ?"},
        {"label": "Attestation", "question": "Comment obtenir une attestation de travail ?"},
        {"label": "Mon profil", "question": "Comment modifier mes informations personnelles ?"},
        {"label": "Mot de passe", "question": "Comment changer mon mot de passe ?"},
    ] + common

def _path(name):
    return reverse(name)


def _menu(name):
    from hr.assistant.access import menu_hint
    return menu_hint(name)


def _employee_leave_guide(ctx):
    from .models import LeaveRequest

    lines = [
        "Pour déposer une demande de congé :",
        "1. Cliquez sur « Congés » dans le menu principal",
        "2. Appuyez sur « + Nouvelle demande »",
        "3. Choisissez le type de congé (annuel, maladie, etc.)",
        "4. Indiquez les dates de début et de fin, puis le motif",
        "5. Validez — les RH seront notifiés et vous recevrez une réponse par notification",
        "",
        "Pour suivre vos demandes, restez sur la page « Congés » : vous y verrez le statut (en attente, accepté, refusé).",
    ]
    emp = ctx.get("employee")
    if emp:
        leaves = LeaveRequest.objects.filter(employee=emp).order_by("-created_at")[:5]
        if leaves:
            lines.append("")
            lines.append("Vos demandes récentes :")
            for lv in leaves:
                lines.append(
                    f"• {lv.get_leave_type_display()} — {lv.get_status_display()} "
                    f"({lv.start_date:%d/%m/%Y} au {lv.end_date:%d/%m/%Y}, {lv.days} jour(s))"
                )
        else:
            lines.append("")
            lines.append("Vous n'avez encore aucune demande de congé enregistrée.")
    return "\n".join(lines)


def _hr_leave_overview():
    from .models import LeaveRequest

    pending = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count()
    approved = LeaveRequest.objects.filter(status=LeaveRequest.Status.APPROVED).count()
    rejected = LeaveRequest.objects.filter(status=LeaveRequest.Status.REJECTED).count()
    lines = [
        f"Il y a {pending} demande(s) de congé en attente de validation.",
        f"Statistiques : {approved} acceptée(s), {rejected} refusée(s).",
        "",
        "Pour traiter les demandes :",
        "1. Ouvrez « Centre d'actions » ou « Congés »",
        "2. Consultez les demandes en attente",
        "3. Acceptez ou refusez avec un commentaire si nécessaire",
    ]
    sample = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).select_related("employee")[:3]
    if sample:
        lines.append("")
        lines.append("Exemples en attente :")
        for lv in sample:
            lines.append(
                f"• {lv.employee} — {lv.get_leave_type_display()} "
                f"({lv.start_date:%d/%m/%Y} → {lv.end_date:%d/%m/%Y})"
            )
    return "\n".join(lines)


def _format_own_employee(emp):
    lines = [
        f"Voici vos informations :",
        f"• Nom : {emp.first_name} {emp.last_name}",
        f"• Matricule : {emp.employee_id}",
        f"• Poste : {emp.position}",
        f"• Département : {emp.department.name if emp.department else 'Non affecté'}",
        f"• Email : {emp.email}",
    ]
    if emp.phone:
        lines.append(f"• Téléphone : {emp.phone}")
    if emp.hire_date:
        lines.append(f"• Date d'embauche : {emp.hire_date:%d/%m/%Y}")
    return "\n".join(lines)


def _normalize_question(question: str) -> str:
    import unicodedata

    q = unicodedata.normalize("NFD", (question or "").lower())
    q = "".join(c for c in q if unicodedata.category(c) != "Mn")
    q = q.replace("contra ", "contrat ").replace("contra?", "contrat?")
    if q.endswith("contra"):
        q = q[:-6] + "contrat"
    return q


def _find_employee_in_question(question: str):
    """Recherche flexible d'un employé dans la question (noms courts, répétés, partiels)."""
    import re

    from .models import Employee

    q = _normalize_question(question)
    skip = {
        "le", "la", "les", "de", "du", "des", "pour", "avec", "sur", "dans", "est", "a",
        "son", "sa", "ses", "mon", "ma", "mes", "ton", "ta", "tes", "quel", "quelle",
        "quels", "quelles", "combien", "nombre", "donne", "donner", "cherche", "trouve",
        "information", "coordonnee", "telephone", "email", "conge", "conges", "departement",
        "poste", "service", "type", "travail", "contrat", "contra", "cdi", "cdd", "valider",
        "demande", "demandes", "attente", "acces", "access",
    }
    tokens = [t for t in re.findall(r"[\w\-']+", q) if t not in skip]

    for i in range(len(tokens) - 1):
        first, last = tokens[i], tokens[i + 1]
        emp = Employee.objects.filter(first_name__iexact=first, last_name__iexact=last).first()
        if emp:
            return emp

    for token in tokens:
        if len(token) < 1:
            continue
        emp = Employee.objects.filter(first_name__iexact=token).first()
        if emp:
            return emp
        emp = Employee.objects.filter(last_name__iexact=token).first()
        if emp:
            return emp
        if len(token) >= 2:
            emp = Employee.objects.filter(first_name__icontains=token).first()
            if emp:
                return emp
            emp = Employee.objects.filter(last_name__icontains=token).first()
            if emp:
                return emp

    for i, token in enumerate(tokens):
        if len(token) >= 1 and i + 1 < len(tokens) and token == tokens[i + 1]:
            emp = Employee.objects.filter(first_name__iexact=token, last_name__iexact=token).first()
            if emp:
                return emp
    return None


def _format_employee_contracts(employee, *, question: str = "", own: bool = False):
    from .models import Contract

    contracts = Contract.objects.filter(employee=employee).order_by("-start_date")[:5]
    q = _normalize_question(question)
    name = f"{employee.first_name} {employee.last_name}"
    if not contracts:
        if own:
            return (
                "Aucun contrat de travail enregistré pour le moment.\n"
                "Consultez « Mes contrats » ou demandez une copie via « Documents administratifs »."
            )
        return (
            f"Aucun contrat de travail enregistré pour {name}.\n"
            f"Consultez « Mes contrats » ou demandez une copie via « Documents administratifs »."
        )
    if any(k in q for k in ("type", "quel", "quelle", "cdi", "cdd")) and len(contracts) >= 1:
        latest = contracts[0]
        end = latest.end_date.strftime("%d/%m/%Y") if latest.end_date else "Indéterminé"
        label = "Votre type de contrat" if own else f"Type de contrat de {name}"
        return (
            f"{label} : {latest.get_contract_type_display()} ({latest.get_status_display()})\n"
            f"Période : {latest.start_date:%d/%m/%Y} → {end}"
        )
    lines = [f"Vos contrats :" if own else f"Contrats de {name} :"]
    for contract in contracts:
        end = contract.end_date.strftime("%d/%m/%Y") if contract.end_date else "Indéterminé"
        lines.append(
            f"• {contract.get_contract_type_display()} — {contract.get_status_display()} "
            f"({contract.start_date:%d/%m/%Y} → {end})"
        )
    return "\n".join(lines)


def _answer_access_requests(ctx):
    from hr.assistant.access import menu_hint

    pending = Employee.objects.filter(active=True, access_status=Employee.AccessStatus.PENDING)
    count = pending.count()
    if count == 0:
        return "Il n'y a aucune demande d'accès en attente de validation."
    lines = [f"Il y a {count} demande(s) d'accès à valider."]
    sample = pending.select_related("department")[:5]
    if sample:
        lines.append("")
        lines.append("Liste :")
        for emp in sample:
            dept = emp.department.name if emp.department else "Non affecté"
            lines.append(f"• {emp.first_name} {emp.last_name} — {emp.email} ({dept})")
    lines.append("")
    lines.append(f"Traitez-les dans « {menu_hint('hr_actions')} » ou « {menu_hint('employees')} ».")
    return "\n".join(lines)


def _answer_employee_field_question(question: str, ctx: dict):
    """Répond aux questions ciblées sur un employé (date embauche, matricule, poste…)."""
    from hr.assistant.access import guard_employee_access, is_self_reference

    q = _normalize_question(question)
    employee = _find_employee_in_question(question)
    if not employee and ctx.get("employee") and is_self_reference(question):
        employee = ctx["employee"]
    if not employee:
        return None

    denied = guard_employee_access(ctx, employee)
    if denied:
        return denied

    name = f"{employee.first_name} {employee.last_name}"

    if "embauche" in q:
        if employee.hire_date:
            return f"Date d'embauche de {name} : {employee.hire_date:%d/%m/%Y}"
        return f"Aucune date d'embauche enregistrée pour {name}."

    if "matricule" in q:
        return f"Matricule de {name} : {employee.employee_id}"

    if "poste" in q:
        return f"Poste de {name} : {employee.position}"

    if "departement" in q or "department" in q:
        dept = employee.department.name if employee.department else "Non affecté"
        return f"Département de {name} : {dept}"

    if any(x in q for x in ("profil", "dossier", "informations", "fiche")):
        return _format_own_employee(employee).replace("Voici vos informations", f"Dossier de {name}")

    return None


def _answer_hr_combien(question: str, ctx: dict):
    q = _normalize_question(question)
    if any(x in q for x in ("acces", "access", "valider")) and any(
        x in q for x in ("demande", "demandes", "combien", "nombre")
    ):
        return _answer_access_requests(ctx)
    if any(x in q for x in ("conge", "conges", "absence")):
        return _hr_leave_overview()
    if any(x in q for x in ("document", "attestation", "certificat")):
        pending = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).count()
        return f"Il y a {pending} demande(s) de document en attente. Consultez « Documents administratifs » ou le Centre d'actions."
    if any(x in q for x in ("employe", "employes", "effectif", "collaborateur")):
        total = Employee.objects.filter(active=True).count()
        return f"L'effectif actif compte {total} collaborateur(s)."
    if "combien" in q or "nombre" in q:
        access = Employee.objects.filter(active=True, access_status=Employee.AccessStatus.PENDING).count()
        leaves = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count()
        docs = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).count()
        return (
            "Demandes en attente :\n"
            f"• Accès à valider : {access}\n"
            f"• Congés : {leaves}\n"
            f"• Documents : {docs}\n\n"
            "Précisez votre question (ex. « combien de demandes d'accès ? ») pour plus de détails."
        )
    return None


def _build_provider_prompt(question, ctx=None, doc_ctx=None, rag_result=None):
    ctx = ctx or {}
    sources_note = ""
    if rag_result and rag_result.get("sources"):
        sources_note = f"\nSources RAG identifiées : {', '.join(rag_result['sources'])}"
    return (
        "Tu es l'assistant RH de PeopleFlow, une plateforme d'entreprise laitière. Réponds en français, "
        "de façon courte, claire et factuelle. Base-toi PRIORITAIREMENT sur les extraits documentaires fournis "
        "(RAG) quand ils sont pertinents. Si l'information n'est pas dans les documents, utilise tes connaissances "
        "générales sur la gestion RH."
        f"\n\nContexte utilisateur :\n{_context_summary(ctx)}"
        f"\n\nExtraits documentaires (RAG) :\n{doc_ctx or 'Aucun extrait pertinent.'}{sources_note}"
        f"\n\nPages utiles : congés={_path('leaves')}, documents={_path('document_requests')}, profil={_path('profile')}"
        f"\n\nQuestion : {question}"
    )


def _call_llm_provider(question, ctx=None, doc_ctx=None, rag_result=None):
    """Appelle le routeur LLM partagé avec le contexte métier construit ici."""
    prompt = _build_provider_prompt(question, ctx=ctx, doc_ctx=doc_ctx, rag_result=rag_result)
    from .assistant.llm import call_llm

    return call_llm(prompt)


def local_chat_answer(question, ctx=None):
    from hr.assistant.access import guard_employee_access, is_self_reference, menu_hint

    from .models import Employee, Payslip, LeaveRequest, DocumentRequest, Training, Contract
    q = _normalize_question(question)
    ctx = ctx or {}
    words = q.split()

    if ctx.get("is_hr") and ("combien" in q or "nombre" in q):
        combien_answer = _answer_hr_combien(question, ctx)
        if combien_answer:
            return combien_answer

    if any(x in q for x in ("acces", "access")) or ("acces" in q and "valider" in q):
        if ctx.get("is_hr"):
            return _answer_access_requests(ctx)
        return "Seuls les responsables RH peuvent valider les demandes d'accès."

    if any(x in q for x in ("contrat", "contra", "cdi", "cdd")) or "contrat" in q:
        employee = _find_employee_in_question(question)
        if not employee and ctx.get("employee"):
            if is_self_reference(question) or not ctx.get("is_hr"):
                employee = ctx["employee"]
        if employee:
            denied = guard_employee_access(ctx, employee)
            if denied:
                return denied
            is_own = bool(ctx.get("employee") and employee.pk == ctx["employee"].pk)
            return _format_employee_contracts(employee, question=question, own=is_own)
        if ctx.get("is_hr"):
            return f"Gérez les contrats dans « {menu_hint('contracts')} ». Indiquez le nom de l'employé pour voir son type de contrat."
        if ctx.get("employee"):
            return _format_employee_contracts(ctx["employee"], question=question, own=True)
        return f"Consultez vos contrats dans « {menu_hint('my_contracts')} »."

    field_answer = _answer_employee_field_question(question, ctx)
    if field_answer:
        return field_answer
    
    # Fonction helper pour extraire le nom d'employé
    def extract_employee_name(question_words):
        skip_words = {"le", "la", "les", "de", "du", "des", "pour", "avec", "sur", "dans", "est", "a", "son", "sa", "ses", "mon", "ma", "mes", "ton", "ta", "tes", "quel", "quelle", "quels", "quelles", "combien", "nombre", "donne", "donner", "cherche", "trouve", "information", "coordonnee", "telephone", "email", "paiement", "salaire", "paie", "fiche", "bulletin", "conge", "congé", "departement", "département", "poste", "service", "type", "travail"}
        
        # Essayer de trouver un nom dans les mots de la question
        for i, word in enumerate(question_words):
            word_lower = word.lower()
            if word_lower not in skip_words and len(word) > 2:
                # Essayer avec 1, 2 ou 3 mots consécutifs
                for length in [1, 2, 3]:
                    if i + length <= len(question_words):
                        potential_name = " ".join(question_words[i:i+length])
                        # Chercher par prénom (insensible à la casse)
                        employee = Employee.objects.filter(
                            first_name__iexact=potential_name.split()[0]
                        ).first()
                        if not employee:
                            employee = Employee.objects.filter(
                                first_name__icontains=potential_name.split()[0]
                            ).first()
                        if employee:
                            return employee
                        # Chercher par nom complet
                        if len(potential_name.split()) > 1:
                            employee = Employee.objects.filter(
                                first_name__iexact=potential_name.split()[0]
                            ).filter(
                                last_name__iexact=potential_name.split()[-1]
                            ).first()
                            if not employee:
                                employee = Employee.objects.filter(
                                    first_name__icontains=potential_name.split()[0]
                                ).filter(
                                    last_name__icontains=potential_name.split()[-1]
                                ).first()
                            if employee:
                                return employee
        
        # Si aucun employé trouvé avec la méthode normale, essayer de trouver des mots répétés
        # (ex: "rachida rachida" -> chercher "rachida")
        seen_words = {}
        for i, word in enumerate(question_words):
            word_lower = word.lower()
            if word_lower not in skip_words and len(word) > 2:
                if word_lower in seen_words:
                    # Mot répété trouvé, essayer comme nom d'employé
                    employee = Employee.objects.filter(
                        first_name__iexact=word_lower
                    ).first()
                    if not employee:
                        employee = Employee.objects.filter(
                            first_name__icontains=word_lower
                        ).first()
                    if employee:
                        return employee
                else:
                    seen_words[word_lower] = i
        
        return None

    # 1. QUESTIONS SUR LES SERVICES ET LA PLATEFORME
    if any(x in q for x in ["service", "disponible", "aide", "menu", "fonctionnalité", "peopleflow", "plateforme", "peut faire", "quoi faire"]):
        if ctx.get("is_hr"):
            return (
                "En tant que responsable RH, vous gérez toute la plateforme PeopleFlow :\n"
                f"• {menu_hint('hr_actions')} — traiter congés et documents en attente\n"
                f"• {menu_hint('employees')} — dossiers, ajout, export CSV\n"
                f"• {menu_hint('departments')} — structure par services\n"
                f"• {menu_hint('leaves')} — validation des demandes de congé\n"
                f"• {menu_hint('document_requests')} — attestations et certificats\n"
                f"• {menu_hint('announcements')} — communication interne\n"
                f"• {menu_hint('job_offers')} — recrutement\n"
                f"• {menu_hint('report')} — rapports et indicateurs\n"
                f"• {menu_hint('documents')} — corpus documentaire IA\n"
                f"• {menu_hint('contracts')}, {menu_hint('trainings')}, {menu_hint('evaluations')}, "
                f"{menu_hint('planning')}, {menu_hint('payslips')}"
            )
        return (
            "Depuis votre espace employé, vous pouvez :\n"
            f"• {menu_hint('profile')} — coordonnées et photo\n"
            f"• {menu_hint('leaves')} — déposer (+ Nouvelle demande) et suivre vos congés\n"
            f"• {menu_hint('document_requests')} — demander attestations et certificats\n"
            f"• {menu_hint('my_contracts')} — consulter vos contrats\n"
            f"• {menu_hint('payslips')} — bulletins de salaire\n"
            f"• {menu_hint('planning')} — vos shifts\n"
            f"• {menu_hint('trainings')} — formations disponibles\n"
            f"• {menu_hint('my_evaluations')} — notes et retours RH\n"
            f"• {menu_hint('notifications')} — alertes congés, documents, paie\n"
            f"• {menu_hint('password_change')} — sécurité du compte"
        )

    # 2. QUESTIONS SUR LES EMPLOYÉS
    if any(x in q for x in ["employé", "employe", "personnel", "collaborateur", "effectif", "matricule", "travaille"]):
        if ctx.get("employee") and is_self_reference(q):
            return _format_own_employee(ctx["employee"])
        employee = extract_employee_name(words)
        if employee:
            denied = guard_employee_access(ctx, employee)
            if denied:
                return denied
            info = [
                f"Employé : {employee.first_name} {employee.last_name}",
                f"Matricule : {employee.employee_id}",
                f"Poste : {employee.position}",
                f"Département : {employee.department.name}",
                f"Email : {employee.email}",
            ]
            if employee.phone:
                info.append(f"Téléphone : {employee.phone}")
            if employee.hire_date:
                info.append(f"Date d'embauche : {employee.hire_date:%d/%m/%Y}")
            info.append(f"Statut : {'Actif' if employee.active else 'Inactif'}")
            return "\n".join(info) + f"\n\nPlus de détails dans « {menu_hint('employees')} »."
        
        if ctx.get("is_hr"):
            total = Employee.objects.filter(active=True).count()
            return (
                f"L'effectif actif compte {total} collaborateur(s). "
                f"Gérez les dossiers dans « {menu_hint('employees')} » ou ajoutez un employé via « {menu_hint('employee_add')} »."
            )
        if ctx.get("employee"):
            return _format_own_employee(ctx["employee"])
        return "Les informations sur les autres collaborateurs sont réservées au service RH."

    # 3. QUESTIONS SUR LES COORDONNÉES
    if any(x in q for x in ["coordonnée", "coordonnee", "téléphone", "telephone", "email", "e-mail", "mail", "courriel", "numero", "numéro", "contact", "appeler", "joindre"]):
        if ctx.get("employee") and (is_self_reference(q) or not extract_employee_name(words)):
            emp = ctx["employee"]
            contact = [f"• E-mail : {emp.email}"]
            if emp.phone:
                contact.append(f"• Téléphone : {emp.phone}")
            return (
                "Vos coordonnées :\n" + "\n".join(contact)
                + f"\n\nPour les modifier, ouvrez « {menu_hint('profile')} »."
            )
        employee = extract_employee_name(words)
        if employee:
            denied = guard_employee_access(ctx, employee)
            if denied:
                return denied
            contact = []
            if employee.phone:
                contact.append(f"• Téléphone : {employee.phone}")
            if employee.email:
                contact.append(f"• E-mail : {employee.email}")
            if contact:
                return f"Coordonnées de {employee.first_name} {employee.last_name} :\n" + "\n".join(contact)
            return f"Aucune coordonnée disponible pour {employee.first_name} {employee.last_name}."
        
        if ctx.get("is_hr"):
            return f"Les coordonnées des employés sont dans « {menu_hint('employees')} »."
        if ctx.get("employee"):
            emp = ctx["employee"]
            return f"Votre e-mail : {emp.email}" + (f" | Téléphone : {emp.phone}" if emp.phone else "")
        return "Les coordonnées des autres collaborateurs sont réservées au service RH."

    # 4. QUESTIONS SUR LES CONGÉS
    if any(x in q for x in ["congé", "conge", "absence", "vacance", "vacances", "repos"]):
        if ctx.get("employee") and is_self_reference(q):
            employee = ctx["employee"]
        else:
            employee = extract_employee_name(words)
        if employee:
            denied = guard_employee_access(ctx, employee)
            if denied:
                return denied
            leaves = LeaveRequest.objects.filter(employee=employee).order_by("-created_at")[:5]
            if leaves:
                status_text = "\n".join([
                    f"• {l.get_leave_type_display()} : {l.get_status_display()} "
                    f"({l.start_date:%d/%m/%Y} - {l.end_date:%d/%m/%Y}, {l.days} jour(s))"
                    for l in leaves
                ])
                prefix = "Vos congés" if ctx.get("employee") and employee.pk == ctx["employee"].pk else f"Congés de {employee.first_name} {employee.last_name}"
                return f"{prefix} :\n{status_text}"
            if ctx.get("employee") and employee.pk == ctx["employee"].pk:
                return _employee_leave_guide(ctx)
            return f"Aucun congé enregistré pour {employee.first_name} {employee.last_name}."
        
        if "combien" in q or "nombre" in q or "statut" in q or "suivi" in q:
            if ctx.get("is_hr"):
                return _hr_leave_overview()
            elif ctx.get("employee"):
                employee_obj = ctx.get("employee")
                if employee_obj:
                    leaves = LeaveRequest.objects.filter(employee=employee_obj)
                    pending = leaves.filter(status=LeaveRequest.Status.PENDING).count()
                    approved = leaves.filter(status=LeaveRequest.Status.APPROVED).count()
                    rejected = leaves.filter(status=LeaveRequest.Status.REJECTED).count()
                    lines = [
                        f"Vos congés : {leaves.count()} demande(s) au total.",
                        f"• {pending} en attente",
                        f"• {approved} acceptée(s)",
                        f"• {rejected} refusée(s)",
                    ]
                    recent = leaves.order_by("-created_at")[:3]
                    if recent:
                        lines.append("")
                        lines.append("Dernières demandes :")
                        for lv in recent:
                            lines.append(
                                f"• {lv.get_leave_type_display()} — {lv.get_status_display()} "
                                f"({lv.start_date:%d/%m/%Y} au {lv.end_date:%d/%m/%Y})"
                            )
                    return "\n".join(lines)
        
        if any(x in q for x in ["demander", "déposer", "deposer", "comment", "nouvelle", "poser", "créer", "creer"]):
            if ctx.get("is_hr"):
                return _hr_leave_overview()
            return _employee_leave_guide(ctx)
        if "demande" in q and not any(x in q for x in ("acces", "access")):
            if ctx.get("is_hr"):
                return _hr_leave_overview()
            return _employee_leave_guide(ctx)
        
        if ctx.get("is_hr"):
            return _hr_leave_overview()
        return _employee_leave_guide(ctx)

    # 5. QUESTIONS SUR LES PAIEMENTS/SALAIRES
    if any(x in q for x in ["paiement", "salaire", "paie", "fiche", "bulletin", "revenu", "paye"]):
        if ctx.get("employee") and (is_self_reference(q) or not extract_employee_name(words)):
            employee = ctx["employee"]
        else:
            employee = extract_employee_name(words)
        if employee:
            denied = guard_employee_access(ctx, employee)
            if denied:
                return denied
            payslips = Payslip.objects.filter(employee=employee).order_by("-year", "-month")[:3]
            if payslips:
                latest = payslips[0]
                label = "Votre dernière fiche de paie" if ctx.get("employee") and employee.pk == ctx["employee"].pk else f"Fiche de paie de {employee.first_name} {employee.last_name}"
                return (
                    f"{label} :\n"
                    f"• Période : {latest.month:02d}/{latest.year}\n"
                    f"• Salaire net : {latest.net_salary} €\n"
                    f"• Salaire brut : {latest.gross_salary} €"
                )
            return f"Aucune fiche de paie disponible pour {employee.first_name} {employee.last_name}."
        
        if ctx.get("is_hr"):
            return f"Gérez les fiches de paie dans « {menu_hint('payslips')} »."
        return f"Consultez vos fiches de paie dans « {menu_hint('payslips')} »."

    # 6. QUESTIONS SUR LES CONTRATS — traitées en tête de fonction (section contrat/contra)

    # 7. QUESTIONS SUR LES DOCUMENTS
    if any(x in q for x in ["document", "attestation", "certificat", "papier", "administratif"]):
        if ctx.get("is_hr"):
            pending = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).count()
            return f"{pending} demande(s) de document en attente. Traitez-les sur {_path('document_requests')}."
        return f"Pour demander un document : {_path('document_request_create')}. Suivez vos demandes sur {_path('document_requests')}"

    # 8. QUESTIONS SUR LES DÉPARTEMENTS
    if any(x in q for x in ["département", "departement", "service", "équipe", "equipe", "direction"]):
        # Chercher d'abord si un employé spécifique est mentionné
        skip_words = {"type", "travail", "de", "du", "des", "pour", "avec", "sur", "dans", "est", "a", "son", "sa", "ses", "mon", "ma", "mes", "ton", "ta", "tes"}
        potential_names = [w for w in words if len(w) > 2 and w.lower() not in skip_words]
        
        employee = None
        for name in potential_names:
            employee = Employee.objects.filter(first_name__iexact=name.lower()).first()
            if employee:
                break
            employee = Employee.objects.filter(first_name__icontains=name.lower()).first()
            if employee:
                break
            employee = Employee.objects.filter(last_name__iexact=name.lower()).first()
            if employee:
                break
            employee = Employee.objects.filter(last_name__icontains=name.lower()).first()
            if employee:
                break
        
        if employee and employee.department:
            return f"{employee.first_name} {employee.last_name} travaille dans le département : {employee.department.name}"
        elif employee:
            return f"{employee.first_name} {employee.last_name} n'est affecté à aucun département."
        
        # Si aucun employé spécifique, lister tous les départements
        from .models import Department
        depts = Department.objects.all()
        if depts:
            dept_list = "\n".join([f"• {d.name} : {d.manager or 'Pas de responsable'}" for d in depts])
            return f"Départements de l'entreprise :\n{dept_list}\n\nGérez-les sur {_path('departments')}"
        return f"Aucun département créé. Créez-en sur {_path('departments')}"

    # 8. QUESTIONS SUR LES FORMATIONS
    if any(x in q for x in ["formation", "training", "cours", "stage", "apprentissage"]):
        from .models import Training
        trainings = Training.objects.all()[:5]
        if trainings:
            training_list = "\n".join([f"• {t.title} ({t.start_date:%d/%m/%Y} - {t.end_date:%d/%m/%Y})" for t in trainings])
            return f"Formations disponibles :\n{training_list}\n\nInscrivez-vous sur {_path('trainings')}"
        return f"Aucune formation prévue. Consultez {_path('trainings')}"

    # 9. RECRUTEMENT (uniquement si pas une question sur un employé existant)
    if not _find_employee_in_question(question) and not is_self_reference(question):
        if any(x in q for x in ["recrutement", "offre d'emploi", "offre d emploi", "offre"]):
            if ctx.get("is_hr"):
                return f"Publiez et suivez les offres dans « {menu_hint('job_offers')} »."
            return f"Consultez les offres internes dans « {menu_hint('job_offers')} »."
        if "embauche" in q and "date" not in q:
            if ctx.get("is_hr"):
                return f"Publiez et suivez les offres dans « {menu_hint('job_offers')} »."
            return f"Consultez les offres internes dans « {menu_hint('job_offers')} »."

    # 10. QUESTIONS SUR LE PLANNING
    if any(x in q for x in ["planning", "shift", "equipe", "équipe", "tour", "mon planning", "mes shifts"]):
        if ctx.get("is_hr"):
            return f"Organisez le planning des équipes dans « {menu_hint('planning')} »."
        return f"Consultez votre planning dans « {menu_hint('planning')} »."

    # 11. QUESTIONS SUR LES ANNONCES
    if any(x in q for x in ["annonce", "information", "nouvelle", "communiqué", "actualité"]):
        from .models import Announcement
        announcements = Announcement.objects.filter(active=True)[:3]
        if announcements:
            ann_list = "\n".join([f"• {a.title} ({a.get_priority_display()})" for a in announcements])
            return f"Annonces récentes :\n{ann_list}\n\nToutes les annonces : {_path('announcements')}"
        return f"Aucune annonce active. Consultez {_path('announcements')}"

    # 12. QUESTIONS SUR LE PROFIL
    if any(x in q for x in ["profil", "photo", "modifier", "changer", "mettre à jour", "personal"]):
        return f"Modifiez votre profil sur {_path('profile')}. Vous pouvez changer vos informations personnelles et votre photo."

    # 13. QUESTIONS SUR LE MOT DE PASSE
    if any(x in q for x in ["mot de passe", "password", "sécurité", "securite", "connexion", "oublié"]):
        return f"Changez votre mot de passe : {_path('password_change')}. Mot de passe oublié ? Utilisez {_path('password_reset')}"

    # 14. QUESTIONS SUR LES RAPPORTS
    if any(x in q for x in ["rapport", "indicateur", "statistique", "analyse", "bilan", "synthèse"]):
        if ctx.get("is_hr"):
            return f"Générez un rapport RH sur {_path('report')}. Export PDF disponible : {_path('report_pdf')}"
        return f"Les rapports sont accessibles aux responsables RH."

    # 15. SALUATIONS
    if any(x in q for x in ["bonjour", "salut", "hello", "bonsoir", "coucou"]):
        name = ctx.get("name", "")
        greeting = f"Bonjour {name} ! " if name else "Bonjour ! "
        if ctx.get("is_hr"):
            return (
                greeting
                + "Je suis SmartZIZ, votre assistant RH. Je peux vous aider sur toute la plateforme : "
                "employés, congés, documents, paie, formations, rapports, recrutement et procédures internes. "
                "Que souhaitez-vous faire ?"
            )
        return (
            greeting
            + "Je suis SmartZIZ, votre assistant RH. Je peux répondre sur votre profil, vos congés, "
            "vos documents, votre paie, vos contrats, votre planning et les procédures RH. "
            "Que souhaitez-vous faire ?"
        )

    # 16. REMERCIEMENTS
    if any(x in q for x in ["merci", "thanks", "d'accord", "ok", "parfait"]):
        return "Je suis ravi de vous aider ! N'hésitez pas si vous avez d'autres questions."

    # Réponse par défaut — laisser le moteur IA / RAG traiter la question
    return None

def document_context(question):
    """Recherche RAG vectorielle puis repli lexical."""
    from .rag import rag_search
    rag = rag_search(question)
    if rag.get("text"):
        return rag["text"]
    words = {word for word in question.lower().split() if len(word) > 3}
    if not words:
        return ""
    sources = list(RHDocument.objects.filter(active=True).values_list("file", flat=True))
    docs_dir = Path(settings.RH_DOCUMENTS_DIR)
    if docs_dir.exists():
        sources += [str(path) for path in docs_dir.glob("*") if path.is_file()]
    matches = []
    for source in sources:
        try:
            path = Path(source)
            if not path.is_absolute():
                path = Path(settings.MEDIA_ROOT) / path
            if not path.exists():
                continue
            if path.suffix.lower() == ".pdf":
                from pypdf import PdfReader
                content = " ".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            else:
                content = path.read_text(encoding="utf-8", errors="ignore")
            for chunk in [content[i:i + 900] for i in range(0, len(content), 750)]:
                score = sum(word in chunk.lower() for word in words)
                if score:
                    matches.append((score, chunk))
        except Exception:
            continue
    return "\n\n".join(chunk for _, chunk in sorted(matches, reverse=True)[:3])

def _context_summary(ctx):
    lines = [f"Utilisateur : {ctx.get('name', 'inconnu')}"]
    if ctx.get("is_hr"):
        lines.append("Rôle : responsable RH — accès complet plateforme et tous les employés")
        lines.append(
            f"Effectif : {ctx.get('employees', 0)} | Congés en attente : {ctx.get('pending', 0)} | "
            f"Documents en attente : {ctx.get('pending_docs', 0)} | Accès à valider : {ctx.get('pending_access', 0)}"
        )
    else:
        lines.append("Rôle : employé — accès UNIQUEMENT à son propre dossier")
    emp = ctx.get("employee")
    if emp:
        lines.append(f"Dossier : {emp.first_name} {emp.last_name} ({emp.employee_id}) — {emp.position}")
        lines.append(f"Congés : {ctx.get('leaves_total', 0)} total, {ctx.get('leaves_pending', 0)} en attente")
        lines.append(f"Documents : {ctx.get('docs_total', 0)} total, {ctx.get('docs_pending', 0)} en attente")
        if ctx.get("last_leave"):
            lines.append(f"Dernière demande : {ctx.get('last_leave')}")
    return "\n".join(lines)

def ai_answer(question, user=None):
    ctx = build_user_context(user) if user and user.is_authenticated else {}
    local = local_chat_answer(question, ctx)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    from .rag import rag_search, rag_answer_from_chunks
    rag = rag_search(question)
    doc_ctx = rag["text"] or document_context(question)
    q = question.lower()
    
    # Intentions qui doivent TOUJOURS utiliser les données locales (employés spécifiques et données RH)
    # Ces mots-clés indiquent une recherche de données spécifiques dans la base de données
    data_query_intents = ["employé", "employe", "personnel", "collaborateur", "effectif", 
                          "coordonnée", "coordonnee", "téléphone", "telephone", "email", "mail", "courriel", "numero",
                          "paiement", "salaire", "paie", "fiche", "bulletin", "contrat", "cdi", "cdd",
                          "congé", "conge", "absence", "document", "attestation", "certificat"]
    
    # Si la question concerne une recherche de données RH, utiliser uniquement les données locales
    if any(x in q for x in data_query_intents):
        return local
    
    # Intentions plus précises pour déclencher le RAG (uniquement pour les politiques/règlements)
    policy_intents = ["horaire", "heure", "travail", "règlement", "reglement", "politique", "procédure",
                      "procedure", "haccp", "hygiène", "hygiene", "sécurité", "securite", "epi", "qualité", "qualite",
                      "règle", "regle"]
    is_policy_question = any(x in q for x in policy_intents)

    # Si le RAG a du contenu et que la question est de type politique, privilégier la réponse du fournisseur.
    if rag.get("text") and rag.get("chunks", 0) > 0 and is_policy_question:
        rag_local = rag_answer_from_chunks(question, rag)
        provider_text = _call_llm_provider(question, ctx=ctx, doc_ctx=doc_ctx, rag_result=rag)
        if provider_text:
            return provider_text + f"\n\n📎 Sources (RAG) : {', '.join(rag['sources'][:3])}"
        if rag_local:
            return rag_local
    
    # Vérifier si la réponse locale contient des informations spécifiques (pas un message générique)
    generic_indicators = ["je peux vous aider", "posez une question précise", "cliquez sur une suggestion"]
    is_generic = any(x in local.lower() for x in generic_indicators) if local else False
    
    # Si la réponse locale n'est pas générique, l'utiliser directement
    if local and not is_generic:
        return local
    
    # Intentions de navigation qui ne nécessitent PAS le RAG
    nav_intents = ["service", "disponible", "aide", "menu", "fonctionnalité", "peopleflow", "plateforme",
                   "profil", "mot de passe", "rapport", "département", "statut", "combien", "bonjour", "salut", "merci", "hello"]
    
    # Si c'est une question de navigation, utiliser la réponse locale
    if any(x in q for x in nav_intents):
        return local
    
    
    # Fournisseur LLM (Gemini/OpenAI) si une clé est disponible et que le contenu RAG est pertinent
    if rag.get("text") and rag.get("chunks", 0) > 0:
        provider_text = _call_llm_provider(question, ctx=ctx, doc_ctx=doc_ctx, rag_result=rag)
        if provider_text:
            if rag.get("sources"):
                provider_text += f"\n\n📎 Sources (RAG) : {', '.join(rag['sources'][:3])}"
            return provider_text
    
    # Fallback : réponse locale
    return local

def report_summary(data):
    parts = []
    parts.append(f"Effectif total : {data['employees']} collaborateur(s) actif(s)")
    parts.append(f"Structure : {data['departments']} département(s)")
    
    # Statistiques des congés
    total_leaves = data['pending'] + data['approved'] + data['rejected']
    if total_leaves > 0:
        approval_rate = (data['approved'] / total_leaves * 100) if total_leaves > 0 else 0
        parts.append(f"Congés : {data['pending']} en attente, {data['approved']} acceptés ({approval_rate:.1f}%), {data['rejected']} refusés")
    
    # Répartition par département
    if data["distribution"]:
        dept_info = ", ".join([f"{d['name']} ({d['count']})" for d in data["distribution"][:3]])
        if len(data["distribution"]) > 3:
            dept_info += f" et {len(data['distribution']) - 3} autres"
        parts.append(f"Répartition : {dept_info}")
        
        leading = max(data["distribution"], key=lambda d: d["count"])
        parts.append(f"Département le plus important : {leading['name']} ({leading['count']} employés)")
    
    return ". ".join(parts) + "."

def report_recommendations(data):
    notes = []
    
    # Recommandations sur les congés
    total_leaves = data['pending'] + data['approved'] + data['rejected']
    if total_leaves > 0:
        approval_rate = (data['approved'] / total_leaves * 100) if total_leaves > 0 else 0
        if data["pending"] > 5:
            notes.append(f"Traiter rapidement les {data['pending']} demandes de congé en attente pour éviter les retards.")
        if approval_rate < 70:
            notes.append("Analyser le taux de refus des congés et vérifier l'équilibre travail-vie des employés.")
        elif approval_rate > 95:
            notes.append("Le taux d'acceptation des congés est excellent. Maintenir cette politique flexible.")
    
    # Recommandations sur l'organisation
    if data["employees"] < 5:
        notes.append("L'effectif est réduit. Envisager un recrutement pour assurer la continuité des activités.")
    elif data["employees"] > 50:
        notes.append("Effectif important. Renforcer la communication interne et les procédures RH.")
    
    # Recommandations sur les départements
    if not data["departments"]:
        notes.append("Créer les départements de l'entreprise pour structurer l'organisation.")
    elif len(data["distribution"]) > 1:
        variance = max(d["count"] for d in data["distribution"]) - min(d["count"] for d in data["distribution"])
        if variance > 10:
            notes.append("Rééquilibrer la charge de travail entre les départements pour une meilleure organisation.")
    
    # Recommandations générales
    if not notes:
        notes.append("Maintenir le suivi régulier des effectifs et des demandes de congé par département.")
        notes.append("Continuer à optimiser les processus RH pour améliorer l'efficacité opérationnelle.")
    
    return " ".join(notes)
