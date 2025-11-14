"""
Management command to add Trail Budget (₱15,000 - ₱24,000) products for bike builder.
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
    help = 'Add Trail Budget products for bike builder (₱15,000 - ₱24,000)'

    def handle(self, *args, **kwargs):
        self.stdout.write('Adding Trail Budget products for bike builder...\n')

        # Get or create brands
        brands = {}
        for brand_name in ['Specialized', 'Shimano', 'Giant']:
            brand, _ = Brands.objects.get_or_create(name=brand_name)
            brands[brand_name] = brand

        # Get compatibility tags
        tags = {}
        tag_values = {
            'use_case': ['trail'],
            'budget': ['budget'],
            'physical': ['wheel_27_5', 'wheel_29', 'disc_brake', 'material_aluminum', 'handlebar_flat', 'saddle_sport'],
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

        # Product definitions for Trail Budget build
        products_data = [
            {
                'name': 'Trail Blazer Aluminum Frame',
                'description': 'Durable aluminum hardtail frame for trail riding adventures.',
                'category': 'frame',
                'brand': brands['Specialized'],
                'price': Decimal('7500.00'),
                'priority': 10,
                'tags': [tags.get('trail'), tags.get('budget'), tags.get('material_aluminum'), tags.get('wheel_27_5'), tags.get('disc_brake')],
                'variants': [
                    ('Small', 1, Decimal('7500.00')),
                    ('Medium', 2, Decimal('7500.00')),
                    ('Large', 2, Decimal('7500.00')),
                ],
            },
            {
                'name': 'Trail Tough Wheels 27.5"',
                'description': 'Durable wheelset built for trail abuse.',
                'category': 'wheels',
                'brand': brands['Shimano'],
                'price': Decimal('5500.00'),
                'priority': 10,
                'tags': [tags.get('trail'), tags.get('budget'), tags.get('wheel_27_5'), tags.get('disc_brake')],
                'variants': [('Black', 4, Decimal('5500.00'))],
            },
            {
                'name': 'Shimano Altus 8-Speed MTB',
                'description': 'Reliable mountain bike shifting for trail adventures.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'price': Decimal('3500.00'),
                'priority': 10,
                'tags': [tags.get('trail'), tags.get('budget')],
                'variants': [('Standard', 5, Decimal('3500.00'))],
            },
            {
                'name': 'Mechanical Disc Brakes MTB',
                'description': 'Cable-actuated disc brakes for trail riding.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'price': Decimal('3500.00'),
                'priority': 10,
                'tags': [tags.get('trail'), tags.get('budget'), tags.get('disc_brake'), tags.get('mechanical_disc')],
                'variants': [('Standard', 6, Decimal('3500.00'))],
            },
            {
                'name': 'Trail Flat Bars',
                'description': 'Wide flat bars for trail control.',
                'category': 'handlebars',
                'brand': brands['Specialized'],
                'price': Decimal('1500.00'),
                'priority': 10,
                'tags': [tags.get('trail'), tags.get('budget'), tags.get('handlebar_flat')],
                'variants': [
                    ('760mm', 6, Decimal('1500.00')),
                    ('800mm', 4, Decimal('1750.00')),
                ],
            },
            {
                'name': 'Trail Sport Saddle',
                'description': 'Performance saddle for trail riding.',
                'category': 'saddle',
                'brand': brands['Specialized'],
                'price': Decimal('1500.00'),
                'priority': 10,
                'tags': [tags.get('trail'), tags.get('budget'), tags.get('saddle_sport')],
                'variants': [('Black', 6, Decimal('1500.00'))],
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
                        sku=f"{product_data['category'].upper()}-TRAIL-BUDGET-{variant_name.replace(' ', '-').upper()}",
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
        self.stdout.write('\nTrail Budget products added successfully!')
        self.stdout.write('=' * 70)

