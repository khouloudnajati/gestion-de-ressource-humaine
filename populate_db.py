import os
import django
from datetime import date, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User
from hr.models import Department, Employee, Contract, Training, TrainingEnrollment, Evaluation, TeamSchedule, Payslip, Profile

def populate():
    print("Début du peuplement de la base de données...")

    # 1. Vérification / Création des Départements
    departments_data = [
        {"name": "Direction Générale", "manager": "M. Alami", "description": "Direction générale de l'entreprise laitière."},
        {"name": "Direction des Ressources Humaines", "manager": "Mme. Benkirane", "description": "Gestion du personnel et du recrutement."},
        {"name": "Département Production", "manager": "M. Tazi", "description": "Production de lait pasteurisé, yaourts et fromages."},
        {"name": "Département Qualité", "manager": "Mme. Bensouda", "description": "Contrôle bactériologique et conformité aux normes sanitaires."},
        {"name": "Département Maintenance", "manager": "M. Jabri", "description": "Maintenance préventive et corrective des machines industrielles."},
        {"name": "Département Logistique", "manager": "M. Mansouri", "description": "Gestion des stocks de matières premières et distribution."},
        {"name": "Département Commercial", "manager": "Mme. Filali", "description": "Ventes et relations avec les distributeurs."},
        {"name": "Département Financier", "manager": "M. Kadiri", "description": "Comptabilité, facturation et gestion budgétaire."},
    ]

    depts = {}
    for data in departments_data:
        dept, created = Department.objects.get_or_create(name=data["name"], defaults={
            "manager": data["manager"],
            "description": data["description"]
        })
        depts[data["name"]] = dept
        if created:
            print(f"Département créé : {dept.name}")

    # 2. Mise à jour des employés existants pour correspondre à des rôles réalistes
    # Rachid (rachid)
    try:
        e1 = Employee.objects.get(pk=1)
        e1.position = "Opérateur de Production Laitière"
        e1.department = depts["Département Production"]
        e1.phone = "0612345678"
        e1.save()
        print("Employé 1 (Rachid) mis à jour.")
    except Employee.DoesNotExist:
        print("Employé 1 introuvable.")

    # Rachida (khoulouddnajati)
    try:
        e2 = Employee.objects.get(pk=2)
        e2.position = "Technicienne Contrôle Qualité"
        e2.department = depts["Département Qualité"]
        e2.phone = "0676543210"
        e2.save()
        print("Employé 2 (Rachida) mis à jour.")
    except Employee.DoesNotExist:
        print("Employé 2 introuvable.")

    # Rachida (khouloudnajati)
    try:
        e3 = Employee.objects.get(pk=3)
        e3.position = "Technicienne Logistique"
        e3.department = depts["Département Logistique"]
        e3.phone = "0666778899"
        e3.save()
        print("Employé 3 (Rachida) mis à jour.")
    except Employee.DoesNotExist:
        print("Employé 3 introuvable.")

    # RH (rh)
    try:
        e4 = Employee.objects.get(pk=4)
        e4.position = "Responsable Ressources Humaines"
        e4.department = depts["Direction des Ressources Humaines"]
        e4.phone = "0655443322"
        e4.save()
        print("Employé 4 (RH) mis à jour.")
    except Employee.DoesNotExist:
        print("Employé 4 introuvable.")

    employees = list(Employee.objects.all())

    # 3. Création des dossiers médias requis pour les fichiers
    os.makedirs("media/contracts", exist_ok=True)
    os.makedirs("media/payslips", exist_ok=True)

    # 4. Création des contrats de travail
    Contract.objects.all().delete()
    print("Anciens contrats supprimés.")

    # Création de fichiers contrats de démo
    for emp in employees:
        filename = f"media/contracts/contrat_{emp.first_name}_{emp.last_name}.pdf"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"CONTRAT DE TRAVAIL - PEOPLEFLOW\n\nEmployé : {emp.first_name} {emp.last_name}\nMatricule : {emp.employee_id}\nPoste : {emp.position}\nDépartement : {emp.department.name}\n\nFait en double exemplaire à Casablanca.")
        
        # Création de l'enregistrement dans la base
        c = Contract.objects.create(
            employee=emp,
            contract_type=Contract.Type.CDI if emp.pk != 2 else Contract.Type.CDD,
            start_date=emp.hire_date - timedelta(days=30) if emp.hire_date else date(2025, 1, 1),
            file=f"contracts/contrat_{emp.first_name}_{emp.last_name}.pdf",
            status=Contract.Status.ACTIVE,
            notes=f"Contrat de travail initial signé pour le poste de {emp.position}."
        )
        print(f"Contrat créé pour : {emp}")

    # Pour l'employé 2 (Rachida), on crée aussi un ancien contrat de stage expiré
    emp_rachida = Employee.objects.filter(pk=2).first()
    if emp_rachida:
        with open("media/contracts/contrat_stage_rachida.pdf", "w", encoding="utf-8") as f:
            f.write("CONTRAT DE STAGE - PEOPLEFLOW\n\nStagiaire : Rachida\nDurée : 3 mois.")
        Contract.objects.create(
            employee=emp_rachida,
            contract_type=Contract.Type.STAGE,
            start_date=date(2025, 3, 1),
            end_date=date(2025, 5, 31),
            file="contracts/contrat_stage_rachida.pdf",
            status=Contract.Status.EXPIRED,
            notes="Stage de fin d'études validé avec succès."
        )
        print("Contrat de stage expiré créé pour Rachida (2).")

    # 5. Création des formations
    Training.objects.all().delete()
    print("Anciennes formations supprimées.")

    t1 = Training.objects.create(
        title="Sécurité et Hygiène en Industrie Laitière",
        description="Formation obligatoire sur l'utilisation des équipements de protection individuelle (EPI) et le respect des normes sanitaires d'hygiène laitière.",
        trainer="M. Reda Bennani",
        department=depts["Département Production"],
        start_date=date.today() + timedelta(days=15),
        end_date=date.today() + timedelta(days=17),
        max_participants=10
    )
    t2 = Training.objects.create(
        title="Contrôle HACCP et Qualité Microbiologique",
        description="Introduction approfondie à la méthode HACCP pour les techniciens et responsables qualité en agroalimentaire.",
        trainer="Dr. Amina Filali",
        department=depts["Département Qualité"],
        start_date=date.today() + timedelta(days=25),
        end_date=date.today() + timedelta(days=28),
        max_participants=8
    )
    t3 = Training.objects.create(
        title="Optimisation de la Chaîne Logistique Froid",
        description="Gestion opérationnelle du transport frigorifique et de la conservation des produits laitiers.",
        trainer="M. Karim Alami",
        department=depts["Département Logistique"],
        start_date=date.today() - timedelta(days=10),
        end_date=date.today() - timedelta(days=8),
        max_participants=12
    )
    print("Formations créées.")

    # 6. Inscriptions aux formations
    TrainingEnrollment.objects.all().delete()
    for emp in employees:
        if emp.pk == 1:
            TrainingEnrollment.objects.create(training=t1, employee=emp, status=TrainingEnrollment.Status.REGISTERED)
        elif emp.pk == 2:
            TrainingEnrollment.objects.create(training=t2, employee=emp, status=TrainingEnrollment.Status.REGISTERED)
            TrainingEnrollment.objects.create(training=t1, employee=emp, status=TrainingEnrollment.Status.REGISTERED)
        elif emp.pk == 3:
            TrainingEnrollment.objects.create(training=t3, employee=emp, status=TrainingEnrollment.Status.COMPLETED)
    print("Inscriptions créées.")

    # 7. Création des évaluations
    Evaluation.objects.all().delete()
    print("Anciennes évaluations supprimées.")

    admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

    eval_data = [
        {"emp_id": 1, "period": "T1 2026", "score": 15, "strengths": "Rigueur exemplaire dans l'exécution de ses tâches en production. Excellent esprit d'équipe.", "improvements": "Peut encore s'améliorer sur l'utilisation du nouveau panneau de contrôle automatisé."},
        {"emp_id": 2, "period": "T1 2026", "score": 18, "strengths": "Excellente analyse critique des échantillons bactériologiques. Très proactive pour proposer des solutions d'amélioration de la qualité.", "improvements": "Doit veiller à documenter plus régulièrement ses procédures internes."},
        {"emp_id": 3, "period": "Année 2025", "score": 16, "strengths": "Excellente réactivité face aux retards de livraison. Très bon relationnel avec les transporteurs.", "improvements": "Optimiser le reporting hebdomadaire des indicateurs clés logistiques."},
        {"emp_id": 4, "period": "Année 2025", "score": 17, "strengths": "Leadership naturel. Très bonne structuration des nouveaux modules de l'application RH.", "improvements": "Améliorer la délégation de certaines tâches opérationnelles."},
    ]

    for data in eval_data:
        emp = Employee.objects.filter(pk=data["emp_id"]).first()
        if emp:
            Evaluation.objects.create(
                employee=emp,
                evaluator=admin_user,
                period=data["period"],
                score=data["score"],
                strengths=data["strengths"],
                improvements=data["improvements"]
            )
            print(f"Évaluation créée pour : {emp}")

    # 8. Création du planning des shifts pour la semaine en cours
    TeamSchedule.objects.all().delete()
    print("Anciens shifts supprimés.")

    # Calcul de la semaine en cours (Lundi à Dimanche)
    today_date = date.today()
    start_of_week = today_date - timedelta(days=today_date.weekday())

    shifts_cycle = [
        TeamSchedule.Shift.MORNING,
        TeamSchedule.Shift.AFTERNOON,
        TeamSchedule.Shift.NIGHT,
        TeamSchedule.Shift.REST,
    ]

    for i in range(7):
        work_day = start_of_week + timedelta(days=i)
        for idx, emp in enumerate(employees):
            # Assigne un shift différent à chaque employé pour faire tourner le planning
            shift_idx = (idx + i) % len(shifts_cycle)
            TeamSchedule.objects.create(
                employee=emp,
                work_date=work_day,
                shift=shifts_cycle[shift_idx],
                notes="Shift planifié standard." if shifts_cycle[shift_idx] != TeamSchedule.Shift.REST else "Repos hebdomadaire."
            )
    print("Planning des shifts créé pour la semaine en cours.")

    # 9. Création des fiches de paie pour 2026 (Janvier à Juin)
    Payslip.objects.all().delete()
    print("Anciennes fiches de paie supprimées.")

    for m in range(1, 7):
        for idx, emp in enumerate(employees):
            # Salaires fictifs de base
            base_gross = 8500.00 + (idx * 500)
            base_net = base_gross * 0.85 # ~15% de charges

            filename = f"media/payslips/bulletin_{emp.first_name}_{emp.last_name}_{m:02d}_2026.pdf"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"BULLETIN DE PAIE - PEOPLEFLOW\n\nPériode : {m:02d}/2026\nEmployé : {emp.first_name} {emp.last_name}\nMatricule : {emp.employee_id}\nSalaire brut : {base_gross:.2f} MAD\nSalaire net : {base_net:.2f} MAD\n\nFait à Casablanca.")

            Payslip.objects.create(
                employee=emp,
                month=m,
                year=2026,
                gross_salary=base_gross,
                net_salary=base_net,
                file=f"payslips/bulletin_{emp.first_name}_{emp.last_name}_{m:02d}_2026.pdf"
            )
        print(f"Bulletins de paie du mois {m:02d}/2026 créés pour tous les employés.")

    print("\nPeuplement de la base de données terminé avec succès !")

if __name__ == "__main__":
    populate()
