"""
Management command to add Casual Mid-Range (₱25,000 - ₱75,000) products for bike builder.
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
    help = 'Add Casual Mid-Range products for bike builder (₱25,000 - ₱75,000)'

    def handle(self, *args, **kwargs):
        self.stdout.write('Adding Casual Mid-Range products for bike builder...\n')

        # Get or create brands
        brands = {}
        for brand_name in ['Trek', 'Shimano', 'Giant']:
            brand, _ = Brands.objects.get_or_create(name=brand_name)
            brands[brand_name] = brand

        # Get compatibility tags
        tags = {}
        tag_values = {
            'use_case': ['casual'],
            'budget': ['mid'],
            'physical': ['wheel_26', 'wheel_700c', 'disc_brake', 'material_aluminum', 'handlebar_flat', 'saddle_comfort', 'saddle_sport'],
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

        # Product definitions for Casual Mid-Range build
        products_data = [
            {
                'name': 'Leisure Pro Aluminum Frame',
                'description': 'Premium aluminum frame with relaxed geometry for comfortable recreational riding.',
                'category': 'frame',
                'brand': brands['Trek'],
                'price': Decimal('19999.00'),
                'priority': 8,
                'tags': [tags.get('casual'), tags.get('mid'), tags.get('material_aluminum'), tags.get('wheel_26'), tags.get('disc_brake')],
                'variants': [
                    ('Small', 2, Decimal('19999.00')),
                    ('Medium', 2, Decimal('19999.00')),
                    ('Large', 1, Decimal('19999.00')),
                ],
            },
            {
                'name': 'Comfort Alloy Wheels 26"',
                'description': 'Quality 26" wheelset with disc brake compatibility for casual riding.',
                'category': 'wheels',
                'brand': brands['Giant'],
                'price': Decimal('14999.00'),
                'priority': 8,
                'tags': [tags.get('casual'), tags.get('mid'), tags.get('wheel_26'), tags.get('disc_brake')],
                'variants': [('Black', 4, Decimal('14999.00'))],
            },
            {
                'name': 'Shimano Altus 8-Speed',
                'description': 'Reliable 8-speed groupset perfect for casual recreational riding.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'price': Decimal('8999.00'),
                'priority': 8,
                'tags': [tags.get('casual'), tags.get('mid')],
                'variants': [('Standard', 4, Decimal('8999.00'))],
            },
            {
                'name': 'Mechanical Disc Brakes Casual',
                'description': 'Cable-actuated disc brakes for reliable stopping power.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'price': Decimal('5999.00'),
                'priority': 8,
                'tags': [tags.get('casual'), tags.get('mid'), tags.get('disc_brake'), tags.get('mechanical_disc')],
                'variants': [('Standard', 5, Decimal('5999.00'))],
            },
            {
                'name': 'Comfort Riser Bars',
                'description': 'Ergonomic riser bars for upright comfortable riding position.',
                'category': 'handlebars',
                'brand': brands['Giant'],
                'price': Decimal('2999.00'),
                'priority': 8,
                'tags': [tags.get('casual'), tags.get('mid'), tags.get('handlebar_flat')],
                'variants': [('Standard', 6, Decimal('2999.00'))],
            },
            {
                'name': 'Premium Comfort Saddle',
                'description': 'Extra-wide comfort saddle with gel padding for long leisurely rides.',
                'category': 'saddle',
                'brand': brands['Trek'],
                'price': Decimal('3999.00'),
                'priority': 8,
                'tags': [tags.get('casual'), tags.get('mid'), tags.get('saddle_comfort')],
                'variants': [
                    ('Black', 5, Decimal('3999.00')),
                    ('Brown', 3, Decimal('3999.00')),
                ],
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
                        sku=f"{product_data['category'].upper()}-CASUAL-MID-{variant_name.replace(' ', '-').upper()}",
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
        self.stdout.write('\nCasual Mid-Range products added successfully!')
        self.stdout.write('=' * 70)

