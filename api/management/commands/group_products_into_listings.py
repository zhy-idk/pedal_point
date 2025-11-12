"""
Group standalone products into listings by brand + name.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Product, ProductListing, Brands


class Command(BaseCommand):
    help = (
        "Group existing products (with no listings) into ProductListing entries "
        "based on shared brand and product name."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show planned changes without modifying the database",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional limit on listing groups to process (0 = all)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        products = Product.objects.filter(product_listing__isnull=True)
        if not products.exists():
            self.stdout.write(self.style.WARNING("No standalone products found to group."))
            return

        groups = defaultdict(list)
        for product in products:
            brand_name = product.brand.name if product.brand else None
            groups[(brand_name, product.name)].append(product)

        group_keys = list(groups.keys())
        self.stdout.write(self.style.SUCCESS(f"Found {len(group_keys)} listing groups"))

        if limit and limit < len(group_keys):
            group_keys = group_keys[:limit]
            self.stdout.write(
                self.style.WARNING(f"Limiting to first {len(group_keys)} groups")
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
            for key in group_keys[:5]:
                brand, name = key
                self.stdout.write(
                    f"- {name} ({brand or 'No brand'}) -> {len(groups[key])} products"
                )
            return

        with transaction.atomic():
            listings_created = 0
            listings_reused = 0

            for brand_name, product_name in group_keys:
                variants = groups[(brand_name, product_name)]
                brand = variants[0].brand if variants and variants[0].brand else None

                min_price = min([p.price or 0 for p in variants])

                listing = (
                    ProductListing.objects.filter(name=product_name, products__brand=brand)
                    .distinct()
                    .first()
                )

                if listing:
                    listings_reused += 1
                    if listing.price is None or min_price < listing.price:
                        listing.price = min_price
                        listing.save(update_fields=["price"])
                else:
                    listing = ProductListing.objects.create(
                        name=product_name,
                        price=min_price,
                        available=True,
                    )
                    listings_created += 1

                for product in variants:
                    product.product_listing = listing
                    product.save(update_fields=["product_listing"])

                if not listing.image:
                    first_image = None
                    for product in variants:
                        first_image = product.product_images.first()
                        if first_image:
                            break
                    if first_image:
                        listing.image = first_image.image
                        listing.save(update_fields=["image"])

            self.stdout.write(self.style.SUCCESS("Listing grouping completed."))
            self.stdout.write(f"Listings created: {listings_created}")
            self.stdout.write(f"Listings reused: {listings_reused}")

