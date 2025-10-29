"""
Custom management command to run Django with WebSocket support using Daphne.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import os
import sys
import subprocess


class Command(BaseCommand):
    help = 'Start the Django development server with WebSocket support using Daphne'

    def add_arguments(self, parser):
        parser.add_argument(
            '--port',
            default='8000',
            help='Port to run the server on (default: 8000)',
        )
        parser.add_argument(
            '--host',
            default='0.0.0.0',
            help='Host to bind to (default: 0.0.0.0)',
        )

    def handle(self, *args, **options):
        port = options['port']
        host = options['host']
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting Django server with WebSocket support on {host}:{port}')
        )
        
        # Set the Django settings module environment variable
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pedal_point.settings')
        
        # Build the command
        cmd = [
            sys.executable, '-m', 'daphne',
            '-b', host,
            '-p', port,
            'pedal_point.asgi:application'
        ]
        
        try:
            # Run daphne as a subprocess
            subprocess.run(cmd, check=True)
            
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR('Daphne is not installed. Please install it with: pip install daphne')
            )
            sys.exit(1)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('\nServer stopped.')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error starting server: {e}')
            )
            sys.exit(1)
