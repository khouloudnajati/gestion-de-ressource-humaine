from datetime import date

from unittest.mock import patch



from django.contrib.auth.models import User

from django.test import TestCase



from hr.assistant import pure_ai_answer
from hr.assistant.llm import call_llm

from hr.assistant.access import employee_access_denial

from hr.models import Department, Employee, Profile

from hr.services import build_user_context, local_chat_answer





class PureAssistantTests(TestCase):

    def test_llm_tries_openrouter_then_openai(self):
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openrouter",
                "OPENROUTER_API_KEY": "router-key",
                "OPENAI_API_KEY": "openai-key",
                "GEMINI_API_KEY": "",
            },
        ):
            with patch(
                "hr.assistant.llm._call_provider",
                side_effect=[None, "Réponse OpenAI"],
            ) as provider:
                answer = call_llm("Question")

        self.assertEqual(answer, "Réponse OpenAI")
        self.assertEqual(
            [call.args[0] for call in provider.call_args_list],
            ["openrouter", "openai"],
        )

    def test_pure_ai_answer_uses_llm_when_available(self):

        user = User.objects.create_user(username="pure_ai_user", password="password123")

        Profile.objects.create(user=user, role=Profile.Role.EMPLOYEE)



        with patch("hr.assistant.engine.call_llm", return_value="Réponse IA pure"):

            with patch("hr.assistant.engine.rag_search", return_value={"text": "Règlement", "sources": ["Règlement"], "chunks": 1}):

                answer = pure_ai_answer("Quels sont les horaires ?", user)



        self.assertIn("Réponse IA pure", answer)



    def test_pure_ai_answer_falls_back_to_adapted_rag_without_llm(self):

        user = User.objects.create_user(username="pure_rag_user", password="password123")

        Profile.objects.create(user=user, role=Profile.Role.EMPLOYEE)



        rag_payload = {

            "text": "[reglement_interieur.txt]\nHORAIRES DE TRAVAIL\n- Bureaux : 08h30 – 17h30 du lundi au vendredi.\n- Production : postes en 3×8.",

            "sources": ["reglement_interieur.txt"],

            "chunks": 1,

        }



        with patch("hr.assistant.engine.call_llm", return_value=None):

            with patch("hr.assistant.engine.rag_search", return_value=rag_payload):

                with patch("hr.assistant.engine.local_chat_answer", return_value="Je peux répondre à des questions concrètes"):

                    answer = pure_ai_answer("Quels sont les horaires de bureau ?", user)



        self.assertIn("08h30", answer)

        self.assertNotIn("[reglement_interieur.txt]", answer)

        self.assertIn("horaires", answer.lower())



    def test_pure_ai_answer_injects_live_employee_data_in_prompt(self):

        user = User.objects.create_user(username="pure_hr_user", password="password123")

        Profile.objects.create(user=user, role=Profile.Role.HR)

        department = Department.objects.create(name="RH", manager="Manager")

        Employee.objects.create(

            employee_id="EMP-00099",

            first_name="Rachida",

            last_name="Benali",

            email="rachida@example.com",

            position="Responsable RH",

            department=department,

            hire_date=date(2026, 1, 1),

        )



        captured = {}



        def fake_call(prompt):

            captured["prompt"] = prompt

            return "Email : rachida@example.com"



        with patch("hr.assistant.engine.call_llm", side_effect=fake_call):

            with patch("hr.assistant.engine.rag_search", return_value={"text": "", "sources": [], "chunks": 0}):

                with patch("hr.assistant.engine.local_chat_answer", return_value="Je peux répondre à des questions concrètes"):

                    answer = pure_ai_answer("Quel est le mail de Rachida ?", user)



        self.assertIn("rachida@example.com", answer)

        self.assertIn("rachida@example.com", captured.get("prompt", ""))





class RoleBasedAssistantTests(TestCase):

    def setUp(self):

        self.dept = Department.objects.create(name="Production", manager="Chef")

        self.hr_user = User.objects.create_user(username="hr1", password="pass", first_name="HR")

        Profile.objects.create(user=self.hr_user, role=Profile.Role.HR)

        self.emp_user = User.objects.create_user(username="emp1", password="pass", first_name="Ali")

        Profile.objects.create(user=self.emp_user, role=Profile.Role.EMPLOYEE)

        self.colleague = Employee.objects.create(

            employee_id="EMP-001",

            user=self.emp_user,

            first_name="Ali",

            last_name="Ben",

            email="ali@example.com",

            position="Opérateur",

            department=self.dept,

            hire_date=date(2025, 1, 1),

        )

        self.other = Employee.objects.create(

            employee_id="EMP-002",

            first_name="Sara",

            last_name="Dupont",

            email="sara@example.com",

            position="Technicien",

            department=self.dept,

            hire_date=date(2025, 6, 1),

        )



    def test_employee_leave_question_gives_complete_guide_not_raw_urls(self):

        ctx = build_user_context(self.emp_user)

        answer = local_chat_answer("Comment déposer une demande de congé ?", ctx)

        self.assertIn("Congés", answer)

        self.assertIn("Nouvelle demande", answer)

        self.assertNotIn("/conges/", answer)



    def test_employee_cannot_access_colleague_email(self):

        ctx = build_user_context(self.emp_user)

        answer = local_chat_answer("Quel est l'email de Sara ?", ctx)

        self.assertIn("propres informations", answer.lower())



    def test_employee_access_denial_blocks_colleague_name(self):

        ctx = build_user_context(self.emp_user)

        denial = employee_access_denial("Donne moi les congés de Sara Dupont", ctx)

        self.assertIsNotNone(denial)



    def test_hr_can_access_colleague_info(self):

        ctx = build_user_context(self.hr_user)

        answer = local_chat_answer("Quel est l'email de Sara ?", ctx)

        self.assertIn("sara@example.com", answer)



    def test_employee_self_email(self):

        ctx = build_user_context(self.emp_user)

        answer = local_chat_answer("Quel est mon email ?", ctx)

        self.assertIn("ali@example.com", answer)

    def test_hr_access_requests_count(self):
        from hr.models import Employee as Emp

        Emp.objects.create(
            employee_id="EMP-003",
            first_name="Nouveau",
            last_name="User",
            email="new@example.com",
            position="Stagiaire",
            department=self.dept,
            hire_date=date(2026, 1, 1),
            access_status=Emp.AccessStatus.PENDING,
        )
        ctx = build_user_context(self.hr_user)
        answer = local_chat_answer("combien Demandes d'accès à valider ?", ctx)
        self.assertIn("demande(s) d'accès", answer.lower())
        self.assertNotIn("plateforme rh", answer.lower())

    def test_hr_contract_typo_short_name(self):
        from hr.models import Contract

        target = Employee.objects.create(
            employee_id="EMP-EE",
            first_name="e",
            last_name="e",
            email="ee@example.com",
            position="Test",
            department=self.dept,
            hire_date=date(2025, 1, 1),
        )
        Contract.objects.create(
            employee=target,
            contract_type=Contract.Type.CDI,
            start_date=date(2025, 1, 1),
            status=Contract.Status.ACTIVE,
        )
        ctx = build_user_context(self.hr_user)
        answer = local_chat_answer("quel type de contra de e e", ctx)
        self.assertIn("CDI", answer)
        self.assertNotIn("plateforme rh", answer.lower())

    def test_hr_hire_date_by_name(self):
        ctx = build_user_context(self.hr_user)
        answer = local_chat_answer("Date Embauche de Ali Ben", ctx)
        self.assertIn("Date d'embauche", answer)
        self.assertIn("Ali Ben", answer)
        self.assertNotIn("Offres d'emploi", answer)

    def test_employee_contract_type_question(self):
        from hr.models import Contract

        Contract.objects.create(
            employee=self.colleague,
            contract_type=Contract.Type.CDI,
            start_date=date(2025, 1, 1),
            status=Contract.Status.ACTIVE,
        )
        ctx = build_user_context(self.emp_user)
        answer = local_chat_answer("quel type de contrat de travail", ctx)
        self.assertIn("CDI", answer)
        self.assertNotIn("horaires", answer.lower())
        self.assertNotIn("Copie de contrat", answer)

        full = pure_ai_answer("quel type de contrat de travail", self.emp_user)
        self.assertIn("CDI", full)
        self.assertNotIn("horaires de travail", full.lower())

