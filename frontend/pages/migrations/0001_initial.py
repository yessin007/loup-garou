import django.db.models.deletion
import pages.models
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="GameRoom",
            fields=[
                ("code", models.CharField(default=pages.models.generate_room_code, editable=False, max_length=6, primary_key=True, serialize=False)),
                ("player_count", models.PositiveSmallIntegerField()),
                ("composition", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("waiting", "Waiting"), ("active", "Active"), ("finished", "Finished")], default="waiting", max_length=12)),
                ("game_state", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="RoomPlayer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=40)),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("role", models.CharField(blank=True, max_length=40)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="room_players", to="pages.gameroom")),
            ],
            options={"ordering": ["joined_at", "id"]},
        ),
        migrations.CreateModel(
            name="RoomEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("marker", models.CharField(max_length=40)),
                ("event_type", models.CharField(max_length=12)),
                ("round_number", models.PositiveSmallIntegerField()),
                ("details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="pages.gameroom")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddConstraint(model_name="roomplayer", constraint=models.UniqueConstraint(fields=("room", "name"), name="unique_room_player_name")),
        migrations.AddConstraint(model_name="roomevent", constraint=models.UniqueConstraint(fields=("room", "marker"), name="unique_room_event_marker")),
    ]
