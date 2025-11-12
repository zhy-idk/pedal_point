from django.db import migrations, models
import django.db.models.deletion


def link_sales_to_orders(apps, schema_editor):
    Sales = apps.get_model("api", "Sales")
    Order = apps.get_model("api", "Order")
    for sale in Sales.objects.exclude(order__isnull=True).select_related("order"):
        order = sale.order
        if order and order.sale_id is None:
            order.sale_id = sale.id
            order.save(update_fields=["sale"])


def unlink_sales_from_orders(apps, schema_editor):
    Sales = apps.get_model("api", "Sales")
    Order = apps.get_model("api", "Order")
    for order in Order.objects.exclude(sale__isnull=True).select_related("sale"):
        sale = order.sale
        if sale and getattr(sale, "order_id", None) is None:
            sale.order_id = order.id  # type: ignore[attr-defined]
            sale.save(update_fields=["order"])  # type: ignore[attr-defined]


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0019_repairestimate"),
    ]

    operations = [
        migrations.AddField(
            model_name="sales",
            name="total_amount",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10, verbose_name="Total Amount"
            ),
        ),
        migrations.AddField(
            model_name="sales",
            name="sale_type",
            field=models.CharField(
                choices=[
                    ("pos", "POS"),
                    ("online", "Online"),
                    ("online_cod", "Online COD"),
                ],
                default="online",
                max_length=20,
                verbose_name="Sale Type",
            ),
        ),
        migrations.AddField(
            model_name="sales",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("cod_pending", "COD Pending"),
                    ("paid", "Paid"),
                    ("failed", "Failed"),
                    ("refunded", "Refunded"),
                ],
                default="pending",
                max_length=20,
                verbose_name="Payment Status",
            ),
        ),
        migrations.AddField(
            model_name="sales",
            name="payment_date",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Payment Date"
            ),
        ),
        migrations.AddField(
            model_name="sales",
            name="notes",
            field=models.TextField(blank=True, default="", verbose_name="Notes"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sales",
            name="paymongo_checkout_session_id",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                verbose_name="PayMongo Checkout Session ID",
            ),
        ),
        migrations.AddField(
            model_name="sales",
            name="paymongo_payment_id",
            field=models.CharField(
                blank=True,
                help_text="Payment ID from PayMongo checkout session",
                max_length=255,
                null=True,
                verbose_name="PayMongo Payment ID",
            ),
        ),
        migrations.AlterField(
            model_name="sales",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash", "Cash"),
                    ("card", "Card"),
                    ("gcash", "GCash"),
                    ("paymaya", "PayMaya"),
                    ("bank_transfer", "Bank Transfer"),
                    ("cod", "Cash on Delivery"),
                    ("paymongo", "PayMongo"),
                ],
                default="paymongo",
                max_length=50,
                verbose_name="Payment Method",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="sale",
            field=models.OneToOneField(
                blank=True,
                help_text="Linked sale record for this order",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="order",
                to="api.sales",
                verbose_name="Sale",
            ),
        ),
        migrations.RunPython(link_sales_to_orders, unlink_sales_from_orders),
        migrations.RemoveField(
            model_name="sales",
            name="order",
        ),
        migrations.AddField(
            model_name="order",
            name="is_cod",
            field=models.BooleanField(
                default=False,
                help_text="Indicates whether this order is Cash on Delivery",
                verbose_name="Cash on Delivery",
            ),
        ),
        migrations.RemoveField(
            model_name="order",
            name="paid_at",
        ),
        migrations.RemoveField(
            model_name="order",
            name="paymongo_checkout_session_id",
        ),
        migrations.RemoveField(
            model_name="order",
            name="paymongo_payment_id",
        ),
        migrations.RemoveField(
            model_name="order",
            name="payment_method",
        ),
        migrations.RemoveField(
            model_name="order",
            name="payment_status",
        ),
        migrations.AlterField(
            model_name="sales",
            name="notes",
            field=models.TextField(blank=True, verbose_name="Notes"),
        ),
    ]

