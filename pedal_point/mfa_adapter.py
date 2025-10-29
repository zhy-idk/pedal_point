"""
Custom MFA Adapter for development
Disables email notifications to avoid Gmail rate limiting
"""

from allauth.mfa.adapter import DefaultMFAAdapter


class NoEmailMFAAdapter(DefaultMFAAdapter):
    """
    Custom MFA adapter that doesn't send notification emails.
    Useful during development to avoid email rate limiting.
    """
    
    def send_notification_mail(self, template_prefix, user):
        """
        Override to prevent sending TOTP activation notification emails.
        In production, you may want to re-enable this.
        """
        # Just log it instead of sending
        print(f"[DEV] Skipping MFA notification email for user: {user.email}")
        # Don't call super() to skip actual email sending
        pass

