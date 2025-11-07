"""
Management command to update the Django Site domain to use HTTPS.
This ensures OAuth callbacks and other site-related URLs use the correct protocol.
"""
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
import os


class Command(BaseCommand):
    help = 'Updates the Django Site domain to match the production URL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--domain',
            type=str,
            help='Domain to set (e.g., pedal-point.onrender.com)',
        )
        parser.add_argument(
            '--name',
            type=str,
            help='Site name to set',
        )

    def handle(self, *args, **options):
        domain = options.get('domain') or os.getenv('BACKEND_URL', 'https://pedal-point.onrender.com')
        
        # Remove protocol from domain if present
        domain = domain.replace('https://', '').replace('http://', '')
        
        site_name = options.get('name') or 'Pedal Point'
        
        try:
            # Get the current site (SITE_ID = 1)
            site = Site.objects.get(pk=1)
            
            # Update the domain and name
            old_domain = site.domain
            old_name = site.name
            
            site.domain = domain
            site.name = site_name
            site.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully updated site:\n'
                    f'  Domain: {old_domain} → {domain}\n'
                    f'  Name: {old_name} → {site_name}'
                )
            )
            
            self.stdout.write(
                self.style.WARNING(
                    '\nIMPORTANT: Make sure your OAuth provider (Google, Facebook) has the following '
                    f'redirect URI authorized:\n'
                    f'  https://{domain}/accounts/google/login/callback/\n'
                    f'  https://{domain}/accounts/facebook/login/callback/'
                )
            )
            
        except Site.DoesNotExist:
            # Create the site if it doesn't exist
            site = Site.objects.create(
                pk=1,
                domain=domain,
                name=site_name
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created site:\n'
                    f'  Domain: {domain}\n'
                    f'  Name: {site_name}'
                )
            )
            
            self.stdout.write(
                self.style.WARNING(
                    '\nIMPORTANT: Make sure your OAuth provider (Google, Facebook) has the following '
                    f'redirect URI authorized:\n'
                    f'  https://{domain}/accounts/google/login/callback/\n'
                    f'  https://{domain}/accounts/facebook/login/callback/'
                )
            )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error updating site: {str(e)}')
            )

