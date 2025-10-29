from django.core.management.base import BaseCommand
from api.models import ProductCategory


class Command(BaseCommand):
    help = 'Setup default product categories (Bikes, Components, Miscellaneous)'

    def handle(self, *args, **kwargs):
        self.stdout.write('Setting up default categories...')

        # Create or get top-level categories
        bikes, _ = ProductCategory.objects.get_or_create(
            slug='bikes',
            defaults={
                'name': 'Bikes',
                'is_component': False,
            }
        )
        self.stdout.write(self.style.SUCCESS(f'✓ Created/Found: {bikes.name}'))

        components, _ = ProductCategory.objects.get_or_create(
            slug='components',
            defaults={
                'name': 'Components',
                'is_component': True,
            }
        )
        self.stdout.write(self.style.SUCCESS(f'✓ Created/Found: {components.name}'))

        miscellaneous, _ = ProductCategory.objects.get_or_create(
            slug='miscellaneous',
            defaults={
                'name': 'Miscellaneous',
                'is_component': False,
            }
        )
        self.stdout.write(self.style.SUCCESS(f'✓ Created/Found: {miscellaneous.name}'))

        # Create component subcategories under Components
        component_subcategories = [
            ('frames', 'Frames', 'frame'),
            ('wheels', 'Wheels', 'wheels'),
            ('drivetrain', 'Drivetrain', 'drivetrain'),
            ('brakes', 'Brakes', 'brakes'),
            ('handlebars', 'Handlebars', 'handlebars'),
            ('saddles', 'Saddles', 'saddle'),
            ('pedals', 'Pedals', 'other'),
            ('accessories', 'Accessories', 'other'),
        ]

        for slug, name, comp_type in component_subcategories:
            subcat, created = ProductCategory.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'parent': components,
                    'is_component': True,
                    'component_type': comp_type,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created subcategory: {name}'))
            else:
                # Update parent if it was None
                if not subcat.parent:
                    subcat.parent = components
                    subcat.save()
                self.stdout.write(f'  - Found subcategory: {name}')

        self.stdout.write(self.style.SUCCESS('\n✅ Categories setup complete!'))
        self.stdout.write('Available categories:')
        self.stdout.write('  - /bikes')
        self.stdout.write('  - /components (with subcategories)')
        self.stdout.write('  - /miscellaneous')

