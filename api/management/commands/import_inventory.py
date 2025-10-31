"""
Management command to import inventory from Excel file.
Groups products by brand and name, creates listings automatically.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import (
    Brands,
    Product,
    ProductListing,
    ProductSupplier,
    ProductCategory,
)
from decimal import Decimal
import os
import re
from collections import defaultdict


class Command(BaseCommand):
    help = 'Import inventory from Excel file (INVENTORY.xlsx)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='INVENTORY.xlsx',
            help='Path to Excel file (default: INVENTORY.xlsx)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making database changes',
        )

    def normalize_brand_name(self, brand_name):
        """Normalize brand name: remove extra whitespace, convert to uppercase"""
        if not brand_name:
            return None
        # Remove extra whitespace and convert to uppercase
        normalized = ' '.join(str(brand_name).strip().upper().split())
        return normalized if normalized else None

    def normalize_color(self, color):
        """Normalize color: if '-' or empty or similar, return None"""
        if not color:
            return None
        color_str = str(color).strip()
        # Check if color is "-", "N/A", "None", etc.
        if color_str.upper() in ['-', 'N/A', 'NA', 'NONE', 'NULL', '', ' ']:
            return None
        return color_str

    def normalize_product_name(self, name):
        """Normalize product name: remove extra whitespace"""
        if not name:
            return None
        return ' '.join(str(name).strip().split())

    def find_column_index(self, headers, possible_names):
        """Find column index by matching possible column names (case-insensitive)"""
        headers_lower = [str(h).lower().strip() for h in headers]
        for name in possible_names:
            name_lower = name.lower().strip()
            for idx, header in enumerate(headers_lower):
                if name_lower in header or header in name_lower:
                    return idx
        return None

    def handle(self, *args, **options):
        file_path = options['file']
        dry_run = options['dry_run']

        # Check if file exists
        if not os.path.exists(file_path):
            self.stdout.write(
                self.style.ERROR(f'File not found: {file_path}')
            )
            return

        self.stdout.write(f'Reading Excel file: {file_path}')
        
        try:
            import pandas as pd
        except ImportError:
            self.stdout.write(
                self.style.ERROR(
                    'pandas is required. Install it with: pip install pandas openpyxl'
                )
            )
            return

        try:
            # Read Excel file
            df = pd.read_excel(file_path)
            self.stdout.write(f'Found {len(df)} rows in Excel file')
            
            # Display column names for debugging
            self.stdout.write(f'Columns found: {list(df.columns)}')
            
            # Find column indices
            brand_idx = self.find_column_index(
                df.columns, 
                ['brand', 'marca', 'manufacturer', 'make']
            )
            name_idx = self.find_column_index(
                df.columns,
                ['name', 'product', 'product name', 'item', 'product_name']
            )
            color_idx = self.find_column_index(
                df.columns,
                ['color', 'colour', 'variant', 'color/variant', 'variant_attribute']
            )
            price_idx = self.find_column_index(
                df.columns,
                ['price', 'cost', 'amount', 'retail price', 'selling price']
            )
            qty_idx = self.find_column_index(
                df.columns,
                ['qty', 'quantity', 'stock', 'inventory', 'qty.', 'quantity.']
            )
            supplier_idx = self.find_column_index(
                df.columns,
                ['supplier', 'vendor', 'supplier name']
            )

            # Validate required columns
            if brand_idx is None:
                self.stdout.write(
                    self.style.ERROR('Could not find brand column. Expected: brand, marca, manufacturer, make')
                )
                return
            if name_idx is None:
                self.stdout.write(
                    self.style.ERROR('Could not find product name column. Expected: name, product, product name, item')
                )
                return
            if price_idx is None:
                self.stdout.write(
                    self.style.ERROR('Could not find price column. Expected: price, cost, amount, retail price')
                )
                return
            if qty_idx is None:
                self.stdout.write(
                    self.style.ERROR('Could not find quantity column. Expected: qty, quantity, stock, inventory')
                )
                return

            self.stdout.write('\nColumn mapping:')
            self.stdout.write(f'  Brand: {df.columns[brand_idx]}')
            self.stdout.write(f'  Product Name: {df.columns[name_idx]}')
            self.stdout.write(f'  Color: {df.columns[color_idx] if color_idx is not None else "Not found"}')
            self.stdout.write(f'  Price: {df.columns[price_idx]}')
            self.stdout.write(f'  Quantity: {df.columns[qty_idx]}')
            self.stdout.write(f'  Supplier: {df.columns[supplier_idx] if supplier_idx is not None else "Not found (will derive from product name)"}')

            # Get or create a default category (Components)
            try:
                default_category = ProductCategory.objects.get(slug='components')
            except ProductCategory.DoesNotExist:
                # Try to get any category
                default_category = ProductCategory.objects.first()
                if not default_category:
                    self.stdout.write(
                        self.style.WARNING('No category found. Creating "Components" category...')
                    )
                    if not dry_run:
                        default_category = ProductCategory.objects.create(
                            name='Components',
                            slug='components',
                            is_component=True
                        )
                    else:
                        default_category = None

            # Group data by brand, then by product name
            grouped_data = defaultdict(lambda: defaultdict(list))
            
            for idx, row in df.iterrows():
                brand_name = self.normalize_brand_name(row.iloc[brand_idx])
                product_name = self.normalize_product_name(row.iloc[name_idx])
                color = self.normalize_color(row.iloc[color_idx] if color_idx is not None else None)
                
                # Get price and quantity
                try:
                    price = Decimal(str(row.iloc[price_idx])).quantize(Decimal('0.01'))
                except (ValueError, TypeError):
                    self.stdout.write(
                        self.style.WARNING(f'Row {idx + 2}: Invalid price, skipping')
                    )
                    continue
                
                try:
                    qty = int(float(row.iloc[qty_idx]))
                except (ValueError, TypeError):
                    self.stdout.write(
                        self.style.WARNING(f'Row {idx + 2}: Invalid quantity, skipping')
                    )
                    continue

                # Get supplier if column exists, otherwise will derive from product name
                supplier_name = None
                if supplier_idx is not None:
                    supplier_name = str(row.iloc[supplier_idx]).strip() if pd.notna(row.iloc[supplier_idx]) else None

                if not brand_name or not product_name:
                    self.stdout.write(
                        self.style.WARNING(f'Row {idx + 2}: Missing brand or product name, skipping')
                    )
                    continue

                grouped_data[brand_name][product_name].append({
                    'color': color,
                    'price': price,
                    'qty': qty,
                    'supplier_name': supplier_name,
                    'row_num': idx + 2,  # Excel row number (1-indexed, +1 for header)
                })

            self.stdout.write(f'\nGrouped into {len(grouped_data)} brands')
            total_listings = sum(len(products) for products in grouped_data.values())
            self.stdout.write(f'Will create {total_listings} product listings')
            
            total_products = sum(
                sum(len(variants) for variants in products.values())
                for products in grouped_data.values()
            )
            self.stdout.write(f'Will create {total_products} products\n')

            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made\n'))
                # Show preview
                for brand_name, products in list(grouped_data.items())[:3]:
                    self.stdout.write(f'Brand: {brand_name}')
                    for product_name, variants in list(products.items())[:2]:
                        self.stdout.write(f'  Product: {product_name} ({len(variants)} variants)')
                return

            # Process in transaction
            with transaction.atomic():
                brands_created = 0
                brands_existing = 0
                suppliers_created = 0
                suppliers_existing = 0
                listings_created = 0
                listings_existing = 0
                products_created = 0

                # Process each brand
                for brand_name, products in grouped_data.items():
                    # Create or get brand
                    brand, created = Brands.objects.get_or_create(
                        name=brand_name,
                        defaults={'name': brand_name}
                    )
                    if created:
                        brands_created += 1
                    else:
                        brands_existing += 1

                    # Process each product name within this brand
                    for product_name, variants in products.items():
                        # Determine supplier - use supplier from first variant if available,
                        # otherwise use product name as supplier name
                        first_variant = variants[0]
                        supplier_name = first_variant['supplier_name'] or product_name
                        
                        # Create or get supplier
                        supplier, created = ProductSupplier.objects.get_or_create(
                            name=supplier_name,
                            defaults={'name': supplier_name}
                        )
                        if created:
                            suppliers_created += 1
                        else:
                            suppliers_existing += 1

                        # Find minimum price for listing
                        min_price = min(v['price'] for v in variants)
                        
                        # Create or get product listing
                        listing, created = ProductListing.objects.get_or_create(
                            name=product_name,
                            defaults={
                                'name': product_name,
                                'price': min_price,
                                'category': default_category,
                                'available': True,
                            }
                        )
                        if created:
                            listings_created += 1
                        else:
                            listings_existing += 1
                            # Update price if new minimum is lower
                            if min_price < listing.price:
                                listing.price = min_price
                                listing.save()

                        # Create products (variants)
                        for variant in variants:
                            # Calculate supplier price (30% below retail = 70% of price)
                            supplier_price = variant['price'] * Decimal('0.7')
                            
                            # Create product
                            product, created = Product.objects.get_or_create(
                                product_listing=listing,
                                brand=brand,
                                variant_attribute=variant['color'],
                                defaults={
                                    'name': product_name,
                                    'variant_attribute': variant['color'],
                                    'brand': brand,
                                    'supply': supplier,
                                    'price': variant['price'],
                                    'supplier_price': supplier_price,
                                    'stock': variant['qty'],
                                    'available': variant['qty'] > 0,
                                    'product_listing': listing,
                                }
                            )
                            
                            if created:
                                products_created += 1
                            else:
                                # Update existing product
                                product.price = variant['price']
                                product.supplier_price = supplier_price
                                product.stock = variant['qty']
                                product.available = variant['qty'] > 0
                                product.supply = supplier
                                product.save()

                # Update listing prices from products
                for listing in ProductListing.objects.all():
                    products = listing.products.all()
                    if products.exists():
                        min_price = min(p.price for p in products)
                        if listing.price != min_price:
                            listing.price = min_price
                            listing.save()

            # Summary
            self.stdout.write('\n' + '='*50)
            self.stdout.write(self.style.SUCCESS('Import completed successfully!'))
            self.stdout.write('='*50)
            self.stdout.write(f'Brands: {brands_created} created, {brands_existing} existing')
            self.stdout.write(f'Suppliers: {suppliers_created} created, {suppliers_existing} existing')
            self.stdout.write(f'Listings: {listings_created} created, {listings_existing} existing')
            self.stdout.write(f'Products: {products_created} created')
            self.stdout.write('='*50)

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error importing inventory: {str(e)}')
            )
            import traceback
            traceback.print_exc()
            raise

