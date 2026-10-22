from django.db import migrations

DEPARTMENTS = [
    ("Direction Générale", "Direction de l'entreprise"),
    ("Direction des Ressources Humaines", "Service RH"),
    ("Département Production", "Unités de production laitière"),
    ("Département Qualité", "Contrôle qualité et hygiène"),
    ("Département Maintenance", "Maintenance des équipements"),
    ("Département Logistique", "Collecte et distribution"),
    ("Département Commercial", "Ventes et relation client"),
    ("Département Financier", "Comptabilité et finance"),
]


def seed_departments(apps, schema_editor):
    Department = apps.get_model("hr", "Department")
    for name, description in DEPARTMENTS:
        Department.objects.get_or_create(name=name, defaults={"description": description})


class Migration(migrations.Migration):
    dependencies = [("hr", "0005_auditlog_contract_evaluation_notification_training_and_more")]
    operations = [migrations.RunPython(seed_departments, migrations.RunPython.noop)]
