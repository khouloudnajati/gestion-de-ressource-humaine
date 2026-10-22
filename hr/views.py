from functools import wraps
from io import BytesIO
import csv
from datetime import date
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.db.models import Count, Q
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import (
    DepartmentForm, EmployeeForm, LeaveForm, RegistrationForm, ProfileForm,
    RHDocumentForm, RoleAuthenticationForm, DocumentRequestForm,
    AnnouncementForm, JobOfferForm, CandidatureSpontaneeForm, CandidatureStatutForm,
)
from .models import (
    ChatMessage, Department, Employee, LeaveRequest, Profile, RHDocument,
    Report, DocumentRequest, Announcement, JobOffer, Contract, TrainingEnrollment,
    Notification, Payslip, CandidatureSpontanee, Filiere,
)
from .assistant import pure_ai_answer
from .services import metrics, report_summary, report_recommendations, get_quick_links, get_suggestions, build_user_context
from .notifications import notify_hr_team, notify_employee, send_welcome_email
from .audit import log_action

def role_required(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser or getattr(getattr(request.user, "profile", None), "role", None) in roles: return view(request, *args, **kwargs)
            return HttpResponseForbidden("Vous n’avez pas l’autorisation d’accéder à cette page.")
        return login_required(wrapped)
    return decorate

class SignInView(LoginView):
    template_name = "hr/login.html"
    authentication_form = RoleAuthenticationForm

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        employee = getattr(user, "employee_profile", None)
        if employee and employee.access_status == Employee.AccessStatus.PENDING:
            return redirect("access_pending")
        return response

class RolePasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change_form.html"

    def get_success_url(self):
        if is_hr(self.request.user):
            return reverse_lazy("dashboard")
        return reverse_lazy("profile")

def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            role = form.cleaned_data.get("role", Profile.Role.EMPLOYEE)
            Profile.objects.create(user=user, role=role)
            department, _ = Department.objects.get_or_create(
                name="Non affecté",
                defaults={"description": "Employés en attente d'affectation RH."},
            )
            Employee.objects.create(
                user=user,
                employee_id=f"EMP-{user.pk:05d}",
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                position="À préciser",
                department=department,
                hire_date=date.today(),
                access_status=Employee.AccessStatus.APPROVED if role == Profile.Role.HR else Employee.AccessStatus.PENDING,
            )
            email_sent = send_welcome_email(user)
            notify_user = __import__("hr.notifications", fromlist=["notify_user"]).notify_user
            notify_user(
                user,
                "Bienvenue sur PeopleFlow RH",
                f"Bienvenue {user.first_name} ! Votre compte est actif. Connectez-vous pour accéder à vos services.",
                send_email=False,
            )
            if role == Profile.Role.EMPLOYEE:
                notify_hr_team("Nouvel accès à valider", f"{user.first_name} {user.last_name} a demandé l’accès à la plateforme.")
            log_action(user, "Inscription", f"{user.email}")
            login(request, user)
            if email_sent:
                messages.success(request, f"Bienvenue {user.first_name} ! Un e-mail de confirmation a été envoyé à {user.email}.")
            else:
                messages.success(request, f"Bienvenue {user.first_name} ! Votre compte a été créé avec succès.")
            return redirect("dashboard")
    else:
        form = RegistrationForm()
    return render(request, "hr/register.html", {"form": form})

@login_required
def dashboard(request):
    data = metrics()
    data["recent_leaves"] = LeaveRequest.objects.select_related("employee")[:5]
    data["is_hr"] = is_hr(request.user)
    data["monthly_labels"] = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin"]
    data["monthly_values"] = [LeaveRequest.objects.filter(created_at__month=m).count() for m in range(1, 7)]
    today = date.today()
    if data["is_hr"]:
        data["pending_documents"] = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).count()
        data["inactive_employees"] = Employee.objects.filter(active=False).count()
        data["open_jobs"] = JobOffer.objects.filter(status=JobOffer.Status.OPEN).count()
        data["active_announcements"] = Announcement.objects.filter(active=True).count()
        data["recent_documents"] = DocumentRequest.objects.select_related("employee")[:5]
        data["absences_today"] = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.APPROVED, start_date__lte=today, end_date__gte=today
        ).select_related("employee")
        data["pending_leaves_list"] = LeaveRequest.objects.filter(
            status=LeaveRequest.Status.PENDING
        ).select_related("employee")[:5]
        data["dept_labels"] = [d["name"] for d in data["distribution"]]
        data["dept_values"] = [d["count"] for d in data["distribution"]]
        data["recent_announcements"] = Announcement.objects.filter(active=True)[:3]
        onboarding_actions = []
        for employee in Employee.objects.filter(active=True).select_related("department"):
            missing = []
            if not employee.contracts.exists():
                missing.append("contrat")
            if not employee.document_requests.exists():
                missing.append("document")
            if not employee.payslips.exists():
                missing.append("paie")
            if missing:
                onboarding_actions.append({"employee": employee, "missing": missing})
        data["onboarding_actions"] = onboarding_actions[:8]
        data["onboarding_count"] = len(onboarding_actions)
        candidatures = CandidatureSpontanee.objects.all()
        data["candidatures_total"] = candidatures.count()
        data["candidatures_nouvelles"] = candidatures.filter(statut=CandidatureSpontanee.Statut.NOUVELLE).count()
        data["candidatures_en_cours"] = candidatures.filter(statut=CandidatureSpontanee.Statut.EN_COURS).count()
        data["candidatures_retenues"] = candidatures.filter(statut=CandidatureSpontanee.Statut.RETENUE).count()
        data["candidatures_non_retenues"] = candidatures.filter(statut=CandidatureSpontanee.Statut.NON_RETENUE).count()
        data["candidatures_par_filiere"] = list(
            Filiere.objects.filter(active=True).annotate(nb=Count("candidatures")).order_by("order", "name")
        )
    if not data["is_hr"]:
        employee = getattr(request.user, "employee_profile", None)
        employee_leaves = LeaveRequest.objects.filter(employee=employee) if employee else LeaveRequest.objects.none()
        employee_documents = DocumentRequest.objects.filter(employee=employee).order_by("-created_at") if employee else DocumentRequest.objects.none()
        employee_contracts = Contract.objects.filter(employee=employee).order_by("-start_date") if employee else Contract.objects.none()
        employee_payslip = Payslip.objects.filter(employee=employee).order_by("-year", "-month").first() if employee else None
        data.update({
            "employee": employee,
            "employee_total_leaves": employee_leaves.count(),
            "employee_pending_leaves": employee_leaves.filter(status=LeaveRequest.Status.PENDING).count(),
            "employee_approved_leaves": employee_leaves.filter(status=LeaveRequest.Status.APPROVED).count(),
            "employee_recent_leaves": employee_leaves[:4],
            "employee_document_requests": employee_documents.count() if employee else 0,
            "employee_recent_documents": employee_documents[:4],
            "employee_contracts": employee_contracts[:3],
            "employee_latest_payslip": employee_payslip,
            "announcements": Announcement.objects.filter(active=True)[:5],
            "job_offers": JobOffer.objects.filter(status=JobOffer.Status.OPEN)[:3],
        })
    return render(request, "hr/dashboard.html", data)

def is_hr(user):
    return user.is_superuser or getattr(getattr(user, "profile", None), "role", None) in [Profile.Role.HR, Profile.Role.ADMIN]

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def employee_list(request):
    q = request.GET.get("q", "")
    date_inscr = request.GET.get("date_inscr", "")
    employees = Employee.objects.select_related("department")
    if q:
        employees = employees.filter(
            Q(last_name__icontains=q) | Q(first_name__icontains=q) | Q(employee_id__icontains=q)
        )
    if date_inscr:
        employees = employees.filter(hire_date=date_inscr)
    return render(request, "hr/employees.html", {"employees": employees, "q": q, "date_inscr": date_inscr})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def employee_form(request, pk=None):
    instance = get_object_or_404(Employee, pk=pk) if pk else None
    initial = {}
    department_id = request.GET.get("department")
    if department_id and not instance:
        initial["department"] = get_object_or_404(Department, pk=department_id)
    form = EmployeeForm(request.POST or None, request.FILES or None, instance=instance, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Employé enregistré avec succès."); return redirect("departments")
    return render(request, "hr/form.html", {"form":form, "title":"Modifier l’employé" if pk else "Ajouter un employé"})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    leaves = employee.leave_requests.all().order_by("-start_date")
    documents = employee.document_requests.all().order_by("-created_at")
    contracts = employee.contracts.all().order_by("-start_date")
    payslips = employee.payslips.all().order_by("-year", "-month")
    schedules = employee.schedules.all().order_by("-work_date")
    
    return render(request, "hr/employee_detail.html", {
        "employee": employee,
        "leaves": leaves,
        "documents": documents,
        "contracts": contracts,
        "payslips": payslips,
        "schedules": schedules,
        "access_status_choices": Employee.AccessStatus.choices,
    })

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def employee_delete(request, pk):
    get_object_or_404(Employee, pk=pk).delete()
    messages.success(request, "Employé supprimé.")
    return redirect("employees")

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def employee_remove_department(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    old_dept = employee.department
    unassigned_dept, _ = Department.objects.get_or_create(
        name="Non affecté",
        defaults={"description": "Employés en attente d'affectation RH."}
    )
    employee.department = unassigned_dept
    employee.save(update_fields=["department"])
    messages.success(request, f"{employee} a été retiré du département {old_dept.name}.")
    return redirect("departments")

@login_required
@require_POST
def employee_access_decide(request, pk, status):
    employee = get_object_or_404(Employee, pk=pk)
    if status not in dict(Employee.AccessStatus.choices):
        messages.error(request, "Statut invalide.")
        return redirect("employee_detail", pk=employee.pk)

    if status == Employee.AccessStatus.APPROVED:
        missing_fields = employee.get_incomplete_onboarding_fields()
        if missing_fields:
            missing_text = ", ".join(missing_fields)
            messages.error(
                request,
                f"Impossible d’autoriser l’accès tant que les informations RH suivantes ne sont pas complètes : {missing_text}.",
            )
            return redirect("employee_detail", pk=employee.pk)

    employee.access_status = status
    employee.save(update_fields=["access_status"])
    if status == Employee.AccessStatus.APPROVED:
        notify_employee(employee, "Accès autorisé", "Votre accès à la plateforme a été autorisé par le service RH.")
    else:
        notify_employee(employee, "Accès refusé", "Votre accès à la plateforme a été refusé par le service RH.")
    messages.success(request, "Décision enregistrée.")
    return redirect("employee_detail", pk=employee.pk)

@login_required
def access_pending(request):
    employee = getattr(request.user, "employee_profile", None)
    if not employee:
        return redirect("dashboard")
    if employee.access_status == Employee.AccessStatus.APPROVED:
        return redirect("dashboard")
    return render(request, "hr/access_pending.html", {"employee": employee})

@login_required
def my_profile(request):
    employee = getattr(request.user, "employee_profile", None)
    if not employee: raise Http404("Profil employé indisponible.")
    form = ProfileForm(request.POST or None, request.FILES or None, instance=employee)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Profil mis à jour."); return redirect("profile")
    return render(request, "hr/profile.html", {"form":form, "employee":employee})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def department_list(request):
    departments = Department.objects.prefetch_related("employees").all()
    return render(request, "hr/departments.html", {"departments": departments})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def department_form(request, pk=None):
    instance = get_object_or_404(Department, pk=pk) if pk else None
    form = DepartmentForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Département enregistré."); return redirect("departments")
    context = {"form": form, "title": "Modifier le département" if pk else "Ajouter un département"}
    if instance:
        context["assign_employee_url"] = reverse_lazy("employee_assign_department", args=[instance.pk])
    return render(request, "hr/form.html", context)

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if department.employees.exists():
        messages.error(request, "Impossible de supprimer un département contenant des employés.")
    else:
        department.delete(); messages.success(request, "Département supprimé.")
    return redirect("departments")

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def employee_assign_department(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        if employee_id:
            employee = get_object_or_404(Employee, pk=employee_id)
            if employee.department_id == department.pk:
                messages.info(request, f"{employee} est déjà dans ce département.")
            else:
                employee.department = department
                employee.save(update_fields=["department"])
                messages.success(request, f"{employee} a été affecté à {department.name}.")
        else:
            messages.error(request, "Veuillez sélectionner un employé.")
        return redirect("departments")

    employees = Employee.objects.exclude(department=department).order_by("last_name", "first_name")
    return render(request, "hr/assign_department.html", {"department": department, "employees": employees})

@login_required
def leaves(request):
    employee = getattr(request.user, "employee_profile", None)
    can_manage = is_hr(request.user)
    queryset = LeaveRequest.objects.select_related("employee")

    if not can_manage:
        queryset = queryset.filter(employee=employee)
    else:
        emp_filter = request.GET.get("employee")
        status_filter = request.GET.get("status")
        type_filter = request.GET.get("leave_type")
        start_date_filter = request.GET.get("start_date")
        end_date_filter = request.GET.get("end_date")
        if emp_filter:
            queryset = queryset.filter(employee_id=emp_filter)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if type_filter:
            queryset = queryset.filter(leave_type=type_filter)
        if start_date_filter:
            queryset = queryset.filter(start_date__gte=start_date_filter)
        if end_date_filter:
            queryset = queryset.filter(end_date__lte=end_date_filter)

    stats = {
        "pending": queryset.filter(status=LeaveRequest.Status.PENDING).count(),
        "approved": queryset.filter(status=LeaveRequest.Status.APPROVED).count(),
        "rejected": queryset.filter(status=LeaveRequest.Status.REJECTED).count(),
        "cancelled": queryset.filter(status=LeaveRequest.Status.CANCELLED).count(),
    }

    context = {
        "leaves": queryset,
        "can_manage": can_manage,
        "employee": employee,
        "current_employee": request.GET.get("employee", ""),
        "current_status": request.GET.get("status", ""),
        "current_leave_type": request.GET.get("leave_type", ""),
        "leave_types": LeaveRequest.LeaveType.choices,
        "status_choices": LeaveRequest.Status.choices,
        "stats": stats,
    }
    if can_manage:
        context["all_employees"] = Employee.objects.filter(active=True)
    return render(request, "hr/leaves.html", context)

@login_required
def leave_create(request):
    employee = getattr(request.user, "employee_profile", None)
    if not employee: messages.error(request, "Votre compte n’est pas encore associé à un dossier employé."); return redirect("leaves")
    form = LeaveForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        leave = form.save(commit=False); leave.employee = employee; leave.save()
        notify_hr_team("Nouvelle demande de congé", f"{employee} a déposé une demande de {leave.get_leave_type_display()} du {leave.start_date:%d/%m/%Y} au {leave.end_date:%d/%m/%Y} ({leave.days} jour(s)).")
        log_action(request.user, "Demande de congé déposée", str(leave))
        messages.success(request, "Demande de congé envoyée."); return redirect("leaves")
    return render(request, "hr/form.html", {"form":form, "title":"Nouvelle demande de congé"})

def _leave_notification_message(leave, status):
    period = f"du {leave.start_date:%d/%m/%Y} au {leave.end_date:%d/%m/%Y}"
    type_label = leave.get_leave_type_display()
    if status == LeaveRequest.Status.APPROVED:
        title = "✅ Congé accepté"
        msg = f"Votre demande de {type_label} ({period}) a été ACCEPTÉE par le service RH."
    elif status == LeaveRequest.Status.REJECTED:
        title = "❌ Congé refusé"
        msg = f"Votre demande de {type_label} ({period}) a été REFUSÉE par le service RH."
    else:
        title = f"Congé {leave.get_status_display().lower()}"
        msg = f"Votre demande de {type_label} ({period}) : {leave.get_status_display()}."
    if leave.decision_comment:
        msg += f"\n\nCommentaire RH : {leave.decision_comment}"
    msg += "\n\nConsultez vos congés sur la plateforme PeopleFlow."
    return title, msg


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def leave_decide(request, pk, status):
    leave = get_object_or_404(LeaveRequest, pk=pk)
    if leave.status != LeaveRequest.Status.PENDING:
        messages.warning(request, "Cette demande a déjà été traitée.")
    elif status in [LeaveRequest.Status.APPROVED, LeaveRequest.Status.REJECTED]:
        leave.status = status
        leave.decision_comment = request.POST.get("comment", "").strip()
        leave.save()
        title, msg = _leave_notification_message(leave, status)
        priority = Notification.Priority.HIGH if status == LeaveRequest.Status.APPROVED else Notification.Priority.URGENT
        notify_employee(leave.employee, title, msg, category=Notification.Category.LEAVE, priority=priority)
        log_action(request.user, f"Congé {leave.get_status_display()}", str(leave.employee))
        messages.success(request, f"Demande {leave.get_status_display().lower()} — l'employé a été notifié.")
    return redirect(request.POST.get("next") or "leaves")


@login_required
@require_POST
def leave_cancel(request, pk):
    leave = get_object_or_404(LeaveRequest, pk=pk)
    employee = getattr(request.user, "employee_profile", None)
    if not employee or leave.employee_id != employee.pk:
        return HttpResponseForbidden("Vous ne pouvez annuler que vos propres demandes.")
    if leave.status != LeaveRequest.Status.PENDING:
        messages.warning(request, "Seules les demandes en attente peuvent être annulées.")
    else:
        leave.status = LeaveRequest.Status.CANCELLED
        leave.save()
        notify_hr_team("Demande de congé annulée", f"{employee} a annulé sa demande du {leave.start_date:%d/%m/%Y} au {leave.end_date:%d/%m/%Y}.")
        log_action(request.user, "Congé annulé", str(leave))
        messages.success(request, "Demande de congé annulée.")
    return redirect("leaves")

@login_required
def chatbot(request):
    from .rag import rag_status, rebuild_index
    history = list(ChatMessage.objects.filter(user=request.user).order_by("-created_at")[:12])
    history.reverse()
    rag = rag_status()
    if not rag.get("active"):
        try:
            rebuild_index()
            rag = rag_status()
        except Exception:
            pass
    if request.method == "POST":
        question = request.POST.get("question", "").strip()
        if question:
            answer = pure_ai_answer(question, request.user)
            ChatMessage.objects.create(user=request.user, question=question, answer=answer)
            return redirect("chatbot")
    ctx = build_user_context(request.user)
    import os
    llm_key = any(
        os.getenv(name, "").strip()
        for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
    )
    return render(request, "hr/chatbot.html", {
        "history": history,
        "ai_enabled": llm_key,
        "assistant_active": True,
        "rag_active": rag.get("active", False),
        "quick_links": get_quick_links(request.user),
        "suggestions": get_suggestions(request.user),
        "user_ctx": ctx,
        "rag": rag,
    })

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def report(request):
    data = metrics(); summary = report_summary(data); recommendations = report_recommendations(data)
    return render(request, "hr/report.html", {**data, "summary":summary, "recommendations":recommendations, "history":Report.objects.all()[:8]})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def report_create(request):
    data = metrics()
    report = Report.objects.create(created_by=request.user, title="Rapport RH automatisé", summary=report_summary(data), recommendations=report_recommendations(data), metrics=data)
    messages.success(request, "Rapport IA enregistré avec succès.")
    return redirect("report_detail", pk=report.pk)

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def report_detail(request, pk):
    report_obj = get_object_or_404(Report, pk=pk)
    return render(request, "hr/report.html", {**report_obj.metrics, "summary":report_obj.summary, "recommendations":report_obj.recommendations, "report_obj":report_obj, "history":Report.objects.all()[:8]})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def report_pdf(request):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    data = metrics(); output = BytesIO(); doc = SimpleDocTemplate(output, pagesize=A4); styles = getSampleStyleSheet()
    content = [Paragraph("Rapport RH – PeopleFlow", styles["Title"]), Spacer(1, 18), Paragraph(report_summary(data), styles["BodyText"]), Spacer(1, 12), Paragraph("Recommandations", styles["Heading2"]), Paragraph(report_recommendations(data), styles["BodyText"]), Spacer(1, 12)]
    for label, value in [("Employés actifs", data["employees"]), ("Départements", data["departments"]), ("Congés en attente", data["pending"]), ("Congés acceptés", data["approved"])]: content.append(Paragraph(f"<b>{label} :</b> {value}", styles["BodyText"]))
    doc.build(content); response = HttpResponse(output.getvalue(), content_type="application/pdf"); response["Content-Disposition"] = 'attachment; filename="rapport-rh.pdf"'; return response

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def documents(request):
    from .rag import rag_status, rebuild_index
    form = RHDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        count = rebuild_index()
        messages.success(request, f"Document ajouté. Index RAG mis à jour ({count} fragments).")
        return redirect("documents")
    return render(request, "hr/documents.html", {
        "form": form,
        "documents": RHDocument.objects.all(),
        "rag": rag_status(),
    })

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def document_delete(request, pk):
    from .rag import rebuild_index
    get_object_or_404(RHDocument, pk=pk).delete()
    rebuild_index()
    messages.success(request, "Document supprimé. Index RAG mis à jour.")
    return redirect("documents")

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def rag_rebuild(request):
    from .rag import rebuild_index
    count = rebuild_index()
    messages.success(request, f"Index RAG reconstruit : {count} fragment(s) indexé(s).")
    return redirect(request.POST.get("next") or "documents")

@login_required
def document_requests(request):
    employee = getattr(request.user, "employee_profile", None)
    can_manage = is_hr(request.user)
    queryset = DocumentRequest.objects.select_related("employee") if can_manage else DocumentRequest.objects.filter(employee=employee)
    return render(request, "hr/document_requests.html", {
        "requests": queryset,
        "can_manage": can_manage,
        "employee": employee,
        "pending_count": queryset.filter(status=DocumentRequest.Status.PENDING).count() if can_manage else None,
    })

@login_required
def document_request_create(request):
    employee = getattr(request.user, "employee_profile", None)
    if not employee:
        messages.error(request, "Votre compte n’est pas encore associé à un dossier employé.")
        return redirect("document_requests")
    form = DocumentRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        doc = form.save(commit=False)
        doc.employee = employee
        doc.save()
        notify_hr_team("Nouvelle demande de document", f"{employee} demande : {doc.get_doc_type_display()}.")
        log_action(request.user, "Demande document", str(doc))
        messages.success(request, "Demande de document envoyée au service RH.")
        return redirect("document_requests")
    return render(request, "hr/form.html", {"form": form, "title": "Nouvelle demande de document"})

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def document_request_decide(request, pk, status):
    doc = get_object_or_404(DocumentRequest, pk=pk)
    valid = {DocumentRequest.Status.READY, DocumentRequest.Status.DELIVERED, DocumentRequest.Status.REJECTED}
    if doc.status != DocumentRequest.Status.PENDING:
        messages.warning(request, "Cette demande a déjà été traitée.")
    elif status in valid:
        doc.status = status
        doc.hr_comment = request.POST.get("comment", "")
        doc.save()
        notify_employee(doc.employee, f"Document {doc.get_status_display().lower()}", f"Votre demande ({doc.get_doc_type_display()}) est : {doc.get_status_display().lower()}.{' Commentaire RH : ' + doc.hr_comment if doc.hr_comment else ''}")
        log_action(request.user, f"Document {doc.get_status_display()}", str(doc.employee))
        messages.success(request, "Décision enregistrée.")
    return redirect(request.POST.get("next") or "document_requests")

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def hr_actions(request):
    from datetime import timedelta
    today = date.today()
    pending_leaves = LeaveRequest.objects.filter(status=LeaveRequest.Status.PENDING).select_related("employee")
    pending_docs = DocumentRequest.objects.filter(status=DocumentRequest.Status.PENDING).select_related("employee")
    recent_enrollments = TrainingEnrollment.objects.filter(
        status=TrainingEnrollment.Status.REGISTERED
    ).select_related("employee", "training").order_by("-enrolled_at")[:10]
    expiring_contracts = Contract.objects.filter(
        status=Contract.Status.ACTIVE,
        end_date__isnull=False,
        end_date__lte=today + timedelta(days=30),
        end_date__gte=today,
    ).select_related("employee").order_by("end_date")[:10]
    pending_access_requests = Employee.objects.filter(active=True, access_status=Employee.AccessStatus.PENDING).select_related("department")
    onboarding_items = []
    for employee in Employee.objects.filter(active=True).select_related("department"):
        missing = []
        if not employee.contracts.exists():
            missing.append("contrat")
        if not employee.document_requests.exists():
            missing.append("document")
        if not employee.payslips.exists():
            missing.append("paie")
        if missing:
            onboarding_items.append({"employee": employee, "missing": missing})
    return render(request, "hr/hr_actions.html", {
        "pending_leaves": pending_leaves,
        "pending_docs": pending_docs,
        "recent_enrollments": recent_enrollments,
        "expiring_contracts": expiring_contracts,
        "onboarding_items": onboarding_items,
        "pending_access_requests": pending_access_requests,
        "total_pending": (
            pending_leaves.count() + pending_docs.count()
            + recent_enrollments.count() + expiring_contracts.count() + len(onboarding_items) + pending_access_requests.count()
        ),
        "enrollment_statuses": TrainingEnrollment.Status.choices,
    })


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def hr_bulk_leave_decide(request, status):
    if status not in [LeaveRequest.Status.APPROVED, LeaveRequest.Status.REJECTED]:
        messages.error(request, "Action invalide.")
        return redirect("hr_actions")
    ids = request.POST.getlist("leave_ids")
    comment = request.POST.get("comment", "").strip()
    if not ids:
        messages.warning(request, "Aucune demande sélectionnée.")
        return redirect("hr_actions")
    count = 0
    priority = Notification.Priority.HIGH if status == LeaveRequest.Status.APPROVED else Notification.Priority.URGENT
    for leave in LeaveRequest.objects.filter(pk__in=ids, status=LeaveRequest.Status.PENDING):
        leave.status = status
        leave.decision_comment = comment
        leave.save()
        title, msg = _leave_notification_message(leave, status)
        notify_employee(leave.employee, title, msg, category=Notification.Category.LEAVE, priority=priority)
        log_action(request.user, f"Congé {leave.get_status_display()} (lot)", str(leave.employee))
        count += 1
    if count:
        messages.success(request, f"{count} demande(s) traitée(s) — employés notifiés.")
    else:
        messages.warning(request, "Aucune demande en attente trouvée.")
    return redirect("hr_actions")

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def hr_bulk_doc_decide(request, status):
    valid = {DocumentRequest.Status.READY, DocumentRequest.Status.REJECTED}
    if status not in valid:
        messages.error(request, "Action invalide.")
        return redirect("hr_actions")
    ids = request.POST.getlist("doc_ids")
    comment = request.POST.get("comment", "").strip()
    if not ids:
        messages.warning(request, "Aucune demande sélectionnée.")
        return redirect("hr_actions")
    count = 0
    for doc in DocumentRequest.objects.filter(pk__in=ids, status=DocumentRequest.Status.PENDING):
        doc.status = status
        doc.hr_comment = comment
        doc.save()
        notify_employee(doc.employee, f"Document {doc.get_status_display().lower()}", f"Votre demande ({doc.get_doc_type_display()}) est : {doc.get_status_display().lower()}.{' Commentaire RH : ' + doc.hr_comment if doc.hr_comment else ''}")
        log_action(request.user, f"Document {doc.get_status_display()} (lot)", str(doc.employee))
        count += 1
    if count:
        messages.success(request, f"{count} demande(s) traitée(s) — employés notifiés.")
    else:
        messages.warning(request, "Aucune demande en attente trouvée.")
    return redirect("hr_actions")

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def announcements(request):
    form = AnnouncementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ann = form.save(commit=False)
        ann.created_by = request.user
        ann.save()
        log_action(request.user, "Annonce publiée", ann.title)
        messages.success(request, "Annonce publiée.")
        return redirect("announcements")
    return render(request, "hr/announcements.html", {
        "form": form,
        "announcements": Announcement.objects.all(),
    })

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def announcement_delete(request, pk):
    get_object_or_404(Announcement, pk=pk).delete()
    messages.success(request, "Annonce supprimée.")
    return redirect("announcements")

@login_required
def job_offers(request):
    offers = JobOffer.objects.select_related("department")
    can_manage = is_hr(request.user)
    if not can_manage:
        offers = offers.filter(status=JobOffer.Status.OPEN)
    return render(request, "hr/job_offers.html", {
        "offers": offers,
        "open_count": JobOffer.objects.filter(status=JobOffer.Status.OPEN).count(),
        "can_manage": can_manage,
    })

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def job_offer_form(request, pk=None):
    instance = get_object_or_404(JobOffer, pk=pk) if pk else None
    form = JobOfferForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        offer = form.save(commit=False)
        if not instance:
            offer.created_by = request.user
        offer.save()
        messages.success(request, "Offre d'emploi enregistrée.")
        return redirect("job_offers")
    return render(request, "hr/form.html", {
        "form": form,
        "title": "Modifier l'offre" if pk else "Nouvelle offre d'emploi",
    })

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def job_offer_delete(request, pk):
    get_object_or_404(JobOffer, pk=pk).delete()
    messages.success(request, "Offre supprimée.")
    return redirect("job_offers")

@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def employee_export(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="employes-peopleflow.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Matricule", "Prénom", "Nom", "E-mail", "Téléphone", "Poste", "Département", "Date embauche", "Actif"])
    for e in Employee.objects.select_related("department"):
        writer.writerow([e.employee_id, e.first_name, e.last_name, e.email, e.phone, e.position, e.department.name, e.hire_date, "Oui" if e.active else "Non"])
    return response


def candidature_spontanee(request):
    form = CandidatureSpontaneeForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            candidature = form.save()
            notify_hr_team(
                "Nouvelle candidature spontanée reçue",
                f"{candidature.prenom} {candidature.nom} ({candidature.filiere}) a déposé une candidature spontanée.",
                priority=Notification.Priority.HIGH,
            )
            log_action(None, "Candidature spontanée", f"{candidature.email} – {candidature.filiere}")
            return redirect("candidature_spontanee_merci")
        messages.error(request, "Votre candidature n'a pas pu être envoyée. Merci de corriger les erreurs indiquées.")
    return render(request, "hr/candidature_spontanee.html", {"form": form})


def candidature_spontanee_merci(request):
    return render(request, "hr/candidature_spontanee_merci.html")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def candidatures_rh(request):
    qs = CandidatureSpontanee.objects.select_related("filiere", "traite_par")
    q = (request.GET.get("q") or "").strip()
    filiere_id = request.GET.get("filiere") or ""
    statut = request.GET.get("statut") or ""
    tri = request.GET.get("tri") or "desc"

    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(email__icontains=q))
    if filiere_id.isdigit():
        qs = qs.filter(filiere_id=int(filiere_id))
    if statut in dict(CandidatureSpontanee.Statut.choices):
        qs = qs.filter(statut=statut)
    qs = qs.order_by("date_candidature" if tri == "asc" else "-date_candidature")

    all_cands = CandidatureSpontanee.objects.all()
    return render(request, "hr/candidatures_rh.html", {
        "candidatures": qs,
        "filieres": Filiere.objects.filter(active=True),
        "statuts": CandidatureSpontanee.Statut.choices,
        "q": q,
        "filiere_id": filiere_id,
        "statut": statut,
        "tri": tri,
        "candidatures_total": all_cands.count(),
        "candidatures_nouvelles": all_cands.filter(statut=CandidatureSpontanee.Statut.NOUVELLE).count(),
        "candidatures_en_cours": all_cands.filter(statut=CandidatureSpontanee.Statut.EN_COURS).count(),
        "candidatures_retenues": all_cands.filter(statut=CandidatureSpontanee.Statut.RETENUE).count(),
        "candidatures_non_retenues": all_cands.filter(statut=CandidatureSpontanee.Statut.NON_RETENUE).count(),
        "candidatures_par_filiere": list(
            Filiere.objects.filter(active=True).annotate(nb=Count("candidatures")).order_by("order", "name")
        ),
    })


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def candidature_rh_detail(request, pk):
    candidature = get_object_or_404(CandidatureSpontanee.objects.select_related("filiere", "traite_par"), pk=pk)
    form = CandidatureStatutForm(request.POST or None, instance=candidature)
    if request.method == "POST" and form.is_valid():
        candidature = form.save(commit=False)
        candidature.traite_par = request.user
        candidature.date_traitement = timezone.now()
        candidature.save()
        log_action(request.user, "Candidature mise à jour", f"{candidature} → {candidature.get_statut_display()}")
        messages.success(request, "Le statut de la candidature a été mis à jour.")
        return redirect("candidature_rh_detail", pk=candidature.pk)
    return render(request, "hr/candidature_rh_detail.html", {
        "candidature": candidature,
        "form": form,
    })


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
@require_POST
def candidature_rh_archive(request, pk):
    candidature = get_object_or_404(CandidatureSpontanee, pk=pk)
    candidature.statut = CandidatureSpontanee.Statut.ARCHIVEE
    candidature.traite_par = request.user
    candidature.date_traitement = timezone.now()
    candidature.save(update_fields=["statut", "traite_par", "date_traitement", "updated_at"])
    log_action(request.user, "Candidature archivée", str(candidature))
    messages.success(request, "La candidature a été archivée.")
    return redirect("candidatures_rh")


@role_required(Profile.Role.HR, Profile.Role.ADMIN)
def candidature_cv(request, pk):
    candidature = get_object_or_404(CandidatureSpontanee, pk=pk)
    if not candidature.cv:
        raise Http404("Aucun CV n'est associé à cette candidature.")
    try:
        as_attachment = request.GET.get("download") == "1"
        return FileResponse(
            candidature.cv.open("rb"),
            as_attachment=as_attachment,
            filename=f"CV_{candidature.nom}_{candidature.prenom}.pdf",
            content_type="application/pdf",
        )
    except FileNotFoundError:
        raise Http404("Le fichier CV est introuvable.")
