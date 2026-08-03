from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0004_expand_player_username"),
    ]

    operations = [
        migrations.AddField(
            model_name="roomplayer",
            name="private_notes",
            field=models.TextField(blank=True, max_length=600),
        ),
    ]
