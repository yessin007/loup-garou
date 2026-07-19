import secrets
import uuid

from django.db import models


ROOM_ALPHABET = "0123456789"


def generate_room_code():
    while True:
        code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(6))
        if not GameRoom.objects.filter(code=code).exists():
            return code


class GameRoom(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"

    code = models.CharField(primary_key=True, max_length=6, default=generate_room_code, editable=False)
    player_count = models.PositiveSmallIntegerField()
    composition = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING)
    game_state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code


class RoomPlayer(models.Model):
    room = models.ForeignKey(GameRoom, related_name="room_players", on_delete=models.CASCADE)
    name = models.CharField(max_length=40)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    role = models.CharField(max_length=40, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["room", "name"], name="unique_room_player_name"),
        ]

    def __str__(self):
        return f"{self.name} · {self.room_id}"


class RoomEvent(models.Model):
    room = models.ForeignKey(GameRoom, related_name="events", on_delete=models.CASCADE)
    marker = models.CharField(max_length=40)
    event_type = models.CharField(max_length=12)
    round_number = models.PositiveSmallIntegerField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["room", "marker"], name="unique_room_event_marker"),
        ]

    def __str__(self):
        return f"{self.room_id} · {self.event_type} {self.round_number}"
