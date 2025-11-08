"""
Custom SocialAccountAdapter to handle multiple SocialApp entries gracefully.
"""
import logging
import mimetypes
import os
from urllib.parse import urlparse

import requests
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.apps import apps
from django.core.exceptions import MultipleObjectsReturned
from django.core.files.base import ContentFile
logger = logging.getLogger(__name__)



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

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)

        extra_data = sociallogin.account.extra_data or {}
        profile_image_url = self._extract_profile_image_url(
            sociallogin.account.provider, extra_data
        )

        if not profile_image_url:
            profile_image_url = sociallogin.account.get_avatar_url()

        if profile_image_url:
            self._update_user_profile_image(user, profile_image_url)
        else:
            logger.debug(
                "No profile image URL found for provider=%s user_id=%s",
                sociallogin.account.provider,
                user.id,
            )

        return user

    def _extract_profile_image_url(self, provider, extra_data):
        try:
            if provider == "google":
                return extra_data.get("picture")
            if provider == "facebook":
                picture_data = extra_data.get("picture")
                if isinstance(picture_data, dict):
                    data = picture_data.get("data")
                    if isinstance(data, dict):
                        return data.get("url")
            return None
        except Exception:
            logger.exception(
                "Failed to extract profile image URL for provider=%s", provider
            )
            return None

    def _update_user_profile_image(self, user, image_url):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            file_name = self._build_image_filename(user, image_url, response)
            content = ContentFile(response.content)

            UserProfile = apps.get_model("api", "UserProfile")

            user_profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "address": "",
                    "contact_number": "",
                },
            )

            if created or not user_profile.image:
                user_profile.image.save(file_name, content, save=True)
                logger.info(
                    "Stored social profile image for user_id=%s provider_url=%s",
                    user.id,
                    image_url,
                )
            else:
                logger.debug(
                    "Skipping social profile image update for user_id=%s; image already set",
                    user.id,
                )
        except Exception:
            logger.exception(
                "Failed to store social profile image for user_id=%s url=%s",
                user.id if user else "unknown",
                image_url,
            )

    def _build_image_filename(self, user, image_url, response):
        parsed = urlparse(image_url)
        base_name = os.path.basename(parsed.path)
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()

        if not base_name:
            base_name = f"{user.username or 'user'}_avatar.jpg"
        elif not os.path.splitext(base_name)[1] and content_type:
            guessed_ext = mimetypes.guess_extension(content_type)
            if guessed_ext:
                base_name = f"{base_name}{guessed_ext}"

        return base_name

