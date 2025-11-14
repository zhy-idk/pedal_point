"""
Management command to add Trail Mid-Range (₱25,000 - ₱75,000) products for bike builder.
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
    help = 'Add Trail Mid-Range products for bike builder (₱25,000 - ₱75,000)'

    def handle(self, *args, **kwargs):
        self.stdout.write('Adding Trail Mid-Range products for bike builder...\n')

        # Get or create brands
        brands = {}
        for brand_name in ['Specialized', 'Shimano', 'Trek']:
            brand, _ = Brands.objects.get_or_create(name=brand_name)
            brands[brand_name] = brand

        # Get compatibility tags
        tags = {}
        tag_values = {
            'use_case': ['trail'],
            'budget': ['mid'],
            'physical': ['wheel_29', 'wheel_27_5', 'disc_brake', 'material_aluminum', 'material_carbon', 'handlebar_flat', 'saddle_sport'],
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

        # Product definitions for Trail Mid-Range build
        products_data = [
            {
                'name': 'Trail Pro Aluminum Frame',
                'description': 'Premium aluminum hardtail frame with modern geometry for aggressive trail riding.',
                'category': 'frame',
                'brand': brands['Specialized'],
                'price': Decimal('24999.00'),
                'priority': 8,
                'tags': [tags.get('trail'), tags.get('mid'), tags.get('material_aluminum'), tags.get('wheel_29'), tags.get('disc_brake')],
                'variants': [
                    ('Medium', 2, Decimal('24999.00')),
                    ('Large', 2, Decimal('24999.00')),
                ],
            },
            {
                'name': 'Trail Master Wheels 29"',
                'description': 'Large 29" wheelset for trail and mountain biking.',
                'category': 'wheels',
                'brand': brands['Specialized'],
                'price': Decimal('24999.00'),
                'priority': 8,
                'tags': [tags.get('trail'), tags.get('mid'), tags.get('wheel_29'), tags.get('disc_brake')],
                'variants': [('Black', 3, Decimal('24999.00'))],
            },
            {
                'name': 'Shimano Deore 10-Speed MTB',
                'description': 'Mid-range mountain bike groupset with smooth shifting.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'price': Decimal('14999.00'),
                'priority': 8,
                'tags': [tags.get('trail'), tags.get('mid')],
                'variants': [('Standard', 3, Decimal('14999.00'))],
            },
            {
                'name': 'Hydraulic Disc Brakes Trail',
                'description': 'Premium hydraulic disc brakes for mountain biking.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'price': Decimal('12499.00'),
                'priority': 8,
                'tags': [tags.get('trail'), tags.get('mid'), tags.get('disc_brake'), tags.get('hydraulic_disc')],
                'variants': [('Standard', 4, Decimal('12499.00'))],
            },
            {
                'name': 'Trail Pro Riser Bars',
                'description': 'Wide riser bars with ergonomic sweep for trail comfort.',
                'category': 'handlebars',
                'brand': brands['Specialized'],
                'price': Decimal('4999.00'),
                'priority': 8,
                'tags': [tags.get('trail'), tags.get('mid'), tags.get('handlebar_flat')],
                'variants': [('780mm', 4, Decimal('4999.00'))],
            },
            {
                'name': 'Trail Pro Saddle',
                'description': 'Premium performance saddle for serious trail riding.',
                'category': 'saddle',
                'brand': brands['Specialized'],
                'price': Decimal('3499.00'),
                'priority': 8,
                'tags': [tags.get('trail'), tags.get('mid'), tags.get('saddle_sport')],
                'variants': [('Black', 4, Decimal('3499.00'))],
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
                        sku=f"{product_data['category'].upper()}-TRAIL-MID-{variant_name.replace(' ', '-').upper()}",
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
        self.stdout.write('\nTrail Mid-Range products added successfully!')
        self.stdout.write('=' * 70)

