"""Vues complémentaires : paie, planning, formations, contrats, évaluations, admin."""
from datetime import date, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .audit import log_action
from .forms import ContractForm, TrainingForm, EvaluationForm, TeamScheduleForm, PayslipForm, UserRoleForm
from .models import (
    Contract, Training, TrainingEnrollment, Evaluation, TeamSchedule, Payslip,
    Notification, AuditLog, Profile, Employee, Department, LeaveRequest,
    DocumentRequest, EmployeeSkill, TrainingRecommendation,
)
from .notifications import notify_employee, notify_user
from .views import role_required, is_hr


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def contracts(request):
    return render(request, "hr/contracts.html", {"contracts": Contract.objects.select_related("employee")})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def contract_form(request, pk=None):
    instance = get_object_or_404(Contract, pk=pk) if pk else None
    form = ContractForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_action(request.user, "Contrat enregistré", str(form.instance))
        messages.success(request, "Contrat enregistré.")
        next_url = request.GET.get("next") or request.POST.get("next")
        if next_url == "hr_actions":
            return redirect("hr_actions")
        return redirect("contracts")
    return render(request, "hr/form.html", {"form": form, "title": "Modifier le contrat" if pk else "Nouveau contrat"})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def contract_delete(request, pk):
    get_object_or_404(Contract, pk=pk).delete()
    messages.success(request, "Contrat supprimé.")
    return redirect("contracts")


@login_required
def trainings(request):
    can_manage = is_hr(request.user)
    employee = getattr(request.user, "employee_profile", None)
    qs = Training.objects.select_related("department")
    enrollments = TrainingEnrollment.objects.filter(employee=employee).values_list("training_id", flat=True) if employee else []
    return render(request, "hr/trainings.html", {
        "trainings": qs, "can_manage": can_manage, "employee": employee,
        "enrolled_ids": list(enrollments),
    })

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def training_form(request, pk=None):
    instance = get_object_or_404(Training, pk=pk) if pk else None
    form = TrainingForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Formation enregistrée.")
        return redirect("trainings")
    return render(request, "hr/form.html", {"form": form, "title": "Modifier la formation" if pk else "Nouvelle formation"})

@login_required
@require_POST
def training_enroll(request, pk):
    training = get_object_or_404(Training, pk=pk)
    employee = getattr(request.user, "employee_profile", None)
    if not employee:
        messages.error(request, "Profil employé requis.")
        return redirect("trainings")
    if training.enrollments.count() >= training.max_participants:
        messages.error(request, "Formation complète.")
        return redirect("trainings")
    TrainingEnrollment.objects.get_or_create(training=training, employee=employee)
    notify_user(request.user, "Inscription formation", f"Vous êtes inscrit(e) à : {training.title}")
    messages.success(request, "Inscription confirmée.")
    return redirect("trainings")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def evaluations(request):
    return render(request, "hr/evaluations.html", {"evaluations": Evaluation.objects.select_related("employee")})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def evaluation_form(request, pk=None):
    instance = get_object_or_404(Evaluation, pk=pk) if pk else None
    form = EvaluationForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        ev = form.save(commit=False)
        if not instance:
            ev.evaluator = request.user
        ev.save()
        notify_employee(ev.employee, "Nouvelle évaluation", f"Votre évaluation {ev.period} est disponible (note : {ev.score}/20).")
        log_action(request.user, "Évaluation créée", f"{ev.employee} – {ev.period}")
        messages.success(request, "Évaluation enregistrée.")
        return redirect("evaluations")
    return render(request, "hr/form.html", {"form": form, "title": "Modifier l'évaluation" if pk else "Nouvelle évaluation"})

@login_required
def my_evaluations(request):
    employee = getattr(request.user, "employee_profile", None)
    qs = Evaluation.objects.filter(employee=employee) if employee else Evaluation.objects.none()
    return render(request, "hr/my_evaluations.html", {"evaluations": qs, "employee": employee})


@login_required
def planning(request):
    can_manage = is_hr(request.user)
    start_str = request.GET.get("start_date")
    if start_str:
        try:
            week_start = date.fromisoformat(start_str)
        except ValueError:
            week_start = date.today() - timedelta(days=date.today().weekday())
    else:
        week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    employee = getattr(request.user, "employee_profile", None)
    qs = TeamSchedule.objects.select_related("employee").filter(work_date__gte=week_start, work_date__lte=week_end)
    
    if not can_manage:
        qs = qs.filter(employee=employee) if employee else qs.none()
    else:
        emp_filter = request.GET.get("employee")
        dept_filter = request.GET.get("department")
        if emp_filter:
            qs = qs.filter(employee_id=emp_filter)
        if dept_filter:
            qs = qs.filter(employee__department_id=dept_filter)

    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    
    context = {
        "schedules": qs,
        "can_manage": can_manage,
        "week_start": week_start,
        "week_end": week_end,
        "prev_week": prev_week,
        "next_week": next_week,
        "current_employee": request.GET.get("employee", ""),
        "current_department": request.GET.get("department", ""),
    }
    
    if can_manage:
        context["all_employees"] = Employee.objects.filter(active=True)
        context["departments"] = Department.objects.all()
        
    return render(request, "hr/planning.html", context)

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def planning_form(request, pk=None):
    instance = get_object_or_404(TeamSchedule, pk=pk) if pk else None
    form = TeamScheduleForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        sched = form.save()
        notify_employee(sched.employee, "Planning mis à jour", f"Shift du {sched.work_date:%d/%m/%Y} : {sched.get_shift_display()}")
        messages.success(request, "Planning enregistré.")
        return redirect("planning")
    return render(request, "hr/form.html", {"form": form, "title": "Modifier le planning" if pk else "Ajouter au planning"})


@login_required
def payslips(request):
    can_manage = is_hr(request.user)
    employee = getattr(request.user, "employee_profile", None)
    qs = Payslip.objects.select_related("employee")
    
    if not can_manage:
        qs = qs.filter(employee=employee) if employee else qs.none()
    else:
        emp_filter = request.GET.get("employee")
        if emp_filter:
            qs = qs.filter(employee_id=emp_filter)

    year_filter = request.GET.get("year")
    month_filter = request.GET.get("month")
    if year_filter:
        qs = qs.filter(year=year_filter)
    if month_filter:
        qs = qs.filter(month=month_filter)
        
    context = {
        "payslips": qs,
        "can_manage": can_manage,
        "current_year": year_filter or "",
        "current_month": month_filter or "",
        "current_employee": request.GET.get("employee", ""),
        "years": range(2024, date.today().year + 2),
        "months": range(1, 13),
    }
    
    if can_manage:
        context["all_employees"] = Employee.objects.filter(active=True)
        
    return render(request, "hr/payslips.html", context)

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def payslip_form(request, pk=None):
    instance = get_object_or_404(Payslip, pk=pk) if pk else None
    form = PayslipForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        ps = form.save()
        notify_employee(ps.employee, "Fiche de paie disponible", f"Votre bulletin {ps.month:02d}/{ps.year} est disponible.")
        log_action(request.user, "Fiche de paie publiée", f"{ps.employee} – {ps.month}/{ps.year}")
        messages.success(request, "Fiche de paie publiée.")
        return redirect("payslips")
    return render(request, "hr/form.html", {"form": form, "title": "Modifier la fiche de paie" if pk else "Nouvelle fiche de paie"})


@login_required
def notifications_list(request):
    qs = Notification.objects.filter(user=request.user)
    return render(request, "hr/notifications.html", {"notifications": qs, "unread": qs.filter(read=False).count()})

@login_required
@require_POST
def notification_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.read = True
    notif.save(update_fields=["read"])
    return redirect("notifications")


@role_required(Profile.Role.ADMIN)
def admin_dashboard(request):
    users = User.objects.select_related("profile").order_by("username")[:8]
    recent_logs = AuditLog.objects.select_related("user").order_by("-created_at")[:8]
    return render(request, "hr/admin_dashboard.html", {
        "users": users,
        "recent_logs": recent_logs,
        "employee_count": Employee.objects.count(),
        "department_count": Department.objects.count(),
        "pending_leaves": LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).count(),
        "pending_documents": DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).count(),
    })


@role_required(Profile.Role.ADMIN)
def user_management(request):
    users = User.objects.select_related("profile").order_by("username")
    target = None
    form = None

    if request.method == "POST" and request.POST.get("create-username"):
        username = request.POST.get("create-username", "").strip()
        email = request.POST.get("create-email", "").strip()
        first_name = request.POST.get("create-first_name", "").strip()
        last_name = request.POST.get("create-last_name", "").strip()
        password = request.POST.get("create-password", "")
        role = request.POST.get("create-role")

        if not username or not email or not password:
            messages.error(request, "Le nom d’utilisateur, l’e-mail et le mot de passe sont obligatoires.")
        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Ce nom d’utilisateur existe déjà.")
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            Profile.objects.create(user=user, role=role or Profile.Role.EMPLOYEE)
            log_action(request.user, "Utilisateur créé", f"{username} ({role or Profile.Role.EMPLOYEE})")
            messages.success(request, f"L’utilisateur {username} a été créé avec succès.")
            return redirect("user_management")

    if request.method == "POST" and request.POST.get("delete-user"):
        delete_id = request.POST.get("delete-user")
        if delete_id and delete_id != str(request.user.pk):
            user_to_delete = get_object_or_404(User, pk=delete_id)
            if user_to_delete.is_superuser:
                messages.error(request, "Impossible de supprimer un superutilisateur.")
            else:
                username = user_to_delete.username
                user_to_delete.delete()
                log_action(request.user, "Utilisateur supprimé", username)
                messages.success(request, f"L’utilisateur {username} a été supprimé.")
                return redirect("user_management")
        else:
            messages.error(request, "Vous ne pouvez pas supprimer votre propre compte depuis cette page.")

    if request.GET.get("user"):
        target = get_object_or_404(User, pk=request.GET["user"])
        form = UserRoleForm(request.POST or None, initial={"role": getattr(getattr(target, "profile", None), "role", Profile.Role.EMPLOYEE)})
        if request.method == "POST" and form.is_valid():
            profile, _ = Profile.objects.get_or_create(user=target, defaults={"role": form.cleaned_data["role"]})
            profile.role = form.cleaned_data["role"]
            profile.save()
            log_action(request.user, "Rôle modifié", f"{target.username} → {profile.role}")
            messages.success(request, f"Rôle de {target.username} mis à jour.")
            return redirect("user_management")
    return render(request, "hr/users.html", {"users": users, "target": target, "form": form})


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def audit_logs(request):
    return render(request, "hr/audit_logs.html", {"logs": AuditLog.objects.select_related("user")[:100]})


@login_required
def my_contracts(request):
    employee = getattr(request.user, "employee_profile", None)
    if not employee:
        messages.error(request, "Votre compte n'est pas associé à un profil employé.")
        return redirect("dashboard")
    contracts_qs = Contract.objects.filter(employee=employee).order_by("-start_date")
    return render(request, "hr/my_contracts.html", {"contracts": contracts_qs, "employee": employee})


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def training_delete(request, pk):
    training = get_object_or_404(Training, pk=pk)
    title = training.title
    training.delete()
    log_action(request.user, "Formation supprimée", title)
    messages.success(request, "Formation supprimée avec succès.")
    return redirect("trainings")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def training_detail(request, pk):
    training = get_object_or_404(Training, pk=pk)
    enrollments = training.enrollments.select_related("employee")
    return render(request, "hr/training_detail.html", {
        "training": training,
        "enrollments": enrollments,
        "statuses": TrainingEnrollment.Status.choices
    })


@login_required
@require_POST
def training_cancel_enroll(request, pk):
    training = get_object_or_404(Training, pk=pk)
    employee = getattr(request.user, "employee_profile", None)
    if not employee:
        messages.error(request, "Profil employé requis.")
        return redirect("trainings")
    enrollment = TrainingEnrollment.objects.filter(training=training, employee=employee).first()
    if enrollment:
        enrollment.delete()
        notify_user(request.user, "Désinscription formation", f"Vous vous êtes désinscrit(e) de la formation : {training.title}")
        messages.success(request, "Désinscription confirmée.")
    else:
        messages.error(request, "Vous n'êtes pas inscrit à cette formation.")
    return redirect("trainings")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def training_enrollment_update(request, enrollment_pk, status):
    enrollment = get_object_or_404(TrainingEnrollment, pk=enrollment_pk)
    if status in dict(TrainingEnrollment.Status.choices):
        enrollment.status = status
        enrollment.save()
        notify_employee(enrollment.employee, "Statut de formation mis à jour", f"Le statut de votre formation '{enrollment.training.title}' a été modifié en : {enrollment.get_status_display()}")
        log_action(request.user, "Statut formation mis à jour", f"{enrollment.employee} - {enrollment.training} : {status}")
        messages.success(request, "Le statut de l'inscription a été mis à jour.")
    else:
        messages.error(request, "Statut invalide.")
    return redirect(request.POST.get("next") or reverse("training_detail", args=[enrollment.training.pk]))


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def evaluation_delete(request, pk):
    evaluation = get_object_or_404(Evaluation, pk=pk)
    info = f"{evaluation.employee} - {evaluation.period}"
    evaluation.delete()
    log_action(request.user, "Évaluation supprimée", info)
    messages.success(request, "Évaluation supprimée.")
    return redirect("evaluations")


@login_required
def evaluation_detail(request, pk):
    from django.http import HttpResponseForbidden
    evaluation = get_object_or_404(Evaluation, pk=pk)
    if not is_hr(request.user):
        employee = getattr(request.user, "employee_profile", None)
        if not employee or evaluation.employee != employee:
            return HttpResponseForbidden("Vous n'êtes pas autorisé à voir cette évaluation.")
    return render(request, "hr/evaluation_detail.html", {"evaluation": evaluation})


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def planning_delete(request, pk):
    schedule = get_object_or_404(TeamSchedule, pk=pk)
    info = f"{schedule.employee} - {schedule.work_date}"
    schedule.delete()
    log_action(request.user, "Planning shift supprimé", info)
    messages.success(request, "Shift de planning supprimé.")
    return redirect("planning")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def payslip_delete(request, pk):
    payslip = get_object_or_404(Payslip, pk=pk)
    info = f"{payslip.employee} - {payslip.month:02d}/{payslip.year}"
    payslip.delete()
    log_action(request.user, "Fiche de paie supprimée", info)
    messages.success(request, "Fiche de paie supprimée.")
    return redirect("payslips")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def ai_training_recommendations(request):
    from django.shortcuts import get_object_or_404, redirect, render
    
    if request.method == "POST" and "skills" in request.POST:
        employee_id = request.POST.get("employee_id")
        skills_text = request.POST.get("skills", "").strip()
        employee = get_object_or_404(Employee, pk=employee_id)
        
        emp_skill, created = EmployeeSkill.objects.get_or_create(employee=employee)
        emp_skill.skills = skills_text
        emp_skill.save()
        
        messages.success(request, f"Compétences de {employee} mises à jour.")
        return redirect("ai_training_recommendations")
        
    employees = Employee.objects.select_related("department", "skills_profile").all()
    
    # Get latest recommendations for each employee
    recs = {}
    for r in TrainingRecommendation.objects.all().order_by("created_at"):
        recs[r.employee_id] = r
        
    employees_data = []
    for e in employees:
        skills_text = e.skills_profile.skills if getattr(e, "skills_profile", None) else ""
        skills_list = [s.strip() for s in skills_text.split(",") if s.strip()] if skills_text else []
        employees_data.append({
            "employee": e,
            "skills_list": skills_list,
            "recommendation": recs.get(e.id),
        })
        
    return render(request, "hr/training_recommendations.html", {
        "employees_data": employees_data,
    })


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def generate_ai_recommendation(request, employee_id):
    import json
    from .assistant.llm import call_llm
    from datetime import date, timedelta
    from .models import Training, TrainingEnrollment
    
    employee = get_object_or_404(Employee, pk=employee_id)
    skills_obj = getattr(employee, "skills_profile", None)
    skills_text = skills_obj.skills if skills_obj else ""
    
    prompt = f"""
    Tu es un assistant RH intelligent de haut niveau spécialisé dans le développement des compétences.
    Analyse le profil de l'employé suivant et recommande-lui la formation la plus adaptée.
    
    PROFIL :
    - Nom : {employee.first_name} {employee.last_name}
    - Poste actuel : {employee.position}
    - Département : {employee.department.name}
    - Compétences actuelles : {skills_text if skills_text else "Non spécifiées (recommande uniquement selon son poste et son département)"}
    
    CONSIGNES :
    Recommande une formation pertinente (ex. "Django avancé" pour un développeur ou "Optimisation Logistique" pour un technicien transport).
    La formation recommandée ne doit pas être redondante par rapport à ses compétences mais plutôt une évolution naturelle ou un approfondissement.
    Tu devez répondre UNIQUEMENT par un objet JSON valide en français avec les clés suivantes :
    - title: Titre de la formation recommandée (court, max 100 caractères)
    - description: Description sommaire du programme et des objectifs (2-3 phrases)
    - priority: La priorité de la formation ("HIGH" pour Élevée, "MEDIUM" pour Moyenne, "LOW" pour Faible)
    - rationale: La justification pédagogique (pourquoi cette formation aidera cet employé par rapport à son poste, département et compétences).
    
    Format de réponse JSON strict attendu :
    {{
      "title": "...",
      "description": "...",
      "priority": "...",
      "rationale": "..."
    }}
    Ne mets aucun texte en dehors du bloc JSON, pas de markdown ```json, juste le JSON brut.
    """
    
    response_text = call_llm(prompt)
    fallback_used = False
    rec_data = None
    
    if response_text:
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        try:
            rec_data = json.loads(clean_text)
        except Exception:
            pass
            
    if not rec_data:
        fallback_used = True
        skills_lower = skills_text.lower() if skills_text else ""
        pos_lower = employee.position.lower()
        dept_lower = employee.department.name.lower()
        
        if "python" in skills_lower or "sql" in skills_lower or "dev" in pos_lower or "it" in dept_lower:
            rec_data = {
                "title": "Django avancé & Architecture Web",
                "description": "Maîtriser les concepts avancés du framework Django, la conception d'API REST sécurisées et l'optimisation des requêtes de base de données.",
                "priority": "HIGH",
                "rationale": "Recommandation basée sur le profil technique/IT pour maîtriser le développement web moderne."
            }
        elif "lait" in skills_lower or "production" in pos_lower or "production" in dept_lower:
            rec_data = {
                "title": "Management de la Qualité en Industrie Laitière",
                "description": "Approfondissement des normes de sécurité sanitaire, de la méthodologie HACCP et de la gestion des audits internes.",
                "priority": "MEDIUM",
                "rationale": "Recommandation basée sur le profil production agroalimentaire pour monter en compétences sur le contrôle qualité."
            }
        elif "microbiologie" in skills_lower or "haccp" in skills_lower or "qualité" in pos_lower or "qualité" in dept_lower:
            rec_data = {
                "title": "Auditeur Interne Norme ISO 22000",
                "description": "Se former aux techniques d'audit d'un système de management de la sécurité des denrées alimentaires selon la norme internationale ISO 22000.",
                "priority": "HIGH",
                "rationale": "Recommandation basée sur le profil qualité pour obtenir la certification d'auditeur ISO 22000."
            }
        elif "logistique" in skills_lower or "stock" in pos_lower or "logistique" in dept_lower:
            rec_data = {
                "title": "Gestion Avancée des Flux Logistiques et SAP",
                "description": "Maîtriser les logiciels de gestion d'entrepôt, l'optimisation des tournées de distribution et la réduction de l'empreinte carbone des transports.",
                "priority": "MEDIUM",
                "rationale": "Recommandation basée sur le profil logistique pour maîtriser la gestion de flux complexes."
            }
        else:
            rec_data = {
                "title": "Développement Professionnel et Leadership",
                "description": "Renforcer son esprit d'initiative, la gestion du temps, la communication d'équipe et la conduite de réunions efficaces.",
                "priority": "MEDIUM",
                "rationale": "Formation transverse soft skills pour renforcer l'efficacité professionnelle et la collaboration."
            }
            
    priority_value = rec_data.get("priority", "MEDIUM").upper()
    if priority_value not in ["HIGH", "MEDIUM", "LOW"]:
        priority_value = "MEDIUM"
        
    recommendation = TrainingRecommendation.objects.create(
        employee=employee,
        skills=skills_text if skills_text else "Non spécifiées",
        recommended_training_title=rec_data.get("title", "Formation Recommandée"),
        recommended_training_description=rec_data.get("description", ""),
        priority=priority_value,
        rationale=rec_data.get("rationale", ""),
        converted_to_training=True,
    )
    
    training_exists = Training.objects.filter(
        title=recommendation.recommended_training_title,
        department=employee.department
    ).exists()
    
    if training_exists:
        training = Training.objects.filter(
            title=recommendation.recommended_training_title,
            department=employee.department
        ).first()
        created_msg = f"Formation existante '{training.title}' réutilisée"
    else:
        training = Training.objects.create(
            title=recommendation.recommended_training_title,
            description=recommendation.recommended_training_description or f"Formation recommandée par l'IA pour renforcer les compétences de {employee}.",
            trainer="IA SmartZIZ / Expert Externe",
            department=employee.department,
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=32),
            max_participants=15
        )
        created_msg = f"Nouvelle formation '{training.title}' créée"
    
    TrainingEnrollment.objects.get_or_create(
        training=training,
        employee=employee,
        defaults={"status": TrainingEnrollment.Status.REGISTERED}
    )
    
    log_action(request.user, "Recommandation et Inscription IA", f"Formation '{training.title}' associée et {employee} inscrit.")
    
    notify_employee(
        employee,
        "🎓 Nouvelle formation planifiée",
        f"Félicitations ! Suite à l'analyse de vos compétences, vous avez été inscrit à la formation '{training.title}' planifiée à partir du {training.start_date:%d/%m/%Y}.",
        category=Notification.Category.TRAINING
    )
    
    msg = f"{created_msg} et {employee} inscrit d'office !"
    if fallback_used:
        msg += " (Moteur de secours local)."
    messages.success(request, msg)
    
    return redirect("ai_training_recommendations")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def convert_recommendation_to_training(request, rec_id):
    from datetime import date, timedelta
    
    rec = get_object_or_404(TrainingRecommendation, pk=rec_id)
    if rec.converted_to_training:
        messages.warning(request, "Cette recommandation a déjà été convertie en formation.")
        return redirect("ai_training_recommendations")
        
    training = Training.objects.create(
        title=rec.recommended_training_title,
        description=rec.recommended_training_description or f"Formation recommandée par l'IA pour renforcer les compétences de {rec.employee}.",
        trainer="IA SmartZIZ / Expert Externe",
        department=rec.employee.department,
        start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=32),
        max_participants=15
    )
    
    TrainingEnrollment.objects.get_or_create(
        training=training,
        employee=rec.employee,
        defaults={"status": TrainingEnrollment.Status.REGISTERED}
    )
    
    rec.converted_to_training = True
    rec.save(update_fields=["converted_to_training"])
    
    log_action(request.user, "Conversion recommandation IA", f"Formation '{training.title}' créée pour {rec.employee}")
    
    notify_employee(
        rec.employee,
        "🎓 Nouvelle formation planifiée",
        f"Félicitations ! Suite à l'analyse de vos compétences, vous avez été inscrit à la formation '{training.title}' planifiée à partir du {training.start_date:%d/%m/%Y}.",
        category=Notification.Category.TRAINING
    )
    
    messages.success(request, f"Formation '{training.title}' créée. L'employé {rec.employee} a été inscrit et notifié.")
    return redirect("ai_training_recommendations")
