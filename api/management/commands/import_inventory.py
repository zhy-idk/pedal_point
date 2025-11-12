"""
Management command to import inventory from Excel file.
Groups products by brand and name, creates listings automatically.
"""

from django.core.management.base import BaseCommand
from django.core.files import File
from django.db import transaction
from django.utils.text import slugify
from api.models import (
    Product,
    ProductVariantImage,
)
from decimal import Decimal
import os
from uuid import uuid4
from collections import deque
from datetime import datetime
try:
    from PIL import Image, ExifTags
except Exception:
    Image = None
    ExifTags = None


class Command(BaseCommand):
    help = 'Import inventory from Excel file (defaults to INVENTORY FINAL.xlsx)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='INVENTORY FINAL.xlsx',
            help='Path to Excel file (default: INVENTORY FINAL.xlsx)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making database changes',
        )
        parser.add_argument(
            '--images-dir',
            type=str,
            default='product pics',
            help='Directory containing product images (default: product pics)',
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

    def gather_image_paths(self, directory):
        """Collect image file paths sorted by capture/creation time (oldest first).
        Preference: EXIF DateTimeOriginal > EXIF DateTime > filesystem modified time.
        """
        if not directory:
            return []

        resolved_dir = os.path.abspath(directory)
        if not os.path.isdir(resolved_dir):
            self.stdout.write(
                self.style.WARNING(f'Image directory not found: {resolved_dir}')
            )
            return []

        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        raw_paths = []

        for root, _, files in os.walk(resolved_dir):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in allowed_extensions:
                    raw_paths.append(os.path.join(root, filename))

        if not raw_paths:
            self.stdout.write(
                self.style.WARNING(f'No images found under {resolved_dir}')
            )
            return []

        def parse_exif_datetime(dt_str):
            # Typical EXIF format: "YYYY:MM:DD HH:MM:SS"
            try:
                return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
            except Exception:
                return None

        def get_image_timestamp(path):
            # Return a datetime representing best guess of when photo was taken/created
            if Image and ExifTags:
                try:
                    with Image.open(path) as img:
                        exif = img.getexif()
                        if exif:
                            tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                            for key in ("DateTimeOriginal", "DateTime"):
                                if key in tag_map:
                                    dt = parse_exif_datetime(str(tag_map[key]))
                                    if dt:
                                        return dt
                except Exception:
                    pass
            # Fallback to filesystem modified time
            try:
                return datetime.fromtimestamp(os.path.getmtime(path))
            except Exception:
                return datetime.min

        # Build (timestamp, path) and sort oldest first
        image_with_times = [(get_image_timestamp(p), p) for p in raw_paths]
        image_with_times.sort(key=lambda x: x[0])
        image_paths = [p for _, p in image_with_times]
        self.stdout.write(
            f'Found {len(image_paths)} images in {resolved_dir} (sorted oldest first)'
        )
        return image_paths

    def next_image(self, image_queue):
        """Pop the next image path from the queue."""
        if not image_queue:
            return None
        return image_queue.popleft()

    def build_image_filename(self, base_name, suffix, original_path):
        base = slugify(base_name) or 'item'
        ext = os.path.splitext(original_path)[1].lower() or '.jpg'
        return f"{base}-{suffix}-{uuid4().hex[:8]}{ext}"

    def create_variant_image(self, product, image_path, alt_text=None, listing=None):
        if not image_path:
            return None

        filename = self.build_image_filename(
            listing.name if listing else (product.name or f'product-{product.pk}'),
            product.variant_attribute or 'variant',
            image_path,
        )

        with open(image_path, 'rb') as img_file:
            return ProductVariantImage.objects.create(
                product=product,
                listing=listing,
                image=File(img_file, name=filename),
                alt_text=alt_text
                or product.variant_attribute
                or product.name
                or (listing.name if listing else None)
                or 'Product image',
            )

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
        images_dir = options.get('images_dir')

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

            # Collect product data in row order (preserve Excel order)
            products_data = []
            
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

                if not product_name:
                    self.stdout.write(
                        self.style.WARNING(f'Row {idx + 2}: Missing product name, skipping')
                    )
                    continue

                products_data.append({
                    'row_num': idx + 2,
                    'brand_name': brand_name,
                    'color': color,
                    'price': price,
                    'qty': qty,
                    'supplier_name': supplier_name,
                    'product_name': product_name,
                })

            total_products = len(products_data)
            self.stdout.write(f'\nPrepared {total_products} products for import\n')

            image_queue = deque(self.gather_image_paths(images_dir) if images_dir else [])
            image_shortage_warned = False
            total_images_available = len(image_queue)
            if image_queue:
                self.stdout.write(f'Images available: {total_images_available}')
            else:
                self.stdout.write('Images available: 0')

            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made\n'))
                # Show preview
                for product in products_data[:5]:
                    self.stdout.write(
                        f"Row {product['row_num']}: {product['product_name']} "
                        f"(Color: {product['color'] or 'N/A'}, Price: {product['price']}, Qty: {product['qty']})"
                    )
                return

            # Process in transaction
            with transaction.atomic():
                products_created = 0
                products_updated = 0

                for product_data in products_data:
                    defaults = {
                        'price': product_data['price'],
                        'stock': product_data['qty'],
                        'available': product_data['qty'] > 0,
                        'supplier_price': None,
                        'supply': None,
                    }

                    product, created = Product.objects.update_or_create(
                        name=product_data['product_name'],
                        variant_attribute=product_data['color'],
                        product_listing=None,
                        brand=None,
                        defaults=defaults,
                    )

                    if created:
                        products_created += 1
                    else:
                        products_updated += 1

                    needs_image = not product.product_images.exists()
                    if needs_image:
                        image_path = self.next_image(image_queue)
                        if image_path:
                            self.create_variant_image(
                                product,
                                image_path,
                                alt_text=product.variant_attribute or product.name,
                                listing=None,
                            )
                        elif not image_shortage_warned:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"No image available for product '{product.name}' (row {product_data['row_num']})"
                                )
                            )
                            image_shortage_warned = True

            # Summary
            self.stdout.write('\n' + '='*50)
            self.stdout.write(self.style.SUCCESS('Import completed successfully!'))
            self.stdout.write('='*50)
            self.stdout.write(f'Products: {products_created} created, {products_updated} updated')
            if total_images_available:
                self.stdout.write(f'Images consumed: {min(products_created + products_updated, total_images_available)} '
                                  f'out of {total_images_available}')
            self.stdout.write('='*50)

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error importing inventory: {str(e)}')
            )
            import traceback
            traceback.print_exc()
            raise

