"""
Management command to assign compatibility tags to existing bike builder products.
"""

from django.core.management.base import BaseCommand
from api.models import ProductListing, BikeCompatibilityTag


class Command(BaseCommand):
    help = "Assigns compatibility tags to existing bike builder products based on their specifications"

    def handle(self, *args, **options):
        self.stdout.write("Assigning compatibility tags to products...")
        
        # Get all tags by value for easy lookup
        tags = {tag.value: tag for tag in BikeCompatibilityTag.objects.all()}
        
        if not tags:
            self.stdout.write(self.style.ERROR(
                "No compatibility tags found! Please run 'python manage.py create_compatibility_tags' first."
            ))
            return
        
        updated = 0
        skipped = 0
        
        # Define product compatibility mappings
        product_mappings = {
            # FRAMES
            "City Cruiser Aluminum Frame": {
                "use_case": ["city"],
                "budget": ["budget"],
                "physical": ["material_aluminum", "disc_brake", "wheel_700c", "type_hybrid"]
            },
            "Urban Pro Carbon Frame": {
                "use_case": ["city"],
                "budget": ["mid"],
                "physical": ["material_carbon", "hydraulic_disc", "wheel_700c", "type_road"]
            },
            "Trail Blazer Aluminum Frame": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["material_aluminum", "disc_brake", "wheel_27_5", "type_mtb"]
            },
            "Mountain Master Carbon Frame": {
                "use_case": ["trail"],
                "budget": ["mid"],
                "physical": ["material_carbon", "hydraulic_disc", "wheel_29", "type_mtb"]
            },
            "Weekend Rider Steel Frame": {
                "use_case": ["casual"],
                "budget": ["budget"],
                "physical": ["material_steel", "rim_brake", "wheel_26", "type_hybrid"]
            },
            
            # WHEELS
            "City Alloy Wheels 700c": {
                "use_case": ["city"],
                "budget": ["budget"],
                "physical": ["wheel_700c", "disc_brake", "rim_brake", "material_alloy"]
            },
            "Trail Tough Wheels 27.5\"": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["wheel_27_5", "disc_brake", "material_alloy"]
            },
            "Casual Comfort Wheels 26\"": {
                "use_case": ["casual"],
                "budget": ["budget"],
                "physical": ["wheel_26", "rim_brake", "material_alloy"]
            },
            "Urban Disc Wheels 700c": {
                "use_case": ["city"],
                "budget": ["budget"],
                "physical": ["wheel_700c", "disc_brake", "material_alloy"]
            },
            "Trail Master Wheels 29\"": {
                "use_case": ["trail"],
                "budget": ["mid"],
                "physical": ["wheel_29", "disc_brake", "material_alloy"]
            },
            "Carbon Aero Wheels 700c": {
                "use_case": ["city"],
                "budget": ["mid"],
                "physical": ["wheel_700c", "hydraulic_disc", "material_carbon"]
            },
            
            # DRIVETRAIN
            "Shimano Tourney 7-Speed": {
                "use_case": ["city", "casual"],
                "budget": ["budget"],
                "physical": ["drivetrain_3x"]
            },
            "Shimano Altus 8-Speed MTB": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["drivetrain_3x"]
            },
            "Shimano Sora 9-Speed": {
                "use_case": ["city"],
                "budget": ["budget"],
                "physical": ["drivetrain_2x"]
            },
            "Shimano Deore 10-Speed MTB": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["drivetrain_2x"]
            },
            "SRAM GX Eagle 12-Speed": {
                "use_case": ["trail"],
                "budget": ["mid"],
                "physical": ["drivetrain_1x"]
            },
            "Shimano Ultegra 11-Speed": {
                "use_case": ["city"],
                "budget": ["mid"],
                "physical": ["drivetrain_2x"]
            },
            
            # BRAKES
            "Rim Brake Set": {
                "use_case": ["city", "casual"],
                "budget": ["budget"],
                "physical": ["rim_brake"]
            },
            "Mechanical Disc Brakes MTB": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["mechanical_disc", "disc_brake"]
            },
            "Mechanical Disc Brakes Urban": {
                "use_case": ["city"],
                "budget": ["budget"],
                "physical": ["mechanical_disc", "disc_brake"]
            },
            "Hydraulic Disc Brakes Trail": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["hydraulic_disc", "disc_brake"]
            },
            "Hydraulic Disc Brakes Urban": {
                "use_case": ["city"],
                "budget": ["budget"],
                "physical": ["hydraulic_disc", "disc_brake"]
            },
            
            # HANDLEBARS
            "Comfort Cruiser Bars": {
                "use_case": ["casual", "city"],
                "budget": ["budget"],
                "physical": ["handlebar_riser"]
            },
            "Trail Flat Bars": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["handlebar_flat"]
            },
            "Carbon Riser Bars": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["handlebar_riser", "material_carbon"]
            },
            
            # SADDLES
            "Comfort Plus Saddle": {
                "use_case": ["casual", "city"],
                "budget": ["budget"],
                "physical": ["saddle_comfort"]
            },
            "Trail Sport Saddle": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["saddle_sport"]
            },
            "Trail Pro Saddle": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["saddle_performance"]
            },
            "Pro Carbon Saddle": {
                "use_case": ["trail"],
                "budget": ["budget"],
                "physical": ["saddle_performance", "material_carbon"]
            },
        }
        
        # Process each product
        for product_name, tag_config in product_mappings.items():
            try:
                # Find the product listing
                listing = ProductListing.objects.filter(name=product_name).first()
                
                if not listing:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠ Product not found: {product_name}"
                    ))
                    skipped += 1
                    continue
                
                # Skip if not bike builder enabled
                if not listing.bike_builder_enabled:
                    self.stdout.write(self.style.WARNING(
                        f"  - Skipped (not bike builder): {product_name}"
                    ))
                    skipped += 1
                    continue
                
                # Collect tags to assign
                tags_to_assign = []
                
                # Add use case tags
                for use_case_value in tag_config.get("use_case", []):
                    if use_case_value in tags:
                        tags_to_assign.append(tags[use_case_value])
                
                # Add budget tags
                for budget_value in tag_config.get("budget", []):
                    if budget_value in tags:
                        tags_to_assign.append(tags[budget_value])
                
                # Add physical tags
                for physical_value in tag_config.get("physical", []):
                    if physical_value in tags:
                        tags_to_assign.append(tags[physical_value])
                
                # Assign tags
                if tags_to_assign:
                    listing.compatibility_tags.set(tags_to_assign)
                    updated += 1
                    
                    tag_names = [tag.display_name for tag in tags_to_assign]
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✓ {product_name}: {len(tags_to_assign)} tags assigned"
                    ))
                    self.stdout.write(f"    Tags: {', '.join(tag_names[:5])}{'...' if len(tag_names) > 5 else ''}")
                else:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠ No tags found for: {product_name}"
                    ))
                    skipped += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"  ✗ Error processing {product_name}: {str(e)}"
                ))
                skipped += 1
        
        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS(
            f"✓ Updated {updated} product(s) with compatibility tags"
        ))
        if skipped > 0:
            self.stdout.write(self.style.WARNING(f"- Skipped {skipped} product(s)"))
        self.stdout.write("=" * 70)
        self.stdout.write(
            "\nYou can now view and edit tags in the Django admin or Staff Portal.\n"
        )


