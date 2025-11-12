"""
Preview/import a limited number of rows from the inventory Excel file.

Unlike the main import command, this writes a small sample (default: 10 rows)
directly to the database so you can quickly verify that the data shows up in
the API/admin before running the full import.
"""

import os
from collections import deque
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from api.models import Product, ProductVariantImage


class Command(BaseCommand):
    help = "Preview/import a limited number of rows from the inventory Excel file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="INVENTORY FINAL.xlsx",
            help="Path to Excel file (default: INVENTORY FINAL.xlsx)",
        )
        parser.add_argument(
            "--images-dir",
            type=str,
            default="product pics",
            help="Directory containing product images (default: product pics)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Number of rows to import (default: 10)",
        )

    # Utility helpers (copied from import_inventory to stay consistent)
    def normalize_brand_name(self, brand_name):
        if not brand_name:
            return None
        normalized = " ".join(str(brand_name).strip().upper().split())
        return normalized if normalized else None

    def normalize_color(self, color):
        if not color:
            return None
        color_str = str(color).strip()
        if color_str.upper() in ["-", "N/A", "NA", "NONE", "NULL", "", " "]:
            return None
        return color_str

    def normalize_product_name(self, name):
        if not name:
            return None
        return " ".join(str(name).strip().split())

    def find_column_index(self, headers, possible_names):
        headers_lower = [str(h).lower().strip() for h in headers]
        for name in possible_names:
            name_lower = name.lower().strip()
            for idx, header in enumerate(headers_lower):
                if name_lower in header or header in name_lower:
                    return idx
        return None

    def build_image_filename(self, base_name, suffix, original_path):
        base = slugify(base_name) or "item"
        ext = os.path.splitext(original_path)[1].lower() or ".jpg"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{base}-{suffix}-{timestamp}{ext}"

    def generate_sku(self, name, brand=None, variant=None, product_id=None):
        parts = []
        for value in (brand, name, variant):
            if value:
                parts.append(str(value))
        if not parts:
            parts.append("item")

        base = slugify("-".join(parts)).replace("-", "").upper()
        if not base:
            base = f"ITEM{datetime.now().strftime('%Y%m%d%H%M%S')}"

        base = base[:32]
        candidate = base
        counter = 1
        while Product.objects.filter(sku=candidate).exclude(id=product_id).exists():
            suffix = f"{counter}"
            candidate = f"{base[:32-len(suffix)]}{suffix}"
            counter += 1
        return candidate

    def handle(self, *args, **options):
        file_path = options["file"]
        limit = options["limit"] or 10
        images_dir = options.get("images_dir")

        try:
            import pandas as pd
        except ImportError:
            self.stdout.write(
                self.style.ERROR(
                    "pandas is required. Install it with: pip install pandas openpyxl"
                )
            )
            return

        try:
            df = pd.read_excel(file_path)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(f"Failed to read Excel file: {exc}")
            )
            return

        if df.empty:
            self.stdout.write(self.style.WARNING("Excel file is empty."))
            return

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(df)} rows"))

        brand_idx = self.find_column_index(
            df.columns, ["brand", "marca", "manufacturer", "make"]
        )
        name_idx = self.find_column_index(
            df.columns, ["name", "product", "product name", "item", "product_name"]
        )
        color_idx = self.find_column_index(
            df.columns, ["color", "colour", "variant", "color/variant", "variant_attribute"]
        )
        price_idx = self.find_column_index(
            df.columns, ["price", "retail price", "selling price", "srp", "amount"]
        )
        supplier_price_idx = self.find_column_index(
            df.columns, ["capital", "supplier price", "cost", "wholesale", "landed cost"]
        )
        qty_idx = self.find_column_index(
            df.columns, ["qty", "quantity", "stock", "inventory", "qty.", "quantity."]
        )

        if name_idx is None or price_idx is None or qty_idx is None:
            self.stdout.write(
                self.style.ERROR(
                    "Excel file must have columns for product name, price, and quantity."
                )
            )
            return

        self.stdout.write("\nColumn mapping:")
        self.stdout.write(
            f"  Brand: {df.columns[brand_idx] if brand_idx is not None else 'Not found (optional)'}"
        )
        self.stdout.write(f"  Product Name: {df.columns[name_idx]}")
        self.stdout.write(
            f"  Color: {df.columns[color_idx] if color_idx is not None else 'Not found'}"
        )
        self.stdout.write(f"  Price: {df.columns[price_idx]}")
        self.stdout.write(
            f"  Supplier Price: {df.columns[supplier_price_idx] if supplier_price_idx is not None else 'Not found (optional)'}"
        )
        self.stdout.write(f"  Quantity: {df.columns[qty_idx]}\n")

        # Prepare image queue (oldest first, same logic as main import)
        def parse_exif_datetime(dt_str):
            try:
                return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
            except Exception:
                return None

        def gather_image_paths(directory):
            if not directory:
                return deque()

            resolved_dir = os.path.abspath(directory)
            if not os.path.isdir(resolved_dir):
                self.stdout.write(
                    self.style.WARNING(f"Image directory not found: {resolved_dir}")
                )
                return deque()

            allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
            raw_paths = []

            try:
                from PIL import Image, ExifTags
            except Exception:
                Image = None
                ExifTags = None

            for root, _, files in os.walk(resolved_dir):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in allowed_extensions:
                        raw_paths.append(os.path.join(root, filename))

            if not raw_paths:
                self.stdout.write(
                    self.style.WARNING(f"No images found under {resolved_dir}")
                )
                return deque()

            def get_image_timestamp(path):
                if Image and ExifTags:
                    try:
                        with Image.open(path) as img:
                            exif = img.getexif()
                            if exif:
                                tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                                for key in ("DateTimeOriginal", "DateTime"):
                                    dt = parse_exif_datetime(str(tag_map.get(key)))
                                    if dt:
                                        return dt
                    except Exception:
                        pass
                try:
                    return datetime.fromtimestamp(os.path.getmtime(path))
                except Exception:
                    return datetime.min

            image_with_times = [(get_image_timestamp(p), p) for p in raw_paths]
            image_with_times.sort(key=lambda x: x[0])
            ordered_paths = [p for _, p in image_with_times]
            self.stdout.write(
                f"Found {len(ordered_paths)} images in {resolved_dir} (sorted oldest first)"
            )
            return deque(ordered_paths)

        image_queue = gather_image_paths(images_dir)
        image_shortage_warned = False
        total_images_available = len(image_queue)
        if total_images_available:
            self.stdout.write(f"Images available: {total_images_available}")
        else:
            self.stdout.write("Images available: 0")

        rows_processed = 0
        created = 0
        updated = 0

        with transaction.atomic():
            for idx, row in df.iterrows():
                if rows_processed >= limit:
                    break

                product_name = self.normalize_product_name(row.iloc[name_idx])
                if not product_name:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {idx + 2}: Missing product name, skipping"
                        )
                    )
                    continue

                brand_name = (
                    self.normalize_brand_name(row.iloc[brand_idx])
                    if brand_idx is not None
                    else None
                )

                color = (
                    self.normalize_color(row.iloc[color_idx])
                    if color_idx is not None
                    else None
                )

                try:
                    price = Decimal(str(row.iloc[price_idx])).quantize(Decimal("0.01"))
                except (ValueError, TypeError, InvalidOperation):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {idx + 2}: Invalid price '{row.iloc[price_idx]}', skipping"
                        )
                    )
                    continue

                try:
                    qty = int(float(row.iloc[qty_idx]))
                except (ValueError, TypeError):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {idx + 2}: Invalid quantity '{row.iloc[qty_idx]}', skipping"
                        )
                    )
                    continue

                supplier_price = None
                if supplier_price_idx is not None:
                    supplier_value = row.iloc[supplier_price_idx]
                    if supplier_value not in (None, ""):
                        try:
                            supplier_price = Decimal(str(supplier_value)).quantize(
                                Decimal("0.01")
                            )
                        except (ValueError, TypeError):
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Row {idx + 2}: Invalid supplier price '{supplier_value}', leaving blank"
                                )
                            )

                defaults = {
                    "price": price,
                    "stock": qty,
                    "available": qty > 0,
                    "supplier_price": supplier_price,
                    "product_listing": None,
                    "brand": None,
                }

                product, was_created = Product.objects.update_or_create(
                    name=product_name,
                    variant_attribute=color,
                    defaults=defaults,
                )

                if was_created or not product.sku:
                    new_sku = self.generate_sku(
                        product_name,
                        brand=brand_name,
                        variant=color,
                        product_id=product.id,
                    )
                    if product.sku != new_sku:
                        product.sku = new_sku
                        product.save(update_fields=["sku"])

                # Attach image if missing
                if not product.product_images.exists():
                    if image_queue:
                        image_path = image_queue.popleft()
                        filename = self.build_image_filename(
                            product.name or f"product-{product.pk}", "preview", image_path
                        )
                        try:
                            with open(image_path, "rb") as img_file:
                                ProductVariantImage.objects.create(
                                    product=product,
                                    listing=None,
                                    image=File(img_file, name=filename),
                                    alt_text=product.variant_attribute
                                    or product.name
                                    or "Product image",
                                )
                        except Exception as img_err:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Image upload failed for '{product.name}' "
                                    f"(row {idx + 2}): {img_err}"
                                )
                            )
                    elif not image_shortage_warned:
                        self.stdout.write(
                            self.style.WARNING(
                                f"No image available for product '{product.name}' (row {idx + 2})"
                            )
                        )
                        image_shortage_warned = True

                action = "Created" if was_created else "Updated"
                message = (
                    f"{action} product ID {product.id}: "
                    f"{product.name} "
                    f"(color={product.variant_attribute or 'N/A'}, "
                    f"price={product.price}, stock={product.stock}, "
                    f"supplier_price={product.supplier_price}, "
                    f"sku={product.sku or 'N/A'}, "
                    f"images={product.product_images.count()})"
                )
                self.stdout.write(self.style.SUCCESS(message))

                rows_processed += 1
                created += 1 if was_created else 0
                updated += 0 if was_created else 1

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Preview import completed"))
        self.stdout.write("=" * 50)
        self.stdout.write(f"Rows processed: {rows_processed}")
        self.stdout.write(f"Products created: {created}")
        self.stdout.write(f"Products updated: {updated}")
        if total_images_available:
            self.stdout.write(
                f"Images consumed: {min(rows_processed, total_images_available)} "
                f"out of {total_images_available}"
            )

