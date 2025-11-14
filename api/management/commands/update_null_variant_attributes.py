"""
Management command to update all null variant_attribute values to "none".
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Product


class Command(BaseCommand):
    help = 'Updates all null variant_attribute values to "none"'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        # Count products with null variant_attribute
        null_count = Product.objects.filter(variant_attribute__isnull=True).count()

        if null_count == 0:
            self.stdout.write(
                self.style.SUCCESS('No products found with null variant_attribute.')
            )
            return

        self.stdout.write(
            f'Found {null_count} products with null variant_attribute.'
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made.')
            )
            self.stdout.write(
                f'Would update {null_count} products to set variant_attribute = "none"'
            )
            return

        # Perform the update
        with transaction.atomic():
            try:
                updated_count = Product.objects.filter(
                    variant_attribute__isnull=True
                ).update(variant_attribute="none")

                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully updated {updated_count} products. '
                        f'Set variant_attribute to "none" for all previously null values.'
                    )
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error updating products: {str(e)}')
                )
                raise
