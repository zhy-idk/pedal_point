"""
Custom OTP-enabled Admin Site for Pedal Point
Requires TOTP authentication for admin access
"""

from django_otp.admin import OTPAdminSite


class PedalPointOTPAdminSite(OTPAdminSite):
    """
    Custom admin site that requires OTP (TOTP) verification
    """
    site_header = "Pedal Point Administration (2FA Protected)"
    site_title = "Pedal Point Admin"
    index_title = "Welcome to Pedal Point Administration"


# Create the OTP-enabled admin site instance
otp_admin_site = PedalPointOTPAdminSite(name='otp_admin')

