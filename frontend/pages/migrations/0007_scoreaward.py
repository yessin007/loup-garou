import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pages", "0006_expand_private_notes"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScoreAward",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("award_key", models.CharField(max_length=140)),
                ("rule_code", models.CharField(max_length=50)),
                ("points", models.PositiveSmallIntegerField()),
                ("phase", models.CharField(blank=True, max_length=12)),
                ("round_number", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_awards", to="pages.roomplayer")),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_awards", to="pages.gameroom")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_awards", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["room__created_at", "round_number", "id"]},
        ),
        migrations.AddConstraint(
            model_name="scoreaward",
            constraint=models.UniqueConstraint(fields=("room", "player", "award_key"), name="unique_player_score_award"),
        ),
        migrations.AddConstraint(
            model_name="scoreaward",
            constraint=models.CheckConstraint(condition=models.Q(("points__gte", 1), ("points__lte", 5)), name="score_award_points_1_to_5"),
        ),
    ]
