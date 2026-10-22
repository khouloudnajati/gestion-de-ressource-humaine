from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0006_seed_departments"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaverequest",
            name="leave_type",
            field=models.CharField(
                choices=[
                    ("ANNUAL", "Congé annuel"),
                    ("SICK", "Congé maladie"),
                    ("UNPAID", "Congé sans solde"),
                    ("MATERNITY", "Congé maternité"),
                    ("OTHER", "Autre"),
                ],
                default="ANNUAL",
                max_length=12,
                verbose_name="type de congé",
            ),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "En attente"),
                    ("APPROVED", "Acceptée"),
                    ("REJECTED", "Refusée"),
                    ("CANCELLED", "Annulée"),
                ],
                default="PENDING",
                max_length=10,
            ),
        ),
    ]
