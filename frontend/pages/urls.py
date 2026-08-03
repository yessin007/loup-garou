from django.urls import path

from .views import (
    game, general_room_qr, health, home, logout_view, room_history, room_history_api, room_history_delete, room_history_finish, room_history_list,
    room_lobby_api, room_player, room_player_api, room_portal, room_reconfigure_api, room_start_api,
    room_sync_api, roles_guide, service_worker, set_language, pwa_manifest, welcome, dashboard, register, user_detail, user_management,
)

urlpatterns = [
    path("health/", health, name="health"),
    path("manifest.webmanifest", pwa_manifest, name="pwa_manifest"),
    path("sw.js", service_worker, name="service_worker"),
    path("", home, name="home"),
    path("dashboard/", dashboard, name="dashboard"),
    path("inscription/", register, name="register"),
    path("utilisateurs/", user_management, name="user_management"),
    path("utilisateurs/<int:user_id>/", user_detail, name="user_detail"),
    path("roles/", roles_guide, name="roles_guide"),
    path("room/", room_portal, name="room_portal"),
    path("room/qr-general.svg", general_room_qr, name="general_room_qr"),
    path("historique/", room_history_list, name="room_history_list"),
    path("historique/<str:code>/terminer/", room_history_finish, name="room_history_finish"),
    path("historique/<str:code>/supprimer/", room_history_delete, name="room_history_delete"),
    path("room/<str:code>/", room_player, name="room_player"),
    path("room/<str:code>/historique/", room_history, name="room_history"),
    path("api/rooms/<str:code>/lobby/", room_lobby_api, name="room_lobby_api"),
    path("api/rooms/<str:code>/reconfigure/", room_reconfigure_api, name="room_reconfigure_api"),
    path("api/rooms/<str:code>/start/", room_start_api, name="room_start_api"),
    path("api/rooms/<str:code>/sync/", room_sync_api, name="room_sync_api"),
    path("api/rooms/<str:code>/player/", room_player_api, name="room_player_api"),
    path("api/rooms/<str:code>/history/", room_history_api, name="room_history_api"),
    path("accueil/", welcome, name="welcome"),
    path("partie/", game, name="game"),
    path("deconnexion/", logout_view, name="logout"),
    path("langue/", set_language, name="set_language"),
]
