"""Copy every record from one database to the (empty) database in DATABASE_URL.

Used once when moving the local demo from SQLite to PostgreSQL, so records typed in during testing are kept:

    python manage.py copy_data --source sqlite:///db.sqlite3

The target must already be migrated and must be empty (no institutions yet). Uploaded files in media/ are not
touched; they stay where they are and the copied records still point at them.
"""
import os
import tempfile

import dj_database_url
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from core.models import Tenant, User

# Rebuilt by migrate on the target; copying them would clash with the rows migrate already made.
EXCLUDE = ["contenttypes", "auth.permission", "admin.logentry", "sessions", "token_blacklist"]


class Command(BaseCommand):
    help = "Copy all data from --source (e.g. sqlite:///db.sqlite3) into the database in DATABASE_URL."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, help="Database URL to copy from.")

    def handle(self, *args, source, **opts):
        if Tenant.objects.exists() or User.objects.exists():
            raise CommandError("The target database already has data. Copy only into a new, empty database.")
        connections.databases["source"] = {**connections.databases["default"], **dj_database_url.parse(source),
                                           "ATOMIC_REQUESTS": False}
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.stdout.write("Reading records from the old database...")
            # Written as UTF-8 explicitly: on Windows the default file encoding cannot hold every name.
            with open(path, "w", encoding="utf-8") as out:
                call_command("dumpdata", database="source", exclude=EXCLUDE, natural_foreign=True, stdout=out,
                             verbosity=0)
            self.stdout.write("Writing them into the new database...")
            call_command("loaddata", path, verbosity=0)
        finally:
            connections["source"].close()
            os.remove(path)
        self.stdout.write(self.style.SUCCESS(
            f"Copied: {Tenant.objects.count()} institutions, {User.objects.count()} user accounts."))
