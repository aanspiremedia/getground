import logging

logger = logging.getLogger(__name__)

def send_email_otp(email: str, otp: str):
    """
    Mock Email sending using SMTP or logger for development.
    In production, use aio-libs/aiosmtplib or similar.
    """
    # For development, we just log it.
    logger.info(f"========= MOCK EMAIL =========")
    logger.info(f"To: {email}")
    logger.info(f"Subject: Your GetGround Login OTP")
    logger.info(f"Body: Use code {otp} to login. Valid for 5 minutes.")
    logger.info(f"==============================")
    
    # Optional: the prompt mentioned using contact@aanspire.com 
    # as a temporary testing email. If configured, you can send real emails from it here.
    return True
