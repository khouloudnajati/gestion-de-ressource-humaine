from django.contrib import admin
from .models import ChatMessage, Department, Employee, LeaveRequest, Profile, RHDocument, Report, DocumentRequest, Announcement, JobOffer, Contract, Training, TrainingEnrollment, Evaluation, TeamSchedule, Payslip, Notification, AuditLog, Filiere, CandidatureSpontanee

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "last_name", "first_name", "department", "position", "active")
    list_filter = ("department", "active")
    search_fields = ("employee_id", "first_name", "last_name", "email")

@admin.register(LeaveRequest)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ("employee", "start_date", "end_date", "status", "created_at")
    list_filter = ("status",)

@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "doc_type", "status", "created_at")
    list_filter = ("status", "doc_type")

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "priority", "active", "created_at")
    list_filter = ("priority", "active")

@admin.register(JobOffer)
class JobOfferAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "status", "deadline", "created_at")
    list_filter = ("status", "department")

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("employee", "contract_type", "status", "start_date", "end_date")

@admin.register(Training)
class TrainingAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "start_date", "end_date")

@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("employee", "month", "year", "net_salary")

@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "order")
    list_editable = ("active", "order")
    search_fields = ("name",)


@admin.register(CandidatureSpontanee)
class CandidatureSpontaneeAdmin(admin.ModelAdmin):
    list_display = ("nom", "prenom", "email", "filiere", "experience", "date_candidature", "statut")
    list_filter = ("filiere", "statut", "date_candidature", "type_candidature")
    search_fields = ("nom", "prenom", "email", "telephone", "ville")
    readonly_fields = ("date_candidature", "updated_at", "cv")
    date_hierarchy = "date_candidature"
    list_editable = ("statut",)
    fields = (
        "nom", "prenom", "email", "telephone", "ville",
        "filiere", "niveau_etudes", "experience", "type_candidature",
        "cv", "message", "statut", "traite_par", "date_traitement",
        "date_candidature", "updated_at",
    )


admin.site.register([Department, Profile, ChatMessage, RHDocument, Report, TrainingEnrollment, Evaluation, TeamSchedule, Notification, AuditLog])
