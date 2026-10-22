import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import Department, Employee, EmployeeSkill, LeaveRequest, RHDocument, DocumentRequest, Announcement, JobOffer, Contract, Training, TrainingEnrollment, Evaluation, TeamSchedule, Payslip, Profile, CandidatureSpontanee, Filiere

CV_MAX_SIZE = 5 * 1024 * 1024
PHONE_RE = re.compile(r"^\+?[\d\s.\-]{8,20}$")


class RoleAuthenticationForm(AuthenticationForm):
    """Authentifie l'utilisateur dans l'espace correspondant à son rôle."""

    role = forms.ChoiceField(
        label="Se connecter en tant que",
        choices=[("EMPLOYEE", "Employé"), ("HR", "Responsable RH")],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        user = self.get_user()
        selected_role = cleaned_data.get("role")

        if user and selected_role:
            stored_role = getattr(getattr(user, "profile", None), "role", None)
            actual_role = "HR" if user.is_superuser or stored_role in {"HR", "ADMIN"} else stored_role
            if actual_role != selected_role:
                raise forms.ValidationError(
                    "Ce compte ne correspond pas au type d'accès sélectionné."
                )
        return cleaned_data

class StyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

class EmployeeForm(StyledForm):
    skills = forms.CharField(
        label="Compétences (séparées par des virgules)",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ex: Python, SQL, Git"}),
    )

    class Meta:
        model = Employee
        fields = ["employee_id", "first_name", "last_name", "email", "phone", "position", "department", "hire_date", "photo", "active", "access_status", "salary_gross", "salary_net"]
        widgets = {"hire_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                self.fields["skills"].initial = self.instance.skills_profile.skills
            except Exception:
                pass

    def save(self, commit=True):
        employee = super().save(commit=commit)
        skills_text = self.cleaned_data.get("skills", "").strip()
        if commit:
            emp_skill, _ = EmployeeSkill.objects.get_or_create(employee=employee)
            emp_skill.skills = skills_text
            emp_skill.save()
        return employee

class DepartmentForm(StyledForm):
    selected_employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.none(),
        required=False,
        label="Employés à affecter",
    )

    class Meta:
        model = Department
        fields = ["name", "manager", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected_employees"].queryset = Employee.objects.filter(active=True).order_by("last_name", "first_name")
        if self.instance.pk:
            self.fields["selected_employees"].initial = list(self.instance.employees.values_list("id", flat=True))

    def save(self, commit=True):
        department = super().save(commit=commit)
        selected_ids = self.cleaned_data.get("selected_employees", [])
        if commit:
            Employee.objects.filter(pk__in=[employee.pk for employee in selected_ids]).update(department=department)
        return department

class LeaveForm(StyledForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "reason"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 3, "placeholder": "Précisez le motif de votre demande"}),
        }
    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]: self.add_error("end_date", "La date de fin doit être postérieure à la date de début.")
        return data

class RegistrationForm(UserCreationForm):
    """Inscription : prénom, nom, e-mail, rôle et mot de passe."""
    first_name = forms.CharField(label="Prénom", max_length=150, required=True)
    last_name = forms.CharField(label="Nom", max_length=150, required=True)
    email = forms.EmailField(label="E-mail", required=True)
    role = forms.ChoiceField(
        label="Rôle",
        choices=[("EMPLOYEE", "Employé"), ("HR", "Responsable RH")],
        required=True,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Mot de passe"
        self.fields["password2"].label = "Confirmer le mot de passe"
        field_order = ["first_name", "last_name", "email", "role", "password1", "password2"]
        self.order_fields(field_order)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte utilise déjà cette adresse e-mail.")
        return email

    def _unique_username(self, email: str) -> str:
        base = email.split("@")[0].replace(".", "_")[:30] or "user"
        candidate = base
        n = 1
        while User.objects.filter(username__iexact=candidate).exists():
            suffix = str(n)
            candidate = f"{base[:30 - len(suffix)]}{suffix}"
            n += 1
        return candidate

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.username = self._unique_username(user.email)
        if commit:
            user.save()
        return user

class ProfileForm(StyledForm):
    skills = forms.CharField(
        label="Vos compétences (séparées par des virgules)",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ex: Python, SQL, Git"}),
    )

    class Meta:
        model = Employee
        fields = ["first_name", "last_name", "email", "phone", "photo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                self.fields["skills"].initial = self.instance.skills_profile.skills
            except Exception:
                pass

    def save(self, commit=True):
        employee = super().save(commit=commit)
        skills_text = self.cleaned_data.get("skills", "").strip()
        if commit:
            emp_skill, _ = EmployeeSkill.objects.get_or_create(employee=employee)
            emp_skill.skills = skills_text
            emp_skill.save()
        return employee

class RHDocumentForm(StyledForm):
    class Meta:
        model = RHDocument
        fields = ["title", "file", "description", "active"]

class DocumentRequestForm(StyledForm):
    class Meta:
        model = DocumentRequest
        fields = ["doc_type", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 3, "placeholder": "Précisez votre besoin (optionnel)"})}

class AnnouncementForm(StyledForm):
    class Meta:
        model = Announcement
        fields = ["title", "content", "priority", "active"]
        widgets = {"content": forms.Textarea(attrs={"rows": 4})}

class JobOfferForm(StyledForm):
    class Meta:
        model = JobOffer
        fields = ["title", "department", "description", "requirements", "status", "deadline"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "requirements": forms.Textarea(attrs={"rows": 3}),
            "deadline": forms.DateInput(attrs={"type": "date"}),
        }

class ContractForm(StyledForm):
    class Meta:
        model = Contract
        fields = ["employee", "contract_type", "start_date", "end_date", "file", "status", "notes"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 2})}

class TrainingForm(StyledForm):
    selected_employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(active=True),
        required=False,
        label="Employés à inscrire",
    )

    class Meta:
        model = Training
        fields = ["title", "description", "trainer", "department", "start_date", "end_date", "max_participants"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected_employees"].queryset = Employee.objects.filter(active=True).order_by("last_name", "first_name")
        if self.instance.pk:
            self.fields["selected_employees"].initial = list(self.instance.enrollments.values_list("employee_id", flat=True))

    def save(self, commit=True):
        training = super().save(commit=commit)
        selected_ids = self.cleaned_data.get("selected_employees", [])
        if commit:
            training.enrollments.exclude(employee_id__in=[e.pk for e in selected_ids]).delete()
            for employee in selected_ids:
                TrainingEnrollment.objects.get_or_create(training=training, employee=employee)
        return training

class EvaluationForm(StyledForm):
    class Meta:
        model = Evaluation
        fields = ["employee", "period", "score", "strengths", "improvements"]
        widgets = {"strengths": forms.Textarea(attrs={"rows": 2}), "improvements": forms.Textarea(attrs={"rows": 2})}

class TeamScheduleForm(StyledForm):
    class Meta:
        model = TeamSchedule
        fields = ["employee", "work_date", "shift", "notes"]
        widgets = {"work_date": forms.DateInput(attrs={"type": "date"})}

class PayslipForm(StyledForm):
    class Meta:
        model = Payslip
        fields = ["employee", "month", "year", "gross_salary", "net_salary", "file"]
        widgets = {"month": forms.NumberInput(attrs={"min": 1, "max": 12}), "year": forms.NumberInput(attrs={"min": 2020, "max": 2035})}

class UserRoleForm(forms.Form):
    role = forms.ChoiceField(label="Rôle", choices=Profile.Role.choices)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].widget.attrs["class"] = "form-control"


class CandidatureSpontaneeForm(StyledForm):
    class Meta:
        model = CandidatureSpontanee
        fields = [
            "nom", "prenom", "email", "telephone", "ville",
            "filiere", "niveau_etudes", "experience", "type_candidature",
            "cv", "message",
        ]
        widgets = {
            "message": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Présentez-vous en quelques lignes (facultatif).",
            }),
            "experience": forms.NumberInput(attrs={"min": 0, "max": 50}),
            "cv": forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"}),
        }
        help_texts = {
            "cv": "Fichier PDF uniquement, 5 Mo maximum.",
            "experience": "Indiquez 0 si vous n'avez pas encore d'expérience professionnelle.",
            "message": "Facultatif.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["filiere"].queryset = Filiere.objects.filter(active=True)
        self.fields["filiere"].empty_label = "Sélectionnez une filière"
        self.fields["message"].required = False
        self.fields["cv"].required = True
        for name in ("filiere", "niveau_etudes", "type_candidature"):
            self.fields[name].widget.attrs["class"] = "form-select"

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_telephone(self):
        telephone = (self.cleaned_data.get("telephone") or "").strip()
        digits = re.sub(r"\D", "", telephone)
        if not PHONE_RE.match(telephone) or len(digits) < 8:
            raise forms.ValidationError("Indiquez un numéro de téléphone valide (au moins 8 chiffres).")
        return telephone

    def clean_cv(self):
        cv = self.cleaned_data.get("cv")
        if not cv:
            raise forms.ValidationError("Le CV au format PDF est obligatoire.")
        name = (getattr(cv, "name", "") or "").lower()
        content_type = (getattr(cv, "content_type", "") or "").lower()
        if not name.endswith(".pdf"):
            raise forms.ValidationError("Seuls les fichiers PDF sont acceptés. Veuillez envoyer un CV au format PDF.")
        if content_type and content_type not in {"application/pdf", "application/x-pdf", "binary/octet-stream"}:
            raise forms.ValidationError("Seuls les fichiers PDF sont acceptés.")
        if cv.size > CV_MAX_SIZE:
            raise forms.ValidationError("Le CV ne doit pas dépasser 5 Mo.")
        header = cv.read(5)
        if hasattr(cv, "seek"):
            cv.seek(0)
        if header != b"%PDF-":
            raise forms.ValidationError("Le fichier n'est pas un PDF valide. Merci d'envoyer un CV au format PDF.")
        return cv


class CandidatureStatutForm(forms.ModelForm):
    class Meta:
        model = CandidatureSpontanee
        fields = ["statut"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["statut"].widget.attrs["class"] = "form-select"
