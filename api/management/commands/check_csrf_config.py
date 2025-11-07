"""
Management command to check CSRF configuration and diagnose common issues.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.sites.models import Site


class Command(BaseCommand):
    help = 'Checks CSRF configuration and displays current settings'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== CSRF Configuration Check ===\n'))
        
        # Check basic CSRF settings
        self.stdout.write('📋 Basic CSRF Settings:')
        self._check_setting('CSRF_COOKIE_SECURE', settings.CSRF_COOKIE_SECURE)
        self._check_setting('CSRF_COOKIE_HTTPONLY', settings.CSRF_COOKIE_HTTPONLY)
        self._check_setting('CSRF_COOKIE_SAMESITE', settings.CSRF_COOKIE_SAMESITE)
        self._check_setting('CSRF_COOKIE_DOMAIN', settings.CSRF_COOKIE_DOMAIN)
        self._check_setting('CSRF_COOKIE_NAME', getattr(settings, 'CSRF_COOKIE_NAME', 'csrftoken'))
        self._check_setting('CSRF_USE_SESSIONS', getattr(settings, 'CSRF_USE_SESSIONS', False))
        
        # Check cookie security
        self.stdout.write('\n🔒 Cookie Security:')
        self._check_setting('SESSION_COOKIE_SECURE', settings.SESSION_COOKIE_SECURE)
        self._check_setting('SESSION_COOKIE_SAMESITE', settings.SESSION_COOKIE_SAMESITE)
        self._check_setting('SESSION_COOKIE_DOMAIN', settings.SESSION_COOKIE_DOMAIN)
        
        # Check proxy settings
        self.stdout.write('\n🔌 Proxy Settings:')
        self._check_setting('SECURE_PROXY_SSL_HEADER', 
                           getattr(settings, 'SECURE_PROXY_SSL_HEADER', None))
        self._check_setting('USE_X_FORWARDED_HOST', 
                           getattr(settings, 'USE_X_FORWARDED_HOST', False))
        
        # Check CORS
        self.stdout.write('\n🌐 CORS Settings:')
        self._check_setting('CORS_ALLOW_CREDENTIALS', settings.CORS_ALLOW_CREDENTIALS)
        self.stdout.write(f'  CORS_ALLOWED_ORIGINS:')
        for origin in settings.CORS_ALLOWED_ORIGINS:
            self.stdout.write(f'    • {origin}')
        
        # Check CSRF Trusted Origins
        self.stdout.write('\n✅ CSRF Trusted Origins:')
        csrf_trusted = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
        if csrf_trusted:
            for origin in csrf_trusted:
                # Check for invalid patterns
                if '*' in origin:
                    self.stdout.write(
                        self.style.ERROR(f'    ❌ INVALID (wildcard): {origin}')
                    )
                elif not origin.startswith(('http://', 'https://')):
                    self.stdout.write(
                        self.style.ERROR(f'    ❌ INVALID (missing protocol): {origin}')
                    )
                else:
                    self.stdout.write(f'    • {origin}')
        else:
            self.stdout.write(self.style.WARNING('    ⚠️  No trusted origins configured!'))
        
        # Check Django Site
        self.stdout.write('\n🏢 Django Site Configuration:')
        try:
            site = Site.objects.get(pk=getattr(settings, 'SITE_ID', 1))
            self.stdout.write(f'  Site Name: {site.name}')
            self.stdout.write(f'  Site Domain: {site.domain}')
            
            # Check if site domain matches backend URL
            backend_url = getattr(settings, 'BACKEND_URL', '')
            backend_domain = backend_url.replace('https://', '').replace('http://', '').rstrip('/')
            
            if site.domain != backend_domain:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n  ⚠️  Site domain ({site.domain}) does not match BACKEND_URL ({backend_domain})\n'
                        f'  Run: python manage.py update_site_domain'
                    )
                )
            else:
                self.stdout.write(self.style.SUCCESS('  ✓ Site domain matches BACKEND_URL'))
        except Site.DoesNotExist:
            self.stdout.write(self.style.ERROR('  ❌ Site not found! Run migrations.'))
        
        # Check environment
        self.stdout.write('\n🔧 Environment:')
        self._check_setting('IS_PRODUCTION', getattr(settings, 'IS_PRODUCTION', False))
        self._check_setting('DEBUG', settings.DEBUG)
        self._check_setting('BACKEND_URL', getattr(settings, 'BACKEND_URL', 'Not set'))
        self._check_setting('FRONTEND_URL', getattr(settings, 'FRONTEND_URL', 'Not set'))
        
        # Production recommendations
        is_production = getattr(settings, 'IS_PRODUCTION', False)
        if is_production or is_production == 'True':
            self.stdout.write('\n💡 Production Checklist:')
            issues = []
            
            if not settings.CSRF_COOKIE_SECURE:
                issues.append('  ❌ CSRF_COOKIE_SECURE should be True')
            
            if not settings.SESSION_COOKIE_SECURE:
                issues.append('  ❌ SESSION_COOKIE_SECURE should be True')
            
            if settings.CSRF_COOKIE_SAMESITE != 'None':
                issues.append('  ❌ CSRF_COOKIE_SAMESITE should be "None" for cross-origin')
            
            if settings.SESSION_COOKIE_SAMESITE != 'None':
                issues.append('  ❌ SESSION_COOKIE_SAMESITE should be "None" for cross-origin')
            
            if settings.CSRF_COOKIE_DOMAIN is not None:
                issues.append('  ❌ CSRF_COOKIE_DOMAIN should be None for cross-origin')
            
            if settings.SESSION_COOKIE_DOMAIN is not None:
                issues.append('  ❌ SESSION_COOKIE_DOMAIN should be None for cross-origin')
            
            if not getattr(settings, 'SECURE_PROXY_SSL_HEADER', None):
                issues.append('  ❌ SECURE_PROXY_SSL_HEADER not set (needed for Render/proxy)')
            
            if issues:
                for issue in issues:
                    self.stdout.write(self.style.ERROR(issue))
            else:
                self.stdout.write(self.style.SUCCESS('  ✓ All production checks passed!'))
        
        self.stdout.write('\n' + '='*60 + '\n')
    
    def _check_setting(self, name, value):
        """Helper to display a setting with appropriate styling"""
        if value is None:
            value_str = 'None'
            style = self.style.WARNING
        elif value is True:
            value_str = 'True'
            style = self.style.SUCCESS
        elif value is False:
            value_str = 'False'
            style = self.style.WARNING
        elif isinstance(value, (list, tuple)):
            value_str = f'{len(value)} items'
            style = self.style.SUCCESS
        else:
            value_str = str(value)
            style = lambda x: x
        
        self.stdout.write(f'  {name}: ' + style(value_str))

