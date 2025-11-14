"""
Assign listings whose names match "Bike #" to the Bikes category.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import ProductListing, ProductCategory


class Command(BaseCommand):
    help = 'Assign listings named "Bike #" to the Bikes category (slug: bikes).'

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show planned updates without saving changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        try:
            bikes_category = ProductCategory.objects.get(slug="bikes")
        except ProductCategory.DoesNotExist:
            self.stdout.write(self.style.ERROR('Category with slug "bikes" not found.'))
            return

        listings_qs = ProductListing.objects.filter(name__iregex=r"Bike\s*#?\s*\d+")
        total = listings_qs.count()

        if total == 0:
            self.stdout.write(self.style.WARNING('No listings matching "Bike #" found.'))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {total} matching listings."))

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            for listing in listings_qs[:10]:
                self.stdout.write(f"- {listing.name} (current category: {listing.category_id})")
            return

        updated = 0
        with transaction.atomic():
            for listing in listings_qs:
                if listing.category_id == bikes_category.id:
                    continue
                listing.category = bikes_category
                listing.save(update_fields=["category"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"Updated {updated} listing(s) to category 'Bikes'.")
        )

