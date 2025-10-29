"""
Management command to process expired reservations.
Run this periodically (e.g., hourly via cron) to expire old reservations and activate next in queue.
"""
from django.core.management.base import BaseCommand
from api.utils import process_expired_reservations


class Command(BaseCommand):
    help = 'Process expired product reservations and activate next in queue'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Processing expired reservations...'))
        
        try:
            process_expired_reservations()
            self.stdout.write(self.style.SUCCESS('Successfully processed expired reservations'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error processing reservations: {str(e)}'))
            raise

