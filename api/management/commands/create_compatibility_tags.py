"""
Management command to create default bike compatibility tags.
Run this after migrating to the new compatibility system.
"""

from django.core.management.base import BaseCommand
from api.models import BikeCompatibilityTag


class Command(BaseCommand):
    help = "Creates default bike compatibility tags for the bike builder"

    def handle(self, *args, **options):
        self.stdout.write("Creating default bike compatibility tags...")

        tags_created = 0
        tags_skipped = 0

        # Define all default tags
        default_tags = [
            # Use Case Tags
            {
                "tag_type": "use_case",
                "value": "city",
                "display_name": "City Commuting",
                "description": "Perfect for daily commutes on paved roads and city streets",
                "display_order": 30,
            },
            {
                "tag_type": "use_case",
                "value": "trail",
                "display_name": "Trail Riding",
                "description": "Built for off-road adventures on dirt trails and rough terrain",
                "display_order": 20,
            },
            {
                "tag_type": "use_case",
                "value": "casual",
                "display_name": "Casual Recreation",
                "description": "Ideal for leisurely rides around the neighborhood or parks",
                "display_order": 10,
            },
            # Budget Tags
            {
                "tag_type": "budget",
                "value": "budget",
                "display_name": "Budget (₱15,000 - ₱24,000)",
                "description": "Great starter options with solid performance at an affordable price",
                "display_order": 30,
            },
            {
                "tag_type": "budget",
                "value": "mid",
                "display_name": "Mid-Range (₱25,000 - ₱74,000)",
                "description": "Best value for quality - perfect balance of performance and price",
                "display_order": 20,
            },
            {
                "tag_type": "budget",
                "value": "premium",
                "display_name": "Premium (₱75,000+)",
                "description": "Top-tier performance components for serious cyclists",
                "display_order": 10,
            },
            # Brake Type Tags
            {
                "tag_type": "physical",
                "value": "disc_brake",
                "display_name": "Disc Brakes",
                "description": "Modern braking system with superior stopping power",
                "display_order": 100,
            },
            {
                "tag_type": "physical",
                "value": "rim_brake",
                "display_name": "Rim Brakes",
                "description": "Traditional braking system, lightweight and economical",
                "display_order": 90,
            },
            {
                "tag_type": "physical",
                "value": "mechanical_disc",
                "display_name": "Mechanical Disc Brakes",
                "description": "Cable-actuated disc brakes",
                "display_order": 85,
            },
            {
                "tag_type": "physical",
                "value": "hydraulic_disc",
                "display_name": "Hydraulic Disc Brakes",
                "description": "Fluid-actuated disc brakes for maximum stopping power",
                "display_order": 95,
            },
            # Wheel Size Tags
            {
                "tag_type": "physical",
                "value": "wheel_26",
                "display_name": "26\" Wheels",
                "description": "Traditional mountain bike wheel size",
                "display_order": 80,
            },
            {
                "tag_type": "physical",
                "value": "wheel_27_5",
                "display_name": "27.5\" Wheels",
                "description": "Modern mountain bike wheel size (650b)",
                "display_order": 75,
            },
            {
                "tag_type": "physical",
                "value": "wheel_29",
                "display_name": "29\" Wheels",
                "description": "Large mountain bike wheels for rolling over obstacles",
                "display_order": 70,
            },
            {
                "tag_type": "physical",
                "value": "wheel_700c",
                "display_name": "700c Wheels",
                "description": "Standard road bike and hybrid wheel size",
                "display_order": 65,
            },
            # Frame Material Tags
            {
                "tag_type": "physical",
                "value": "material_aluminum",
                "display_name": "Aluminum Frame",
                "description": "Lightweight and corrosion-resistant",
                "display_order": 60,
            },
            {
                "tag_type": "physical",
                "value": "material_carbon",
                "display_name": "Carbon Fiber Frame",
                "description": "Ultra-lightweight and high-performance",
                "display_order": 55,
            },
            {
                "tag_type": "physical",
                "value": "material_steel",
                "display_name": "Steel Frame",
                "description": "Durable and comfortable ride quality",
                "display_order": 50,
            },
            {
                "tag_type": "physical",
                "value": "material_alloy",
                "display_name": "Alloy Frame",
                "description": "Mixed metal construction for strength and weight balance",
                "display_order": 45,
            },
            # Bike Type Tags
            {
                "tag_type": "physical",
                "value": "type_mtb",
                "display_name": "Mountain Bike",
                "description": "Designed for off-road cycling",
                "display_order": 40,
            },
            {
                "tag_type": "physical",
                "value": "type_road",
                "display_name": "Road Bike",
                "description": "Built for speed on paved surfaces",
                "display_order": 35,
            },
            {
                "tag_type": "physical",
                "value": "type_hybrid",
                "display_name": "Hybrid Bike",
                "description": "Versatile bike for mixed terrain",
                "display_order": 30,
            },
            {
                "tag_type": "physical",
                "value": "type_gravel",
                "display_name": "Gravel Bike",
                "description": "Adventure bike for rough roads and light trails",
                "display_order": 25,
            },
            # Drivetrain Tags
            {
                "tag_type": "physical",
                "value": "drivetrain_1x",
                "display_name": "1x Drivetrain",
                "description": "Single front chainring setup",
                "display_order": 20,
            },
            {
                "tag_type": "physical",
                "value": "drivetrain_2x",
                "display_name": "2x Drivetrain",
                "description": "Double front chainring setup",
                "display_order": 15,
            },
            {
                "tag_type": "physical",
                "value": "drivetrain_3x",
                "display_name": "3x Drivetrain",
                "description": "Triple front chainring setup",
                "display_order": 10,
            },
            # Handlebar Type Tags
            {
                "tag_type": "physical",
                "value": "handlebar_flat",
                "display_name": "Flat Handlebars",
                "description": "Straight handlebars for upright riding",
                "display_order": 9,
            },
            {
                "tag_type": "physical",
                "value": "handlebar_drop",
                "display_name": "Drop Handlebars",
                "description": "Curved handlebars for aerodynamic positioning",
                "display_order": 8,
            },
            {
                "tag_type": "physical",
                "value": "handlebar_riser",
                "display_name": "Riser Handlebars",
                "description": "Elevated handlebars for comfortable upright position",
                "display_order": 7,
            },
            # Saddle Type Tags
            {
                "tag_type": "physical",
                "value": "saddle_comfort",
                "display_name": "Comfort Saddle",
                "description": "Extra padding for casual riding",
                "display_order": 6,
            },
            {
                "tag_type": "physical",
                "value": "saddle_sport",
                "display_name": "Sport Saddle",
                "description": "Balanced comfort and performance",
                "display_order": 5,
            },
            {
                "tag_type": "physical",
                "value": "saddle_performance",
                "display_name": "Performance Saddle",
                "description": "Lightweight and streamlined for speed",
                "display_order": 4,
            },
        ]

        # Create tags
        for tag_data in default_tags:
            tag, created = BikeCompatibilityTag.objects.get_or_create(
                tag_type=tag_data["tag_type"],
                value=tag_data["value"],
                defaults={
                    "display_name": tag_data["display_name"],
                    "description": tag_data.get("description", ""),
                    "display_order": tag_data.get("display_order", 0),
                },
            )

            if created:
                tags_created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created: [{tag.get_tag_type_display()}] {tag.display_name}"
                    )
                )
            else:
                tags_skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  - Skipped (already exists): [{tag.get_tag_type_display()}] {tag.display_name}"
                    )
                )

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(
            self.style.SUCCESS(f"✓ Created {tags_created} new compatibility tags")
        )
        if tags_skipped > 0:
            self.stdout.write(
                self.style.WARNING(f"- Skipped {tags_skipped} existing tags")
            )
        self.stdout.write(
            f"\nTotal tags in database: {BikeCompatibilityTag.objects.count()}"
        )
        self.stdout.write("=" * 70)
        self.stdout.write(
            "\nYou can now assign these tags to products in the Django admin or Staff Portal."
        )
        self.stdout.write(
            "To add custom tags, use the BikeCompatibilityTag admin interface.\n"
        )

