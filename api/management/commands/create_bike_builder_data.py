from django.core.management.base import BaseCommand
from api.models import (
    CompatibilityGroup,
    CompatibilityAttribute,
    CompatibilityAttributeValue,
    ProductListing,
    Product,
    ProductCategory,
    Brands,
)
from decimal import Decimal


class Command(BaseCommand):
    help = 'Create mock data for bike builder system'

    def clear_existing_data(self):
        """Clear existing bike builder data to prevent duplicates"""
        self.stdout.write('Clearing existing data...')
        
        # Clear product listings that are bike builder enabled
        bike_builder_listings = ProductListing.objects.filter(bike_builder_enabled=True)
        count = bike_builder_listings.count()
        bike_builder_listings.delete()
        self.stdout.write(f'  ✓ Deleted {count} existing bike builder listings')
        
        # Clear compatibility data
        CompatibilityAttributeValue.objects.all().delete()
        self.stdout.write('  ✓ Cleared compatibility attribute values')
        
        CompatibilityAttribute.objects.all().delete()
        self.stdout.write('  ✓ Cleared compatibility attributes')
        
        CompatibilityGroup.objects.all().delete()
        self.stdout.write('  ✓ Cleared compatibility groups')
        
        # Clear component categories (but keep main categories)
        ProductCategory.objects.filter(is_component=True).delete()
        self.stdout.write('  ✓ Cleared component categories')

    def handle(self, *args, **kwargs):
        self.stdout.write('Creating bike builder mock data...\n')

        # Clear existing data first
        self.clear_existing_data()
        
        self.stdout.write('\nCreating new bike builder data...')

        # Create category hierarchy
        self.stdout.write('Creating category structure...')
        
        # Create main top-level categories
        bikes_category, _ = ProductCategory.objects.get_or_create(
            name='Bikes',
            defaults={'slug': 'bikes', 'is_component': False}
        )
        
        # Create main Components category (dropdown parent only, not a direct category)
        components_category, _ = ProductCategory.objects.get_or_create(
            name='Components',
            defaults={'slug': 'components', 'is_component': False}
        )
        
        misc_category, _ = ProductCategory.objects.get_or_create(
            name='Miscellaneous',
            defaults={'slug': 'miscellaneous', 'is_component': False}
        )
        
        # Create component subcategories under Components
        component_subcategories = {
            'frame': ProductCategory.objects.get_or_create(
                name='Frames',
                defaults={
                    'slug': 'frames',
                    'parent': components_category,
                    'is_component': True,
                    'component_type': 'frame'
                }
            )[0],
            'wheels': ProductCategory.objects.get_or_create(
                name='Wheels',
                defaults={
                    'slug': 'wheels',
                    'parent': components_category,
                    'is_component': True,
                    'component_type': 'wheels'
                }
            )[0],
            'drivetrain': ProductCategory.objects.get_or_create(
                name='Drivetrain',
                defaults={
                    'slug': 'drivetrain',
                    'parent': components_category,
                    'is_component': True,
                    'component_type': 'drivetrain'
                }
            )[0],
            'brakes': ProductCategory.objects.get_or_create(
                name='Brakes',
                defaults={
                    'slug': 'brakes',
                    'parent': components_category,
                    'is_component': True,
                    'component_type': 'brakes'
                }
            )[0],
            'handlebars': ProductCategory.objects.get_or_create(
                name='Handlebars',
                defaults={
                    'slug': 'handlebars',
                    'parent': components_category,
                    'is_component': True,
                    'component_type': 'handlebars'
                }
            )[0],
            'saddle': ProductCategory.objects.get_or_create(
                name='Saddles',
                defaults={
                    'slug': 'saddles',
                    'parent': components_category,
                    'is_component': True,
                    'component_type': 'saddle'
                }
            )[0],
        }
        
        self.stdout.write(self.style.SUCCESS('✓ Category structure created'))
        self.stdout.write(f'  - Main categories: Bikes, Components (parent), Miscellaneous')
        self.stdout.write(f'  - Component subcategories: {len(component_subcategories)} created')
        
        category = components_category  # Default for backwards compatibility

        # Create or get brands
        brands_data = ['Trek', 'Specialized', 'Giant', 'Shimano', 'SRAM']
        brands = {}
        for brand_name in brands_data:
            brand, _ = Brands.objects.get_or_create(name=brand_name)
            brands[brand_name] = brand

        # 1. Create Compatibility Groups and Attributes
        self.stdout.write('Creating compatibility system...')
        
        # Bike Type Group
        bike_type_group, _ = CompatibilityGroup.objects.get_or_create(
            name='Bike Type',
            defaults={'description': 'What type of riding is this for'}
        )
        
        bike_type_attr, _ = CompatibilityAttribute.objects.get_or_create(
            name='Usage Type',
            group=bike_type_group,
            defaults={'attribute_type': 'choice', 'is_required': True}
        )
        
        # Create bike type values
        usage_types = [
            ('city', 'City/Commute', 'Ideal for daily commuting and city streets'),
            ('trail', 'Trail/Mountain', 'Built for off-road trails and rough terrain'),
            ('casual', 'Casual/Recreation', 'Perfect for leisure rides and weekend fun'),
        ]
        
        usage_values = {}
        for value, display, desc in usage_types:
            val, _ = CompatibilityAttributeValue.objects.get_or_create(
                attribute=bike_type_attr,
                value=value,
                defaults={'display_name': display, 'description': desc}
            )
            usage_values[value] = val

        # Budget Group
        budget_group, _ = CompatibilityGroup.objects.get_or_create(
            name='Budget Range',
            defaults={'description': 'Price range for components'}
        )
        
        budget_attr, _ = CompatibilityAttribute.objects.get_or_create(
            name='Budget Level',
            group=budget_group,
            defaults={'attribute_type': 'choice', 'is_required': False}
        )
        
        budget_ranges = [
            ('budget', 'Budget (₱15,000-₱24,000)', 'Affordable options for cost-conscious buyers'),
            ('mid', 'Mid-Range (₱25,000-₱75,000)', 'Great balance of quality and price'),
            ('premium', 'Premium (₱75,000+)', 'High-end components for serious riders'),
        ]
        
        budget_values = {}
        for value, display, desc in budget_ranges:
            val, _ = CompatibilityAttributeValue.objects.get_or_create(
                attribute=budget_attr,
                value=value,
                defaults={'display_name': display, 'description': desc}
            )
            budget_values[value] = val

        # Frame Material Group
        material_group, _ = CompatibilityGroup.objects.get_or_create(
            name='Frame Material',
            defaults={'description': 'Frame construction material'}
        )
        
        material_attr, _ = CompatibilityAttribute.objects.get_or_create(
            name='Material',
            group=material_group,
            defaults={'attribute_type': 'choice', 'is_required': True}
        )
        
        materials = [
            ('aluminum', 'Aluminum', 'Lightweight and durable'),
            ('carbon', 'Carbon Fiber', 'Premium lightweight material'),
            ('steel', 'Steel', 'Classic and comfortable'),
        ]
        
        material_values = {}
        for value, display, desc in materials:
            val, _ = CompatibilityAttributeValue.objects.get_or_create(
                attribute=material_attr,
                value=value,
                defaults={'display_name': display, 'description': desc}
            )
            material_values[value] = val

        # Wheel Size Group
        wheel_group, _ = CompatibilityGroup.objects.get_or_create(
            name='Wheel Size',
            defaults={'description': 'Wheel diameter size'}
        )
        
        wheel_attr, _ = CompatibilityAttribute.objects.get_or_create(
            name='Size',
            group=wheel_group,
            defaults={'attribute_type': 'choice', 'is_required': True}
        )
        
        wheel_sizes = [
            ('26', '26 inch', 'Standard size for mountain bikes'),
            ('27.5', '27.5 inch', 'Balanced size for versatility'),
            ('29', '29 inch', 'Larger wheels for better rolling'),
            ('700c', '700c', 'Standard road bike size'),
        ]
        
        wheel_values = {}
        for value, display, desc in wheel_sizes:
            val, _ = CompatibilityAttributeValue.objects.get_or_create(
                attribute=wheel_attr,
                value=value,
                defaults={'display_name': display, 'description': desc}
            )
            wheel_values[value] = val

        # Brake Type Group
        brake_group, _ = CompatibilityGroup.objects.get_or_create(
            name='Brake Type',
            defaults={'description': 'Braking system type'}
        )
        
        brake_attr, _ = CompatibilityAttribute.objects.get_or_create(
            name='Type',
            group=brake_group,
            defaults={'attribute_type': 'choice', 'is_required': True}
        )
        
        brake_types = [
            ('disc', 'Disc Brake', 'Modern hydraulic braking'),
            ('rim', 'Rim Brake', 'Traditional caliper braking'),
        ]
        
        brake_values = {}
        for value, display, desc in brake_types:
            val, _ = CompatibilityAttributeValue.objects.get_or_create(
                attribute=brake_attr,
                value=value,
                defaults={'display_name': display, 'description': desc}
            )
            brake_values[value] = val

        self.stdout.write(self.style.SUCCESS('✓ Compatibility system created'))

        # 2. Create Product Listings
        self.stdout.write('\nCreating product listings...')

        # FRAMES - City bikes (Prices in Philippine Peso)
        frames_data = [
            # Budget City Frame
            {
                'name': 'City Cruiser Aluminum Frame',
                'price': Decimal('7499.00'),
                'description': 'Lightweight aluminum frame perfect for city commuting. Comfortable geometry for upright riding.',
                'category': 'frame',
                'brand': brands['Giant'],
                'priority': 10,
                'attributes': [usage_values['city'], budget_values['budget'], material_values['aluminum'], wheel_values['700c'], brake_values['rim']],
                'compatible_with': [wheel_values['700c'], brake_values['rim']],
                'variants': [
                    ('Small', 2, Decimal('7499.00')),
                    ('Medium', 3, Decimal('7499.00')),
                    ('Large', 2, Decimal('7499.00')),
                ]
            },
            # Mid-range City Frame
            {
                'name': 'Urban Pro Carbon Frame',
                'price': Decimal('29999.00'),
                'description': 'Premium carbon fiber frame designed for serious commuters. Disc brake compatible.',
                'category': 'frame',
                'brand': brands['Trek'],
                'priority': 8,
                'attributes': [usage_values['city'], budget_values['mid'], material_values['carbon'], wheel_values['700c'], brake_values['disc']],
                'compatible_with': [wheel_values['700c'], brake_values['disc']],
                'variants': [
                    ('Medium', 2, Decimal('29999.00')),
                    ('Large', 1, Decimal('29999.00')),
                ]
            },
            # Budget Trail Frame
            {
                'name': 'Trail Blazer Aluminum Frame',
                'price': Decimal('7500.00'),
                'description': 'Durable aluminum hardtail frame for trail riding adventures.',
                'category': 'frame',
                'brand': brands['Specialized'],
                'priority': 10,
                'attributes': [usage_values['trail'], budget_values['budget'], material_values['aluminum'], wheel_values['27.5'], brake_values['disc']],
                'compatible_with': [wheel_values['27.5'], wheel_values['29'], brake_values['disc']],
                'variants': [
                    ('Small', 1, Decimal('7500.00')),
                    ('Medium', 2, Decimal('7500.00')),
                    ('Large', 2, Decimal('7500.00')),
                ]
            },
            # Premium Trail Frame
            {
                'name': 'Mountain Master Carbon Frame',
                'price': Decimal('64999.00'),
                'description': 'Top-of-the-line carbon fiber frame for serious trail riders. Full suspension ready.',
                'category': 'frame',
                'brand': brands['Trek'],
                'priority': 5,
                'attributes': [usage_values['trail'], budget_values['premium'], material_values['carbon'], wheel_values['29'], brake_values['disc']],
                'compatible_with': [wheel_values['29'], brake_values['disc']],
                'variants': [
                    ('Medium', 1, Decimal('64999.00')),
                    ('Large', 1, Decimal('64999.00')),
                ]
            },
            # Casual Frame
            {
                'name': 'Weekend Rider Steel Frame',
                'price': Decimal('6499.00'),
                'description': 'Classic steel frame for comfortable weekend rides. Smooth and reliable.',
                'category': 'frame',
                'brand': brands['Giant'],
                'priority': 10,
                'attributes': [usage_values['casual'], budget_values['budget'], material_values['steel'], wheel_values['26'], brake_values['rim']],
                'compatible_with': [wheel_values['26'], brake_values['rim'], brake_values['disc']],
                'variants': [
                    ('Small', 3, Decimal('6499.00')),
                    ('Medium', 3, Decimal('6499.00')),
                ]
            },
        ]

        # WHEELS (Prices in Philippine Peso)
        wheels_data = [
            # Budget wheels - City
            {
                'name': 'City Alloy Wheels 700c',
                'price': Decimal('4499.00'),
                'description': 'Reliable alloy wheelset for city commuting.',
                'category': 'wheels',
                'brand': brands['Shimano'],
                'priority': 10,
                'attributes': [usage_values['city'], budget_values['budget'], wheel_values['700c'], brake_values['rim']],
                'compatible_with': [brake_values['rim']],
                'variants': [('Black', 5, Decimal('4499.00'))],
            },
            # Budget wheels - Trail
            {
                'name': 'Trail Tough Wheels 27.5"',
                'price': Decimal('5500.00'),
                'description': 'Durable wheelset built for trail abuse.',
                'category': 'wheels',
                'brand': brands['Shimano'],
                'priority': 10,
                'attributes': [usage_values['trail'], budget_values['budget'], wheel_values['27.5'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Black', 4, Decimal('5500.00'))],
            },
            # Budget wheels - Casual (26")
            {
                'name': 'Casual Comfort Wheels 26"',
                'price': Decimal('4499.00'),
                'description': 'Comfortable 26" wheelset for casual riding.',
                'category': 'wheels',
                'brand': brands['Giant'],
                'priority': 10,
                'attributes': [usage_values['casual'], budget_values['budget'], wheel_values['26'], brake_values['rim']],
                'compatible_with': [brake_values['rim'], brake_values['disc']],
                'variants': [('Black', 5, Decimal('4499.00'))],
            },
            # Mid-range wheels - City with disc
            {
                'name': 'Urban Disc Wheels 700c',
                'price': Decimal('19999.00'),
                'description': 'Quality 700c wheelset with disc brake mounts.',
                'category': 'wheels',
                'brand': brands['Shimano'],
                'priority': 8,
                'attributes': [usage_values['city'], budget_values['mid'], wheel_values['700c'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Black', 3, Decimal('19999.00'))],
            },
            # Mid-range wheels - Trail 29"
            {
                'name': 'Trail Master Wheels 29"',
                'price': Decimal('24999.00'),
                'description': 'Large 29" wheelset for trail and mountain biking.',
                'category': 'wheels',
                'brand': brands['Specialized'],
                'priority': 8,
                'attributes': [usage_values['trail'], budget_values['mid'], wheel_values['29'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Black', 3, Decimal('24999.00'))],
            },
            # Premium wheels
            {
                'name': 'Carbon Aero Wheels 700c',
                'price': Decimal('39999.00'),
                'description': 'Lightweight carbon wheelset with disc brake compatibility.',
                'category': 'wheels',
                'brand': brands['Specialized'],
                'priority': 5,
                'attributes': [usage_values['city'], budget_values['premium'], wheel_values['700c'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Black', 2, Decimal('39999.00'))],
            },
        ]

        # DRIVETRAINS (Prices in Philippine Peso)
        drivetrain_data = [
            # Budget - City
            {
                'name': 'Shimano Tourney 7-Speed',
                'price': Decimal('3500.00'),
                'description': 'Entry-level reliable shifting system for city commuting.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'priority': 10,
                'attributes': [usage_values['city'], usage_values['casual'], budget_values['budget']],
                'compatible_with': [],
                'variants': [('Standard', 6, Decimal('3500.00'))],
            },
            # Budget - Trail
            {
                'name': 'Shimano Altus 8-Speed MTB',
                'price': Decimal('3500.00'),
                'description': 'Reliable mountain bike shifting for trail adventures.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'priority': 10,
                'attributes': [usage_values['trail'], budget_values['budget']],
                'compatible_with': [],
                'variants': [('Standard', 5, Decimal('3500.00'))],
            },
            # Mid-Range - City
            {
                'name': 'Shimano Sora 9-Speed',
                'price': Decimal('14999.00'),
                'description': 'Smooth road-oriented groupset for city riding.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'priority': 8,
                'attributes': [usage_values['city'], budget_values['mid']],
                'compatible_with': [],
                'variants': [('Standard', 3, Decimal('14999.00'))],
            },
            # Mid-Range - Trail
            {
                'name': 'Shimano Deore 10-Speed MTB',
                'price': Decimal('14999.00'),
                'description': 'Mid-range mountain bike groupset with smooth shifting.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'priority': 8,
                'attributes': [usage_values['trail'], budget_values['mid']],
                'compatible_with': [],
                'variants': [('Standard', 3, Decimal('14999.00'))],
            },
            # Premium - Trail
            {
                'name': 'SRAM GX Eagle 12-Speed',
                'price': Decimal('34999.00'),
                'description': 'Premium 1x12 drivetrain for serious trail riding.',
                'category': 'drivetrain',
                'brand': brands['SRAM'],
                'priority': 5,
                'attributes': [usage_values['trail'], budget_values['premium']],
                'compatible_with': [],
                'variants': [('Standard', 2, Decimal('34999.00'))],
            },
            # Premium - City
            {
                'name': 'Shimano Ultegra 11-Speed',
                'price': Decimal('39999.00'),
                'description': 'High-performance road groupset for urban performance.',
                'category': 'drivetrain',
                'brand': brands['Shimano'],
                'priority': 5,
                'attributes': [usage_values['city'], budget_values['premium']],
                'compatible_with': [],
                'variants': [('Standard', 2, Decimal('39999.00'))],
            },
        ]

        # BRAKES (Prices in Philippine Peso)
        brakes_data = [
            # Budget - City/Casual Rim Brakes
            {
                'name': 'Rim Brake Set',
                'price': Decimal('1999.00'),
                'description': 'Traditional caliper brake system for city bikes.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'priority': 10,
                'attributes': [usage_values['city'], usage_values['casual'], budget_values['budget'], brake_values['rim']],
                'compatible_with': [brake_values['rim']],
                'variants': [('Standard', 8, Decimal('1999.00'))],
            },
            # Budget - Trail Disc Brakes
            {
                'name': 'Mechanical Disc Brakes MTB',
                'price': Decimal('3500.00'),
                'description': 'Cable-actuated disc brakes for trail riding.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'priority': 10,
                'attributes': [usage_values['trail'], budget_values['budget'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Standard', 6, Decimal('3500.00'))],
            },
            # Budget/Mid - City Disc Brakes
            {
                'name': 'Mechanical Disc Brakes Urban',
                'price': Decimal('3500.00'),
                'description': 'Cable-actuated disc brakes for city commuting.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'priority': 8,
                'attributes': [usage_values['city'], budget_values['budget'], budget_values['mid'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Standard', 5, Decimal('3500.00'))],
            },
            # Mid/Premium - Trail Hydraulic
            {
                'name': 'Hydraulic Disc Brakes Trail',
                'price': Decimal('12499.00'),
                'description': 'Premium hydraulic disc brakes for mountain biking.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'priority': 5,
                'attributes': [usage_values['trail'], budget_values['mid'], budget_values['premium'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Standard', 4, Decimal('12499.00'))],
            },
            # Mid/Premium - City Hydraulic
            {
                'name': 'Hydraulic Disc Brakes Urban',
                'price': Decimal('12499.00'),
                'description': 'Premium hydraulic disc brakes for high-end city bikes.',
                'category': 'brakes',
                'brand': brands['Shimano'],
                'priority': 5,
                'attributes': [usage_values['city'], budget_values['mid'], budget_values['premium'], brake_values['disc']],
                'compatible_with': [brake_values['disc']],
                'variants': [('Standard', 3, Decimal('12499.00'))],
            },
        ]

        # HANDLEBARS (Prices in Philippine Peso)
        handlebars_data = [
            {
                'name': 'Comfort Cruiser Bars',
                'price': Decimal('1499.00'),
                'description': 'Upright handlebars for comfortable city riding.',
                'category': 'handlebars',
                'brand': brands['Giant'],
                'priority': 10,
                'attributes': [usage_values['city'], usage_values['casual'], budget_values['budget']],
                'compatible_with': [],
                'variants': [('Standard', 10, Decimal('1499.00'))],
            },
            {
                'name': 'Trail Flat Bars',
                'price': Decimal('1500.00'),
                'description': 'Wide flat bars for trail control.',
                'category': 'handlebars',
                'brand': brands['Specialized'],
                'priority': 10,
                'attributes': [usage_values['trail'], budget_values['budget'], budget_values['mid']],
                'compatible_with': [],
                'variants': [('760mm', 6, Decimal('1500.00')), ('800mm', 4, Decimal('1750.00'))],
            },
            {
                'name': 'Carbon Riser Bars',
                'price': Decimal('7499.00'),
                'description': 'Lightweight carbon handlebars with rise.',
                'category': 'handlebars',
                'brand': brands['Specialized'],
                'priority': 5,
                'attributes': [usage_values['trail'], budget_values['premium']],
                'compatible_with': [],
                'variants': [('780mm', 2, Decimal('7499.00'))],
            },
        ]

        # SADDLES (Prices in Philippine Peso)
        saddles_data = [
            {
                'name': 'Comfort Plus Saddle',
                'price': Decimal('1999.00'),
                'description': 'Extra padding for comfortable rides.',
                'category': 'saddle',
                'brand': brands['Giant'],
                'priority': 10,
                'attributes': [usage_values['city'], usage_values['casual'], budget_values['budget']],
                'compatible_with': [],
                'variants': [('Black', 8, Decimal('1999.00')), ('Brown', 5, Decimal('1999.00'))],
            },
            {
                'name': 'Trail Sport Saddle',
                'price': Decimal('1500.00'),
                'description': 'Performance saddle for trail riding.',
                'category': 'saddle',
                'brand': brands['Specialized'],
                'priority': 10,
                'attributes': [usage_values['trail'], budget_values['budget']],
                'compatible_with': [],
                'variants': [('Black', 6, Decimal('1500.00'))],
            },
            {
                'name': 'Trail Pro Saddle',
                'price': Decimal('3499.00'),
                'description': 'Premium performance saddle for serious trail riding.',
                'category': 'saddle',
                'brand': brands['Specialized'],
                'priority': 8,
                'attributes': [usage_values['trail'], budget_values['mid']],
                'compatible_with': [],
                'variants': [('Black', 4, Decimal('3499.00'))],
            },
            {
                'name': 'Pro Carbon Saddle',
                'price': Decimal('9999.00'),
                'description': 'Lightweight carbon-railed saddle for serious riders.',
                'category': 'saddle',
                'brand': brands['Specialized'],
                'priority': 5,
                'attributes': [budget_values['premium']],
                'compatible_with': [],
                'variants': [('Black', 3, Decimal('9999.00'))],
            },
        ]

        # Combine all product data
        all_products = frames_data + wheels_data + drivetrain_data + brakes_data + handlebars_data + saddles_data

        # Create product listings
        created_count = 0
        for product_data in all_products:
            # Get the appropriate subcategory for this product
            product_category = component_subcategories.get(
                product_data['category'],
                category
            )
            
            listing, created = ProductListing.objects.get_or_create(
                name=product_data['name'],
                defaults={
                    'price': product_data['price'],
                    'description': product_data['description'],
                    'category': product_category,
                    'available': True,
                    'bike_builder_enabled': True,
                    'builder_category': product_data['category'],
                    'builder_priority': product_data['priority'],
                }
            )
            
            if created:
                # Set compatibility attributes
                listing.compatibility_attributes.set(product_data['attributes'])
                listing.compatible_with.set(product_data['compatible_with'])
                
                # Create product variants
                for variant_name, stock, price in product_data['variants']:
                    Product.objects.create(
                        product_listing=listing,
                        name=product_data['name'],
                        variant_attribute=variant_name,
                        brand=product_data['brand'],
                        sku=f"{product_data['category'].upper()}-{variant_name.replace(' ', '-').upper()}",
                        price=price,
                        stock=stock,
                        available=True,
                    )
                
                created_count += 1
                self.stdout.write(f'  ✓ Created: {product_data["name"]}')
            else:
                self.stdout.write(f'  - Skipped (exists): {product_data["name"]}')

        self.stdout.write(self.style.SUCCESS(f'\n✓ Created {created_count} product listings'))
        self.stdout.write(self.style.SUCCESS('\nBike builder mock data created successfully!'))
        self.stdout.write('\nYou can now:')
        self.stdout.write('  1. Visit the Django admin to see the products')
        self.stdout.write('  2. Go to /builder to test the bike builder wizard')
        self.stdout.write('  3. Products are organized by usage type and budget')

