import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


def candidature_cv_upload_to(instance, filename):
    """Stocke le CV sous un nom opaque (jamais le nom original)."""
    return f"candidatures/{uuid.uuid4().hex}.pdf"

class Department(models.Model):
    name = models.CharField("nom", max_length=100, unique=True)
    manager = models.CharField("responsable", max_length=120, blank=True)
    description = models.TextField(blank=True)
    def __str__(self): return self.name

class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur"
        HR = "HR", "Responsable RH"
        EMPLOYEE = "EMPLOYEE", "Employé"
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.EMPLOYEE)
    def __str__(self): return f"{self.user.username} – {self.get_role_display()}"

class Employee(models.Model):
    class AccessStatus(models.TextChoices):
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Autorisé"
        REJECTED = "REJECTED", "Refusé"

    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee_profile")
    employee_id = models.CharField("matricule", max_length=30, unique=True)
    first_name = models.CharField("prénom", max_length=100)
    last_name = models.CharField("nom", max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    position = models.CharField("poste", max_length=120)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    hire_date = models.DateField("date d'embauche")
    photo = models.ImageField(upload_to="employees/", blank=True, null=True)
    active = models.BooleanField(default=True)
    access_status = models.CharField(max_length=12, choices=AccessStatus.choices, default=AccessStatus.APPROVED)
    salary_gross = models.DecimalField("salaire brut RH", max_digits=10, decimal_places=2, default=0)
    salary_net = models.DecimalField("salaire net RH", max_digits=10, decimal_places=2, default=0)
    class Meta: ordering = ["last_name", "first_name"]

    @property
    def effective_salary_gross(self):
        if self.salary_gross and self.salary_gross > 0:
            return self.salary_gross
        latest_payslip = self.payslips.order_by("-year", "-month").first()
        return latest_payslip.gross_salary if latest_payslip else self.salary_gross

    @property
    def effective_salary_net(self):
        if self.salary_net and self.salary_net > 0:
            return self.salary_net
        latest_payslip = self.payslips.order_by("-year", "-month").first()
        return latest_payslip.net_salary if latest_payslip else self.salary_net

    def _default_salary_for_position(self):
        position = (self.position or "").strip().lower()
        if any(keyword in position for keyword in ["manager", "responsable", "chef", "lead", "dir"]):
            return Decimal("18000.00"), Decimal("15000.00")
        if any(keyword in position for keyword in ["dev", "developpeur", "ingénieur", "informatique", "tech", "it"]):
            return Decimal("16000.00"), Decimal("13000.00")
        if any(keyword in position for keyword in ["commercial", "vente", "sales", "account", "compta"]):
            return Decimal("14000.00"), Decimal("11500.00")
        return Decimal("12000.00"), Decimal("10000.00")

    def get_incomplete_onboarding_fields(self):
        missing = []
        if not (self.first_name or "").strip():
            missing.append("prénom")
        if not (self.last_name or "").strip():
            missing.append("nom")
        if not (self.email or "").strip():
            missing.append("e-mail")
        if not (self.employee_id or "").strip():
            missing.append("matricule")
        if not self.hire_date:
            missing.append("date d'embauche")

        position = (self.position or "").strip()
        if not position or position.lower() in {"à préciser", "a preciser", "à preciser"}:
            missing.append("poste")

        department_name = getattr(self.department, "name", "") if self.department_id else ""
        if not self.department_id or not department_name or department_name.lower() in {"non affecté", "non affecte", "non affectée"}:
            missing.append("département")

        if not self.salary_gross or self.salary_gross <= 0:
            missing.append("salaire brut RH")
        if not self.salary_net or self.salary_net <= 0:
            missing.append("salaire net RH")

        if not self.contracts.exists():
            missing.append("contrat")
        if not self.document_requests.exists():
            missing.append("document administratif")
        if not self.payslips.exists():
            missing.append("bulletin de paie")

        return missing

    @property
    def is_onboarding_complete(self):
        return not self.get_incomplete_onboarding_fields()

    def _suggest_department_name(self):
        position = (self.position or "").strip().lower()
        mapping = {
            "dev": "IT",
            "developpeur": "IT",
            "informatique": "IT",
            "tech": "IT",
            "it": "IT",
            "commercial": "Commercial",
            "vente": "Commercial",
            "sales": "Commercial",
            "compta": "Finance",
            "finance": "Finance",
            "rh": "RH",
            "ressources humaines": "RH",
            "marketing": "Marketing",
        }
        for keyword, name in mapping.items():
            if keyword in position:
                return name
        return None

    def _assign_department_from_position(self):
        suggested_name = self._suggest_department_name()
        if not suggested_name:
            return
        current_name = getattr(self.department, "name", "") if self.department_id else ""
        if current_name and current_name != "Non affecté":
            return
        department, _ = Department.objects.get_or_create(
            name=suggested_name,
            defaults={"description": f"Département suggéré automatiquement pour le poste {self.position or 'non précisé'}."},
        )
        self.department = department

    def _salary_values(self):
        gross = self.salary_gross or Decimal("0.00")
        net = self.salary_net or Decimal("0.00")
        if gross <= 0 or net <= 0:
            default_gross, default_net = self._default_salary_for_position()
            gross = gross or default_gross
            net = net or default_net
        return gross, net

    def _normalize_salary_values(self):
        gross, net = self._salary_values()
        self.salary_gross = gross
        self.salary_net = net
        return gross, net

    def _sync_salary_to_latest_payslip(self):
        if not self.payslips.exists():
            return
        latest_payslip = self.payslips.order_by("-year", "-month").first()
        if not latest_payslip:
            return
        latest_payslip.gross_salary = self.salary_gross
        latest_payslip.net_salary = self.salary_net
        latest_payslip.save(update_fields=["gross_salary", "net_salary"])

    def _create_default_onboarding(self):
        if not self.pk:
            return
        if not self.contracts.exists():
            Contract.objects.create(
                employee=self,
                contract_type=Contract.Type.CDI,
                start_date=self.hire_date,
                status=Contract.Status.ACTIVE,
                notes="Contrat créé automatiquement à l’embauche.",
            )
        if not self.document_requests.exists():
            DocumentRequest.objects.create(
                employee=self,
                doc_type=DocumentRequest.DocType.CONTRAT,
                details="Dossier administratif initial créé automatiquement à l’embauche.",
                status=DocumentRequest.Status.PENDING,
            )
        if not self.payslips.exists():
            gross_salary, net_salary = self._salary_values()
            Payslip.objects.create(
                employee=self,
                month=self.hire_date.month,
                year=self.hire_date.year,
                gross_salary=gross_salary,
                net_salary=net_salary,
            )

    def save(self, *args, **kwargs):
        created = self._state.adding
        if created and not self.department_id:
            self._assign_department_from_position()
        elif created or not self.department_id:
            self._assign_department_from_position()

        self._normalize_salary_values()
        super().save(*args, **kwargs)
        if created:
            self._create_default_onboarding()
        else:
            self._sync_salary_to_latest_payslip()

    def __str__(self): return f"{self.first_name} {self.last_name}"

class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Acceptée"
        REJECTED = "REJECTED", "Refusée"
        CANCELLED = "CANCELLED", "Annulée"
    class LeaveType(models.TextChoices):
        ANNUAL = "ANNUAL", "Congé annuel"
        SICK = "SICK", "Congé maladie"
        UNPAID = "UNPAID", "Congé sans solde"
        MATERNITY = "MATERNITY", "Congé maternité"
        OTHER = "OTHER", "Autre"
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField("type de congé", max_length=12, choices=LeaveType.choices, default=LeaveType.ANNUAL)
    start_date = models.DateField("date de début")
    end_date = models.DateField("date de fin")
    reason = models.TextField("motif")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decision_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    @property
    def days(self): return (self.end_date - self.start_date).days + 1
    def __str__(self): return f"{self.employee} ({self.get_status_display()})"

class ChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["created_at"]

class RHDocument(models.Model):
    """Document interne consultable par le moteur RAG."""
    title = models.CharField(max_length=180)
    file = models.FileField(upload_to="rh_documents/")
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.title

class Report(models.Model):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=180, default="Rapport RH")
    summary = models.TextField()
    recommendations = models.TextField(blank=True)
    metrics = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    pdf = models.FileField(upload_to="reports/", blank=True, null=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.title} – {self.created_at:%d/%m/%Y}"

class DocumentRequest(models.Model):
    """Demande de document administratif déposée par un employé."""
    class DocType(models.TextChoices):
        ATTESTATION = "ATTESTATION", "Attestation de travail"
        CERTIFICAT = "CERTIFICAT", "Certificat de salaire"
        CONTRAT = "CONTRAT", "Copie de contrat"
        AUTRE = "AUTRE", "Autre document"
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        READY = "READY", "Prêt"
        DELIVERED = "DELIVERED", "Remis"
        REJECTED = "REJECTED", "Refusée"
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="document_requests")
    doc_type = models.CharField("type de document", max_length=20, choices=DocType.choices)
    details = models.TextField("précisions", blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    hr_comment = models.TextField("commentaire RH", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.employee} – {self.get_doc_type_display()}"

class Announcement(models.Model):
    """Annonce interne publiée par le service RH."""
    class Priority(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        IMPORTANT = "IMPORTANT", "Important"
    title = models.CharField("titre", max_length=180)
    content = models.TextField("contenu")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return self.title

class JobOffer(models.Model):
    """Offre d'emploi gérée par le service RH."""
    class Status(models.TextChoices):
        OPEN = "OPEN", "Ouverte"
        CLOSED = "CLOSED", "Fermée"
    title = models.CharField("intitulé du poste", max_length=180)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="job_offers")
    description = models.TextField("description")
    requirements = models.TextField("profil recherché", blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    deadline = models.DateField("date limite", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return self.title

class Contract(models.Model):
    """Contrat de travail (cahier des charges – gestion des contrats)."""
    class Type(models.TextChoices):
        CDI = "CDI", "CDI"
        CDD = "CDD", "CDD"
        STAGE = "STAGE", "Stage"
        INTERIM = "INTERIM", "Intérim"
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Actif"
        EXPIRED = "EXPIRED", "Expiré"
        TERMINATED = "TERMINATED", "Résilié"
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="contracts")
    contract_type = models.CharField("type", max_length=12, choices=Type.choices, default=Type.CDI)
    start_date = models.DateField("date de début")
    end_date = models.DateField("date de fin", null=True, blank=True)
    file = models.FileField("document", upload_to="contracts/", blank=True, null=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-start_date"]
    def __str__(self): return f"{self.employee} – {self.get_contract_type_display()}"

class Training(models.Model):
    """Formation RH (cahier des charges §5.7 – évolutivité)."""
    title = models.CharField(max_length=180)
    description = models.TextField()
    trainer = models.CharField("formateur", max_length=120, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="trainings")
    start_date = models.DateField()
    end_date = models.DateField()
    max_participants = models.PositiveIntegerField("places max", default=20)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-start_date"]
    def __str__(self): return self.title

class TrainingEnrollment(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "REGISTERED", "Inscrit"
        COMPLETED = "COMPLETED", "Terminé"
        CANCELLED = "CANCELLED", "Annulé"
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name="enrollments")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="training_enrollments")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REGISTERED)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = [("training", "employee")]
    def __str__(self): return f"{self.employee} – {self.training}"

class Evaluation(models.Model):
    """Évaluation du personnel (cahier des charges §5.7)."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="evaluations")
    evaluator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    period = models.CharField("période", max_length=60, help_text="Ex. T1 2026")
    score = models.PositiveSmallIntegerField("note /20", default=10)
    strengths = models.TextField("points forts", blank=True)
    improvements = models.TextField("axes d'amélioration", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.employee} – {self.period}"

class TeamSchedule(models.Model):
    """Planning des équipes."""
    class Shift(models.TextChoices):
        MORNING = "MORNING", "Matin (06h–14h)"
        AFTERNOON = "AFTERNOON", "Après-midi (14h–22h)"
        NIGHT = "NIGHT", "Nuit (22h–06h)"
        REST = "REST", "Repos"
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="schedules")
    work_date = models.DateField("date")
    shift = models.CharField(max_length=12, choices=Shift.choices, default=Shift.MORNING)
    notes = models.CharField(max_length=200, blank=True)
    class Meta: unique_together = [("employee", "work_date")]; ordering = ["work_date", "employee"]
    def __str__(self): return f"{self.employee} – {self.work_date}"

class Payslip(models.Model):
    """Fiche de paie."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="payslips")
    month = models.PositiveSmallIntegerField("mois")
    year = models.PositiveSmallIntegerField("année")
    gross_salary = models.DecimalField("salaire brut", max_digits=10, decimal_places=2, default=0)
    net_salary = models.DecimalField("salaire net", max_digits=10, decimal_places=2, default=0)
    file = models.FileField(upload_to="payslips/", blank=True, null=True)
    published_at = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = [("employee", "month", "year")]; ordering = ["-year", "-month"]
    def __str__(self): return f"{self.employee} – {self.month:02d}/{self.year}"

class Notification(models.Model):
    """Notification in-app (+ e-mail si configuré)."""
    class Priority(models.TextChoices):
        LOW = "LOW", "Faible"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "Élevé"
        URGENT = "URGENT", "Urgent"
    class Category(models.TextChoices):
        LEAVE = "LEAVE", "Congé"
        DOCUMENT = "DOCUMENT", "Document"
        SYSTEM = "SYSTEM", "Système"
        ANNOUNCEMENT = "ANNOUNCEMENT", "Annonce"
        TRAINING = "TRAINING", "Formation"
        EVALUATION = "EVALUATION", "Évaluation"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=180)
    message = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SYSTEM)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    read = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return self.title

class AuditLog(models.Model):
    """Traçabilité des actions importantes (cahier des charges §6.8)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=120)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.action} – {self.created_at:%d/%m/%Y %H:%M}"


class EmployeeSkill(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="skills_profile")
    skills = models.TextField("compétences", help_text="Séparez les compétences par des virgules")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Compétences de {self.employee}"


class TrainingRecommendation(models.Model):
    class Priority(models.TextChoices):
        LOW = "LOW", "Faible"
        MEDIUM = "MEDIUM", "Moyenne"
        HIGH = "HIGH", "Élevée"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="training_recommendations")
    skills = models.TextField("compétences analysées")
    recommended_training_title = models.CharField("formation recommandée", max_length=200)
    recommended_training_description = models.TextField("description de la formation", blank=True)
    priority = models.CharField("priorité", max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    rationale = models.TextField("justification / raison", blank=True)
    converted_to_training = models.BooleanField("converti en formation", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Recommandation pour {self.employee} : {self.recommended_training_title}"


class Filiere(models.Model):
    """Domaine de compétence, modifiable par l'administrateur / RH."""
    name = models.CharField("filière", max_length=120, unique=True)
    active = models.BooleanField("active", default=True)
    order = models.PositiveSmallIntegerField("ordre d'affichage", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "filière"
        verbose_name_plural = "filières"

    def __str__(self):
        return self.name


class CandidatureSpontanee(models.Model):
    class NiveauEtudes(models.TextChoices):
        BAC = "BAC", "Baccalauréat"
        BAC2 = "BAC2", "Bac+2"
        BAC3 = "BAC3", "Bac+3 / Licence"
        BAC5 = "BAC5", "Bac+5 / Master"
        DOCTORAT = "DOCTORAT", "Doctorat"
        AUTRE = "AUTRE", "Autre"

    class TypeCandidature(models.TextChoices):
        CDI = "CDI", "CDI"
        CDD = "CDD", "CDD"
        STAGE = "STAGE", "Stage"
        ALTERNANCE = "ALTERNANCE", "Alternance"
        INDIFFERENT = "INDIFFERENT", "Indifférent"

    class Statut(models.TextChoices):
        NOUVELLE = "NOUVELLE", "Nouvelle"
        EN_COURS = "EN_COURS", "En cours d'étude"
        RETENUE = "RETENUE", "Retenue"
        NON_RETENUE = "NON_RETENUE", "Non retenue"
        ARCHIVEE = "ARCHIVEE", "Archivée"

    nom = models.CharField("nom", max_length=100)
    prenom = models.CharField("prénom", max_length=100)
    email = models.EmailField("e-mail")
    telephone = models.CharField("téléphone", max_length=30)
    ville = models.CharField("ville", max_length=100)
    filiere = models.ForeignKey(Filiere, on_delete=models.PROTECT, related_name="candidatures", verbose_name="filière")
    niveau_etudes = models.CharField("niveau d'études", max_length=12, choices=NiveauEtudes.choices)
    experience = models.PositiveSmallIntegerField("années d'expérience")
    type_candidature = models.CharField("type de candidature souhaité", max_length=14, choices=TypeCandidature.choices)
    cv = models.FileField("CV (PDF)", upload_to=candidature_cv_upload_to)
    message = models.TextField("message / lettre de motivation", blank=True)
    date_candidature = models.DateTimeField("date de candidature", auto_now_add=True)
    statut = models.CharField(max_length=12, choices=Statut.choices, default=Statut.NOUVELLE)
    traite_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="candidatures_traitees", verbose_name="traité par",
    )
    date_traitement = models.DateTimeField("date de traitement", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_candidature"]
        verbose_name = "candidature spontanée"
        verbose_name_plural = "candidatures spontanées"

    def __str__(self):
        return f"{self.prenom} {self.nom} – {self.filiere}"

    @property
    def candidat(self):
        return f"{self.prenom} {self.nom}"
