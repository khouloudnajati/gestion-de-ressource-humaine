from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import hr.models


FILIERES = [
    "Informatique / IT",
    "Finance / Comptabilité",
    "Ressources Humaines",
    "Marketing / Communication",
    "Commercial",
    "Production",
    "Qualité",
    "Logistique",
    "Maintenance",
    "Administration",
    "Autre",
]


def seed_filieres(apps, schema_editor):
    Filiere = apps.get_model("hr", "Filiere")
    for order, name in enumerate(FILIERES, start=1):
        Filiere.objects.get_or_create(name=name, defaults={"active": True, "order": order})


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("hr", "0012_remove_employee_skills_employeeskill"),
    ]

    operations = [
        migrations.CreateModel(
            name="Filiere",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True, verbose_name="filière")),
                ("active", models.BooleanField(default=True, verbose_name="active")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ordre d'affichage")),
            ],
            options={
                "verbose_name": "filière",
                "verbose_name_plural": "filières",
                "ordering": ["order", "name"],
            },
        ),
        migrations.CreateModel(
            name="CandidatureSpontanee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=100, verbose_name="nom")),
                ("prenom", models.CharField(max_length=100, verbose_name="prénom")),
                ("email", models.EmailField(max_length=254, verbose_name="e-mail")),
                ("telephone", models.CharField(max_length=30, verbose_name="téléphone")),
                ("ville", models.CharField(max_length=100, verbose_name="ville")),
                (
                    "niveau_etudes",
                    models.CharField(
                        choices=[
                            ("BAC", "Baccalauréat"),
                            ("BAC2", "Bac+2"),
                            ("BAC3", "Bac+3 / Licence"),
                            ("BAC5", "Bac+5 / Master"),
                            ("DOCTORAT", "Doctorat"),
                            ("AUTRE", "Autre"),
                        ],
                        max_length=12,
                        verbose_name="niveau d'études",
                    ),
                ),
                ("experience", models.PositiveSmallIntegerField(verbose_name="années d'expérience")),
                (
                    "type_candidature",
                    models.CharField(
                        choices=[
                            ("CDI", "CDI"),
                            ("CDD", "CDD"),
                            ("STAGE", "Stage"),
                            ("ALTERNANCE", "Alternance"),
                            ("INDIFFERENT", "Indifférent"),
                        ],
                        max_length=14,
                        verbose_name="type de candidature souhaité",
                    ),
                ),
                ("cv", models.FileField(upload_to=hr.models.candidature_cv_upload_to, verbose_name="CV (PDF)")),
                ("message", models.TextField(blank=True, verbose_name="message / lettre de motivation")),
                ("date_candidature", models.DateTimeField(auto_now_add=True, verbose_name="date de candidature")),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("NOUVELLE", "Nouvelle"),
                            ("EN_COURS", "En cours d'étude"),
                            ("RETENUE", "Retenue"),
                            ("NON_RETENUE", "Non retenue"),
                            ("ARCHIVEE", "Archivée"),
                        ],
                        default="NOUVELLE",
                        max_length=12,
                    ),
                ),
                ("date_traitement", models.DateTimeField(blank=True, null=True, verbose_name="date de traitement")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "filiere",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="candidatures",
                        to="hr.filiere",
                        verbose_name="filière",
                    ),
                ),
                (
                    "traite_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="candidatures_traitees",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="traité par",
                    ),
                ),
            ],
            options={
                "verbose_name": "candidature spontanée",
                "verbose_name_plural": "candidatures spontanées",
                "ordering": ["-date_candidature"],
            },
        ),
        migrations.RunPython(seed_filieres, migrations.RunPython.noop),
    ]
