from django.core.management.base import BaseCommand
from django.db import transaction

from pages.models import GameRoom
from pages.scoring import reconcile_room_scores


class Command(BaseCommand):
    help = "Rebuild the auditable league ledger from recorded room events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Only rebuild rooms that do not have any score awards yet.",
        )

    def handle(self, *args, **options):
        rooms = GameRoom.objects.all()
        if options["missing_only"]:
            rooms = rooms.filter(score_awards__isnull=True).distinct()
        rebuilt = 0
        for room in rooms.iterator():
            with transaction.atomic():
                reconcile_room_scores(room)
            rebuilt += 1
        self.stdout.write(self.style.SUCCESS(f"League scores rebuilt for {rebuilt} room(s)."))
