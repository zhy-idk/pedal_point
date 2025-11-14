"""
Management command to add Trail Premium (₱75,000+) products for bike builder.
Creates a complete set of components: frame, wheels, drivetrain, brakes, handlebars, saddle.
"""

from django.core.management.base import BaseCommand
from api.models import (
    ProductListing,
    Product,
    ProductCategory,
    Brands,
    BikeCompatibilityTag,
)
from decimal import Decimal


class Command(BaseCommand):
    help = 'Add Trail Premium products for bike builder (₱75,000+)'

    def handle(self, *args, **kwargs):
        self.stdout.write('Adding Trail Premium products for bike builder...\n')

        # Get or create brands
        brands = {}
        for brand_name in ['Trek', 'SRAM', 'Specialized']:
            brand, _ = Brands.objects.get_or_create(name=brand_name)
            brands[brand_name] = brand

        # Get compatibility tags
        tags = {}
        tag_values = {
            'use_case': ['trail'],
            'budget': ['premium'],
            'physical': ['wheel_29', 'disc_brake', 'material_carbon', 'handlebar_flat', 'saddle_performance'],
        }
        
        for tag_type, values in tag_values.items():
            for value in values:
                try:
                    tag = BikeCompatibilityTag.objects.get(tag_type=tag_type, value=value)
                    tags[value] = tag
                except BikeCompatibilityTag.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠ Tag not found: {tag_type}/{value}')
                    )

        # Get component categories
        components_category, _ = ProductCategory.objects.get_or_create(
            slug='components',
            defaults={'name': 'Components', 'is_component': False}
        )

        categories = {}
        for cat_slug, cat_name, builder_cat in [
            ('frames', 'Frames', 'frame'),
            ('wheels', 'Wheels', 'wheels'),
            ('drivetrain', 'Drivetrain', 'drivetrain'),
            ('brakes', 'Brakes', 'brakes'),
            ('handlebars', 'Handlebars', 'handlebars'),
            ('saddles', 'Saddles', 'saddle'),
        ]:
            cat, _ = ProductCategory.objects.get_or_create(
                slug=cat_slug,
                defaults={
                    'name': cat_name,
                    'parent': components_category,
                    'is_component': True,
                    'component_type': builder_cat,
                }
            )
            categories[builder_cat] = cat

        # Product definitions for Trail Premium build
        products_data = [
            {
                'name': 'Mountain Master Carbon Frame',
                'description': 'Top-of-the-line carbon fiber frame for serious trail riders. Full suspension ready.',
                'category': 'frame',
                'brand': brands['Trek'],
                'price': Decimal('64999.00'),
                'priority': 5,
                'tags': [tags.get('trail'), tags.get('premium'), tags.get('material_carbon'), tags.get('wheel_29'), tags.get('disc_brake')],
                'variants': [
                    ('Medium', 1, Decimal('64999.00')),
                    ('Large', 1, Decimal('64999.00')),
                ],
            },
            {
                'name': 'Carbon Trail Wheels 29"',
                'description': 'Premium carbon wheelset for aggressive trail riding.',
                'category': 'wheels',
                'brand': brands['Specialized'],
                'price': Decimal('44999.00'),
                'priority': 5,
                'tags': [tags.get('trail'), tags.get('premium'), tags.get('wheel_29'), tags.get('disc_brake')],
                'variants': [('Black', 2, Decimal('44999.00'))],
            },
            {
                'name': 'SRAM GX Eagle 12-Speed',
                'description': 'Premium 1x12 drivetrain for serious trail riding.',
                'category': 'drivetrain',
                'brand': brands['SRAM'],
                'price': Decimal('34999.00'),
                'priority': 5,
                'tags': [tags.get('trail'), tags.get('premium')],
                'variants': [('Standard', 2, Decimal('34999.00'))],
            },
            {
                'name': 'Premium Hydraulic Disc Brakes MTB',
                'description': 'Top-tier hydraulic disc brakes with maximum stopping power.',
                'category': 'brakes',
                'brand': brands['SRAM'],
                'price': Decimal('19999.00'),
                'priority': 5,
                'tags': [tags.get('trail'), tags.get('premium'), tags.get('disc_brake'), tags.get('hydraulic_disc')],
                'variants': [('Standard', 2, Decimal('19999.00'))],
            },
            {
                'name': 'Carbon Riser Bars',
                'description': 'Lightweight carbon handlebars with rise.',
                'category': 'handlebars',
                'brand': brands['Specialized'],
                'price': Decimal('7499.00'),
                'priority': 5,
                'tags': [tags.get('trail'), tags.get('premium'), tags.get('handlebar_flat')],
                'variants': [('780mm', 2, Decimal('7499.00'))],
            },
            {
                'name': 'Elite Performance Saddle',
                'description': 'Ultra-lightweight carbon-railed saddle for competitive trail riding.',
                'category': 'saddle',
                'brand': brands['Specialized'],
                'price': Decimal('12999.00'),
                'priority': 5,
                'tags': [tags.get('trail'), tags.get('premium'), tags.get('saddle_performance')],
                'variants': [('Black', 2, Decimal('12999.00'))],
            },
        ]

        created_count = 0
        skipped_count = 0

        for product_data in products_data:
            # Filter out None tags
            product_tags = [tag for tag in product_data['tags'] if tag is not None]
            
            listing, created = ProductListing.objects.get_or_create(
                name=product_data['name'],
                defaults={
                    'price': product_data['price'],
                    'description': product_data['description'],
                    'category': categories[product_data['category']],
                    'available': True,
                    'bike_builder_enabled': True,
                    'builder_category': product_data['category'],
                    'builder_priority': product_data['priority'],
                }
            )

            if created:
                # Set compatibility tags
                listing.compatibility_tags.set(product_tags)

                # Create product variants
                for variant_name, stock, price in product_data['variants']:
                    Product.objects.create(
                        product_listing=listing,
                        name=product_data['name'],
                        variant_attribute=variant_name,
                        brand=product_data['brand'],
                        sku=f"{product_data['category'].upper()}-TRAIL-PREM-{variant_name.replace(' ', '-').upper()}",
                        price=price,
                        stock=stock,
                        available=True,
                    )

                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ Created: {product_data["name"]}')
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f'  - Skipped (exists): {product_data["name"]}')
                )

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Created {created_count} product listings')
        )
        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(f'- Skipped {skipped_count} existing listings')
            )
        self.stdout.write('\nTrail Premium products added successfully!')
        self.stdout.write('=' * 70)

