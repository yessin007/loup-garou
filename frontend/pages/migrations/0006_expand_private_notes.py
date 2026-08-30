from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0005_roomplayer_private_notes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="roomplayer",
            name="private_notes",
            field=models.TextField(blank=True, max_length=5000),
        ),
    ]
