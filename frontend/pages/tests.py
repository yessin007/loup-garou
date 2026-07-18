import json

from django.test import Client, TestCase
from django.urls import reverse

from .models import GameRoom, RoomEvent
from .translations import ROLES


class RoomFlowTests(TestCase):
    def setUp(self):
        self.narrator = Client()
        self.narrator.post(reverse("home"), {"username": "123", "password": "123"})
        self.composition = {role: 0 for role in ROLES["fr"]}
        self.composition.update({"simple_wolves": 2, "villagers": 6})

    def create_room(self):
        response = self.narrator.post(
            reverse("welcome"),
            {"player_count": 8, **self.composition},
        )
        self.assertRedirects(response, reverse("game"), fetch_redirect_response=False)
        return GameRoom.objects.get(code=self.narrator.session["game_setup"]["room_code"])

    def test_player_joins_and_receives_role_after_narrator_starts(self):
        room = self.create_room()
        player = Client()
        response = player.post(
            reverse("room_portal"),
            {"action": "join", "room_code": room.code.lower(), "player_name": "Sarra"},
        )
        self.assertRedirects(response, reverse("room_player", args=[room.code]), fetch_redirect_response=False)

        lobby = self.narrator.get(reverse("room_lobby_api", args=[room.code])).json()
        self.assertEqual(lobby["players"][0]["name"], "Sarra")

        started = self.narrator.post(reverse("room_start_api", args=[room.code])).json()
        self.assertEqual(len(started["assignments"]), 1)
        self.assertEqual(len(started["remaining_roles"]), 7)

        private_state = player.get(reverse("room_player_api", args=[room.code])).json()
        self.assertEqual(private_state["status"], GameRoom.Status.ACTIVE)
        self.assertIsNotNone(private_state["role"])

    def test_night_and_day_history_are_created_once(self):
        room = self.create_room()
        self.narrator.post(reverse("room_start_api", args=[room.code]))
        state = {
            "stage": "dawn", "round": 1,
            "players": [{"id": 1, "name": "Ahmed", "alive": False}],
            "deaths": [1], "wolfTargetId": 1,
        }
        sync_url = reverse("room_sync_api", args=[room.code])
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")
        state.update({"stage": "day_end", "lastVote": 1, "voteOutcome": "eliminated"})
        self.narrator.post(sync_url, json.dumps(state), content_type="application/json")

        self.assertEqual(RoomEvent.objects.filter(room=room).count(), 2)
        history = Client().get(reverse("room_history_api", args=[room.code])).json()
        self.assertEqual([event["type"] for event in history["events"]], ["night", "day"])
