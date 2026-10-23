"""
Adds the FK from OrderLine.refund → payments.Refund.
This is in a separate migration to break the circular dependency between
orders and payments (payments depends on orders for Order/SupplierOrder/OrderLine,
and orders.OrderLine needs to reference payments.Refund).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0001_initial"),
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderline",
            name="refund",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="order_lines",
                to="payments.refund",
            ),
        ),
    ]
