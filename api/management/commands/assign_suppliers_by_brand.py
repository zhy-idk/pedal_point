"""
Management command to assign suppliers to products based on their brands.
Products with the same brand will be assigned to the same supplier.
Brands are distributed evenly across all available suppliers.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Product, ProductSupplier, Brands


class Command(BaseCommand):
    help = 'Assigns suppliers to products based on their brands. Products with the same brand get the same supplier. Brands are distributed evenly across suppliers.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be assigned without making changes',
        )
        parser.add_argument(
            '--supplier-count',
            type=int,
            default=7,
            help='Number of suppliers to distribute brands across (default: 7)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        supplier_count = options.get('supplier_count', 7)

        # Get all suppliers
        suppliers = list(ProductSupplier.objects.all().order_by('id'))
        
        if not suppliers:
            self.stdout.write(
                self.style.ERROR('No suppliers found in the database. Please create suppliers first.')
            )
            return

        if len(suppliers) < supplier_count:
            self.stdout.write(
                self.style.WARNING(
                    f'Only {len(suppliers)} suppliers found, but {supplier_count} requested. '
                    f'Will use all {len(suppliers)} suppliers.'
                )
            )
            supplier_count = len(suppliers)
        elif len(suppliers) > supplier_count:
            self.stdout.write(
                self.style.WARNING(
                    f'Found {len(suppliers)} suppliers, but only using the first {supplier_count}. '
                    f'To use all suppliers, run with --supplier-count {len(suppliers)}'
                )
            )

        # Get all unique brands that have products
        brands_with_products = Brands.objects.filter(
            product__isnull=False
        ).distinct().order_by('id')

        if not brands_with_products.exists():
            self.stdout.write(
                self.style.WARNING('No brands with products found.')
            )
            return

        brand_list = list(brands_with_products)
        total_brands = len(brand_list)

        self.stdout.write(f'\nFound {total_brands} unique brands with products.')
        self.stdout.write(f'Found {len(suppliers)} suppliers.')
        self.stdout.write(f'Distributing brands across {supplier_count} suppliers...\n')

        # Create brand-to-supplier mapping (round-robin distribution)
        brand_supplier_map = {}
        for index, brand in enumerate(brand_list):
            supplier_index = index % supplier_count
            supplier = suppliers[supplier_index]
            brand_supplier_map[brand.id] = supplier
            self.stdout.write(
                f'  Brand "{brand.name}" -> Supplier "{supplier.name}"'
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDRY RUN MODE - No changes will be made.')
            )
            
            # Count products that would be affected
            total_products = 0
            for brand_id, supplier in brand_supplier_map.items():
                product_count = Product.objects.filter(brand_id=brand_id).count()
                total_products += product_count
                self.stdout.write(
                    f'  Would update {product_count} products with brand ID {brand_id} '
                    f'to supplier "{supplier.name}"'
                )
            
            self.stdout.write(
                f'\nWould update {total_products} products total.'
            )
            return

        # Perform the updates
        self.stdout.write('\nUpdating products...')
        
        updated_count = 0
        errors = []

        with transaction.atomic():
            try:
                for brand_id, supplier in brand_supplier_map.items():
                    count = Product.objects.filter(brand_id=brand_id).update(supply=supplier)
                    updated_count += count
                    self.stdout.write(
                        f'  Updated {count} products with brand ID {brand_id} '
                        f'to supplier "{supplier.name}"'
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nSuccessfully updated {updated_count} products. '
                        f'All products with the same brand now have the same supplier.'
                    )
                )

                # Show summary by supplier
                self.stdout.write('\nSummary by supplier:')
                for supplier in suppliers[:supplier_count]:
                    assigned_brands = [
                        brand for brand, sup in brand_supplier_map.items() 
                        if sup.id == supplier.id
                    ]
                    product_count = Product.objects.filter(supply=supplier).count()
                    self.stdout.write(
                        f'  {supplier.name}: {len(assigned_brands)} brands, {product_count} products'
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error updating products: {str(e)}')
                )
                errors.append(str(e))
                raise

        if errors:
            self.stdout.write(
                self.style.ERROR(f'\nCompleted with {len(errors)} error(s).')
            )

