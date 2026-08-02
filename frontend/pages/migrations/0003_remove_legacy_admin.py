from django.conf import settings
from django.db import migrations


def remove_legacy_admin(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    user_model = apps.get_model(app_label, model_name)
    user_model.objects.filter(username="admin").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0002_room_accounts"),
    ]

    operations = [
        migrations.RunPython(remove_legacy_admin, migrations.RunPython.noop),
    ]
