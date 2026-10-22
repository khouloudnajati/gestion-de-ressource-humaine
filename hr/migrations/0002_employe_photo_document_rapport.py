import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("hr", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="employee", name="photo", field=models.ImageField(blank=True, null=True, upload_to="employees/")),
        migrations.CreateModel(name="RHDocument", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("title", models.CharField(max_length=180)), ("file", models.FileField(upload_to="rh_documents/")), ("description", models.TextField(blank=True)), ("uploaded_at", models.DateTimeField(auto_now_add=True)), ("active", models.BooleanField(default=True))]),
        migrations.CreateModel(name="Report", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("title", models.CharField(default="Rapport RH", max_length=180)), ("summary", models.TextField()), ("recommendations", models.TextField(blank=True)), ("metrics", models.JSONField(default=dict)), ("created_at", models.DateTimeField(auto_now_add=True)), ("pdf", models.FileField(blank=True, null=True, upload_to="reports/")), ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL))], options={"ordering": ["-created_at"]}),
    ]
