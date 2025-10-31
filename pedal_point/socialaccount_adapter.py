"""
Custom SocialAccountAdapter to handle multiple SocialApp entries gracefully.
"""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.core.exceptions import MultipleObjectsReturned


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter that handles cases where multiple SocialApp entries exist
    for the same provider by selecting the first one.
    """
    
    def get_app(self, request, provider, client_id=None):
        """
        Get SocialApp for a provider, handling MultipleObjectsReturned gracefully.
        """
        try:
            return super().get_app(request, provider, client_id)
        except MultipleObjectsReturned:
            # If multiple apps exist, get the first one for the current site
            from django.contrib.sites.models import Site
            site = Site.objects.get_current(request)
            
            apps = SocialApp.objects.filter(
                provider=provider,
                sites=site
            )
            
            if client_id:
                apps = apps.filter(client_id=client_id)
            
            # Return the first matching app
            app = apps.first()
            if app:
                return app
            
            # If no site-specific app, try without site filter
            apps = SocialApp.objects.filter(provider=provider)
            if client_id:
                apps = apps.filter(client_id=client_id)
            
            return apps.first()

