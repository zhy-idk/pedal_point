"""
Rename images in the “product pics” directory sequentially (oldest → newest).
"""

import os
import uuid
from datetime import datetime

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rename images in a directory to 1.ext, 2.ext, ... based on oldest creation time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--directory",
            type=str,
            default="product pics",
            help='Directory containing images (default: "product pics")',
        )
        parser.add_argument(
            "--start",
            type=int,
            default=1,
            help="Starting number for filenames (default: 1)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the planned renames without applying them",
        )

    def handle(self, *args, **options):
        directory = options["directory"]
        start = options["start"]
        dry_run = options["dry_run"]

        resolved_dir = os.path.abspath(directory)
        if not os.path.isdir(resolved_dir):
            self.stdout.write(self.style.ERROR(f"Directory not found: {resolved_dir}"))
            return

        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        files = []

        for entry in os.listdir(resolved_dir):
            full_path = os.path.join(resolved_dir, entry)
            if not os.path.isfile(full_path):
                continue
            ext = os.path.splitext(entry)[1].lower()
            if ext not in allowed_extensions:
                continue
            try:
                modified = os.path.getmtime(full_path)
            except OSError:
                modified = None
            files.append((full_path, ext, modified))

        if not files:
            self.stdout.write(
                self.style.WARNING(f"No image files found in {resolved_dir}")
            )
            return

        files.sort(key=lambda item: (item[2] or 0, item[0]))

        self.stdout.write(self.style.SUCCESS(f"Found {len(files)} images"))
        operations = []
        for index, (old_path, ext, modified) in enumerate(files, start=start):
            new_name = f"{index}{ext}"
            new_path = os.path.join(resolved_dir, new_name)
            modified_str = (
                datetime.fromtimestamp(modified).isoformat(sep=" ")
                if modified
                else "unknown"
            )
            operations.append((old_path, new_path, modified_str))
            self.stdout.write(f"{os.path.basename(old_path)} -> {new_name} ({modified_str})")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run enabled, no files renamed."))
            return

        # First pass: rename to temporary unique filenames to avoid collisions
        temp_operations = []
        for old_path, new_path, _ in operations:
            if old_path == new_path:
                temp_operations.append((old_path, new_path))
                continue
            temp_name = f".tmp_{uuid.uuid4().hex}{os.path.splitext(new_path)[1]}"
            temp_path = os.path.join(os.path.dirname(old_path), temp_name)
            os.rename(old_path, temp_path)
            temp_operations.append((temp_path, new_path))

        # Second pass: rename temps to final names
        for temp_path, final_path in temp_operations:
            if temp_path == final_path:
                continue
            if os.path.exists(final_path):
                self.stdout.write(
                    self.style.WARNING(
                        f"Destination already exists, overwriting: {final_path}"
                    )
                )
                os.remove(final_path)
            os.rename(temp_path, final_path)

        self.stdout.write(self.style.SUCCESS("Renaming completed successfully."))

