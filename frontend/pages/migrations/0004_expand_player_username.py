from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0003_remove_legacy_admin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="roomplayer",
            name="name",
            field=models.CharField(max_length=150),
        ),
    ]
