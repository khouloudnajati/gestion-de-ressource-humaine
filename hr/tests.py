from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core import mail
from unittest.mock import patch
from hr.forms import RegistrationForm
from hr.services import ai_answer
from hr.models import Employee, Department, Profile, LeaveRequest, Payslip, Contract, DocumentRequest, Training, TrainingEnrollment
from datetime import date

class RegistrationTests(TestCase):
    def test_registration_form_fields(self):
        # Verify that all required fields are present in the form
        form = RegistrationForm()
        self.assertIn("first_name", form.fields)
        self.assertIn("last_name", form.fields)
        self.assertIn("email", form.fields)
        self.assertIn("role", form.fields)
        self.assertIn("password1", form.fields)
        self.assertIn("password2", form.fields)
        self.assertTrue(form.fields["first_name"].required)
        self.assertTrue(form.fields["last_name"].required)
        self.assertTrue(form.fields["email"].required)
        self.assertTrue(form.fields["role"].required)

    def test_registration_employee_success(self):
        # Submit a registration request as Employee
        response = self.client.post(reverse("register"), {
            "first_name": "Rachida",
            "last_name": "Rachida",
            "email": "khoulouddnajati@gmail.com",
            "role": "EMPLOYEE",
            "password1": "PeopleFlow#2026",
            "password2": "PeopleFlow#2026",
        })
        
        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        
        # Verify user was created
        user = User.objects.get(email="khoulouddnajati@gmail.com")
        self.assertEqual(user.first_name, "Rachida")
        self.assertEqual(user.last_name, "Rachida")
        self.assertEqual(user.profile.role, "EMPLOYEE")
        
        # Verify welcome email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["khoulouddnajati@gmail.com"])
        self.assertIn("Bienvenue sur notre plateforme de ziz", email.subject)
        self.assertIn("Bienvenue sur notre plateforme de ziz !", email.body)
        
        # If there is HTML alternative, verify its content as well
        if email.alternatives:
            html_content, mime_type = email.alternatives[0]
            self.assertEqual(mime_type, "text/html")
            self.assertIn("notre plateforme de ziz", html_content)

    def test_registration_hr_success(self):
        # Submit a registration request as HR
        response = self.client.post(reverse("register"), {
            "first_name": "Karim",
            "last_name": "Alaoui",
            "email": "karim.alaoui@gmail.com",
            "role": "HR",
            "password1": "PeopleFlow#2026",
            "password2": "PeopleFlow#2026",
        })
        
        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        
        # Verify user was created
        user = User.objects.get(email="karim.alaoui@gmail.com")
        self.assertEqual(user.first_name, "Karim")
        self.assertEqual(user.last_name, "Alaoui")
        self.assertEqual(user.profile.role, "HR")

class PasswordResetTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_sends_email_for_registered_user(self):
        user = User.objects.create_user(username="forgot_user", email="forgot@example.com", password="password123")

        response = self.client.post(reverse("password_reset"), {"email": user.email})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])

class AdminDashboardTests(TestCase):
    def test_admin_can_access_general_admin_dashboard(self):
        user = User.objects.create_user(username="admin_dashboard", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.ADMIN)
        self.client.login(username="admin_dashboard", password="password123")

        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administration générale")
        self.assertContains(response, "Gestion des rôles")

    def test_admin_can_create_new_user_from_management_page(self):
        user = User.objects.create_user(username="admin_creator", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.ADMIN)
        self.client.login(username="admin_creator", password="password123")

        response = self.client.post(reverse("user_management"), {
            "create-username": "new_admin_user",
            "create-email": "new.admin@example.com",
            "create-first_name": "Nouvel",
            "create-last_name": "Admin",
            "create-password": "StrongPass123!",
            "create-role": Profile.Role.HR,
        })

        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username="new_admin_user")
        self.assertEqual(created_user.email, "new.admin@example.com")
        self.assertEqual(created_user.profile.role, Profile.Role.HR)

    def test_admin_can_delete_regular_user_from_management_page(self):
        admin_user = User.objects.create_user(username="admin_deleter", password="password123")
        Profile.objects.create(user=admin_user, role=Profile.Role.ADMIN)
        user_to_delete = User.objects.create_user(username="user_to_delete", password="password123")
        Profile.objects.create(user=user_to_delete, role=Profile.Role.EMPLOYEE)
        self.client.login(username="admin_deleter", password="password123")

        response = self.client.post(reverse("user_management"), {"delete-user": user_to_delete.pk})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=user_to_delete.pk).exists())

class AssistantTests(TestCase):
    def test_ai_answer_uses_provider_response_when_available(self):
        user = User.objects.create_user(username="assistant_user", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.EMPLOYEE)

        with patch("hr.services._call_llm_provider", return_value="Réponse IA enrichie") as mocked_provider:
            with patch("hr.rag.rag_search", return_value={"text": "Règlement intérieur", "sources": ["Règlement"], "chunks": 1}):
                answer = ai_answer("Quels sont les horaires de travail ?", user)

        self.assertTrue(answer.startswith("Réponse IA enrichie"))
        mocked_provider.assert_called_once()

    def test_ai_answer_returns_employee_email_for_precise_question(self):
        user = User.objects.create_user(username="assistant_email_user", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.EMPLOYEE)
        department = Department.objects.create(name="RH", manager="Manager")
        Employee.objects.create(
            employee_id="EMP-00010",
            first_name="Rachida",
            last_name="Benali",
            email="rachida@example.com",
            position="Responsable RH",
            department=department,
            hire_date=date(2026, 1, 1),
        )

        with patch("hr.services._call_llm_provider", return_value=None):
            answer = ai_answer("Quel est le mail de Rachida ?", user)

        self.assertIn("rachida@example.com", answer)
        self.assertIn("Rachida", answer)

class DepartmentManagementTests(TestCase):
    def test_creating_department_can_assign_existing_employees(self):
        user = User.objects.create_user(username="dept_creator", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.HR)
        self.client.login(username="dept_creator", password="password123")

        other_department = Department.objects.create(name="IT", manager="Karim")
        employee = Employee.objects.create(
            employee_id="EMP-00020",
            first_name="Amine",
            last_name="Mouline",
            email="amine@example.com",
            position="Analyste",
            department=other_department,
            hire_date=date(2026, 1, 1),
        )

        response = self.client.post(reverse("department_add"), {
            "name": "Finance",
            "manager": "Lina",
            "description": "Département finance",
            "selected_employees": [employee.pk],
        })

        self.assertEqual(response.status_code, 302)
        department = Department.objects.get(name="Finance")
        employee.refresh_from_db()
        self.assertEqual(employee.department, department)

    def test_department_page_shows_employees_and_summary(self):
        user = User.objects.create_user(username="dept_admin", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.HR)
        self.client.login(username="dept_admin", password="password123")

        department = Department.objects.create(name="RH", manager="Mina")
        Employee.objects.create(
            employee_id="EMP-00011",
            first_name="Sara",
            last_name="Bennani",
            email="sara@example.com",
            position="Responsable RH",
            department=department,
            hire_date=date(2026, 1, 1),
        )

        response = self.client.get(reverse("departments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RH")
        self.assertContains(response, "Sara Bennani")
        self.assertContains(response, "Résumé")
        self.assertContains(response, "Modifier")

    def test_assign_existing_employee_to_department_from_department_page(self):
        user = User.objects.create_user(username="dept_assigner", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.HR)
        self.client.login(username="dept_assigner", password="password123")

        department = Department.objects.create(name="RH", manager="Mina")
        other_department = Department.objects.create(name="IT", manager="Karim")
        employee = Employee.objects.create(
            employee_id="EMP-00012",
            first_name="Nadia",
            last_name="El Idrissi",
            email="nadia@example.com",
            position="Analyste",
            department=other_department,
            hire_date=date(2026, 1, 1),
        )

        response = self.client.post(reverse("employee_assign_department", args=[department.pk]), {"employee_id": employee.pk})

        self.assertEqual(response.status_code, 302)
        employee.refresh_from_db()
        self.assertEqual(employee.department, department)

    def test_department_page_only_offers_existing_employee_assignment(self):
        user = User.objects.create_user(username="dept_existing_only", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.HR)
        self.client.login(username="dept_existing_only", password="password123")

        department = Department.objects.create(name="Finance", manager="Lina")
        response = self.client.get(reverse("departments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("employee_assign_department", args=[department.pk]))
        self.assertNotContains(response, "/employes/ajouter/")

    def test_department_page_uses_post_forms_for_employee_actions(self):
        user = User.objects.create_user(username="dept_form_actions", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.HR)
        self.client.login(username="dept_form_actions", password="password123")

        department = Department.objects.create(name="Logistique", manager="Yassine")
        Employee.objects.create(
            employee_id="EMP-00013",
            first_name="Mina",
            last_name="Saad",
            email="mina@example.com",
            position="Coordinateur",
            department=department,
            hire_date=date(2026, 1, 1),
        )

        response = self.client.get(reverse("departments"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'action="/employes/')

    def test_employee_remove_department(self):
        user = User.objects.create_user(username="dept_remover", password="password123")
        Profile.objects.create(user=user, role=Profile.Role.HR)
        self.client.login(username="dept_remover", password="password123")

        department = Department.objects.create(name="Logistique", manager="Yassine")
        employee = Employee.objects.create(
            employee_id="EMP-00013",
            first_name="Mina",
            last_name="Saad",
            email="mina@example.com",
            position="Coordinateur",
            department=department,
            hire_date=date(2026, 1, 1),
        )

        response = self.client.post(reverse("employee_remove_department", args=[employee.pk]))

        self.assertEqual(response.status_code, 302)
        
        # Verify employee still exists in system and is unassigned
        employee.refresh_from_db()
        self.assertEqual(employee.department.name, "Non affecté")
        self.assertTrue(Employee.objects.filter(pk=employee.pk).exists())

class EmployeeManagementTests(TestCase):
    def setUp(self):
        # Create an HR user and log in
        self.hr_user = User.objects.create_user(username="hr_user", password="password123")
        Profile.objects.create(user=self.hr_user, role=Profile.Role.HR)
        self.client.login(username="hr_user", password="password123")
        
        self.department = Department.objects.create(name="IT", manager="Manager")
        self.emp1 = Employee.objects.create(
            employee_id="EMP-00001",
            first_name="Anas",
            last_name="Ait",
            email="anas@example.com",
            position="Dev",
            department=self.department,
            hire_date=date(2026, 1, 15)
        )
        self.emp2 = Employee.objects.create(
            employee_id="EMP-00002",
            first_name="Brahim",
            last_name="Bou",
            email="brahim@example.com",
            position="QA",
            department=self.department,
            hire_date=date(2026, 2, 20)
        )

    def test_employee_list_text_search(self):
        url = reverse("employees")
        response = self.client.get(url, {"q": "Anas"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anas")
        self.assertNotContains(response, "Brahim")

    def test_employee_list_date_search(self):
        url = reverse("employees")
        response = self.client.get(url, {"date_inscr": "2026-02-20"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Brahim")
        self.assertNotContains(response, "Anas")

    def test_employee_detail_loads_related(self):
        # Add a leave request and payslip
        LeaveRequest.objects.create(
            employee=self.emp1,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 5),
            reason="Maladie"
        )
        Payslip.objects.create(
            employee=self.emp1,
            month=5,
            year=2026,
            gross_salary=15000,
            net_salary=12000
        )
        
        url = reverse("employee_detail", args=[self.emp1.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("leaves", response.context)
        self.assertIn("payslips", response.context)
        self.assertContains(response, "Maladie")
        self.assertContains(response, "15000")

    def test_new_employee_gets_default_contract_document_and_salary(self):
        employee = Employee.objects.create(
            employee_id="EMP-00003",
            first_name="Sara",
            last_name="Benali",
            email="sara@example.com",
            position="Commerciale",
            department=self.department,
            hire_date=date(2026, 3, 1),
        )

        self.assertTrue(Contract.objects.filter(employee=employee).exists())
        self.assertTrue(DocumentRequest.objects.filter(employee=employee).exists())
        self.assertTrue(Payslip.objects.filter(employee=employee).exists())

    def test_contract_renewal_redirects_back_to_actions_when_requested(self):
        employee = Employee.objects.create(
            employee_id="EMP-00008",
            first_name="Nora",
            last_name="Saidi",
            email="nora@example.com",
            position="Assistante",
            department=self.department,
            hire_date=date(2026, 2, 10),
        )
        contract = Contract.objects.create(
            employee=employee,
            contract_type=Contract.Type.CDD,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 7, 18),
            status=Contract.Status.ACTIVE,
            notes="CDD initial",
        )

        response = self.client.post(
            f"{reverse('contract_edit', args=[contract.pk])}?next=hr_actions",
            {
                "employee": employee.pk,
                "contract_type": Contract.Type.CDD,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "status": Contract.Status.ACTIVE,
                "notes": "CDD renouvelé",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("hr_actions"))

    def test_new_employee_salary_syncs_with_default_payslip(self):
        employee = Employee.objects.create(
            employee_id="EMP-00006",
            first_name="Nadia",
            last_name="Mansouri",
            email="nadia@example.com",
            position="Développeuse",
            department=self.department,
            hire_date=date(2026, 6, 1),
        )

        payslip = employee.payslips.order_by("-year", "-month").first()
        self.assertIsNotNone(payslip)
        self.assertGreater(employee.salary_gross, 0)
        self.assertGreater(employee.salary_net, 0)
        self.assertEqual(employee.salary_gross, payslip.gross_salary)
        self.assertEqual(employee.salary_net, payslip.net_salary)

    def test_employee_detail_uses_latest_payslip_when_rh_salary_is_empty(self):
        employee = Employee.objects.create(
            employee_id="EMP-00007",
            first_name="Rachida",
            last_name="Rachida",
            email="rachida@example.com",
            position="Technicienne Logistique",
            department=self.department,
            hire_date=date(2026, 7, 13),
        )
        payslip = employee.payslips.order_by("-year", "-month").first()
        payslip.gross_salary = 9500
        payslip.net_salary = 8075
        payslip.save(update_fields=["gross_salary", "net_salary"])
        Employee.objects.filter(pk=employee.pk).update(salary_gross=0, salary_net=0)
        employee.refresh_from_db()

        response = self.client.get(reverse("employee_detail", args=[employee.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "9500,00 MAD brut")
        self.assertContains(response, "8075,00 MAD net")

    def test_hr_cannot_approve_employee_access_until_required_profile_info_is_complete(self):
        employee = Employee.objects.create(
            employee_id="EMP-00004",
            first_name="Mina",
            last_name="Elhaj",
            email="mina@example.com",
            position="À préciser",
            department=self.department,
            hire_date=date(2026, 4, 1),
            salary_gross=0,
            salary_net=0,
            access_status=Employee.AccessStatus.PENDING,
        )

        response = self.client.post(
            reverse("employee_access_decide", args=[employee.pk, Employee.AccessStatus.APPROVED]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "complètes")
        employee.refresh_from_db()
        self.assertEqual(employee.access_status, Employee.AccessStatus.PENDING)

    def test_pending_employee_access_is_blocked_until_hr_approval(self):
        user = User.objects.create_user(username="pending_emp", password="PeopleFlow#2026")
        Profile.objects.create(user=user, role=Profile.Role.EMPLOYEE)
        Employee.objects.create(
            user=user,
            employee_id="EMP-00005",
            first_name="Mina",
            last_name="Elhaj",
            email="mina@example.com",
            position="Développeuse",
            department=self.department,
            hire_date=date(2026, 4, 1),
            access_status="PENDING",
        )

        response = self.client.post(reverse("login"), {
            "username": "pending_emp",
            "password": "PeopleFlow#2026",
            "role": "EMPLOYEE",
        })

        self.assertRedirects(response, reverse("access_pending"))

    def test_hr_can_assign_selected_employees_to_training(self):
        employee = Employee.objects.create(
            employee_id="EMP-00005",
            first_name="Omar",
            last_name="Khalid",
            email="omar@example.com",
            position="Analyste",
            department=self.department,
            hire_date=date(2026, 5, 1),
        )

        response = self.client.post(reverse("training_add"), {
            "title": "Formation sécurité",
            "description": "Formation interne",
            "trainer": "Amina",
            "department": self.department.pk,
            "start_date": "2026-06-01",
            "end_date": "2026-06-03",
            "max_participants": 10,
            "selected_employees": [employee.pk],
        })

        self.assertEqual(response.status_code, 302)
        training = Training.objects.get(title="Formation sécurité")
        self.assertTrue(TrainingEnrollment.objects.filter(training=training, employee=employee).exists())

