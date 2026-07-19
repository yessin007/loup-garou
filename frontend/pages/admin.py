from django.contrib import admin

from .models import GameRoom, RoomEvent, RoomPlayer


class SuperuserDeleteOnlyMixin:
    """History data can only be deleted by a Django superuser."""

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(GameRoom)
class GameRoomAdmin(SuperuserDeleteOnlyMixin, admin.ModelAdmin):
    list_display = ("code", "status", "player_count", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("code",)
    readonly_fields = ("code", "created_at", "updated_at")


@admin.register(RoomEvent)
class RoomEventAdmin(SuperuserDeleteOnlyMixin, admin.ModelAdmin):
    list_display = ("room", "event_type", "round_number", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("room__code", "marker")
    list_select_related = ("room",)
    readonly_fields = ("room", "marker", "event_type", "round_number", "details", "created_at")


@admin.register(RoomPlayer)
class RoomPlayerAdmin(SuperuserDeleteOnlyMixin, admin.ModelAdmin):
    list_display = ("name", "room", "role", "joined_at")
    search_fields = ("name", "room__code")
    list_select_related = ("room",)
    readonly_fields = ("room", "name", "token", "role", "joined_at")
