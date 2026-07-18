from django.urls import path

from .views import (
    game, health, home, logout_view, room_history, room_history_api,
    room_lobby_api, room_player, room_player_api, room_portal, room_start_api,
    room_sync_api, roles_guide, set_language, welcome,
)

urlpatterns = [
    path("health/", health, name="health"),
    path("", home, name="home"),
    path("roles/", roles_guide, name="roles_guide"),
    path("room/", room_portal, name="room_portal"),
    path("room/<str:code>/", room_player, name="room_player"),
    path("room/<str:code>/historique/", room_history, name="room_history"),
    path("api/rooms/<str:code>/lobby/", room_lobby_api, name="room_lobby_api"),
    path("api/rooms/<str:code>/start/", room_start_api, name="room_start_api"),
    path("api/rooms/<str:code>/sync/", room_sync_api, name="room_sync_api"),
    path("api/rooms/<str:code>/player/", room_player_api, name="room_player_api"),
    path("api/rooms/<str:code>/history/", room_history_api, name="room_history_api"),
    path("accueil/", welcome, name="welcome"),
    path("partie/", game, name="game"),
    path("deconnexion/", logout_view, name="logout"),
    path("langue/", set_language, name="set_language"),
]
