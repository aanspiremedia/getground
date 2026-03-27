import random
import logging
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        self.redis = get_redis()
        
    def generate_otp(self, email: str) -> str:
        """
        Generates a 6-digit OTP, stores it in Redis with 5 minutes TTL, and limits attempts.
        """
        email = email.lower().strip()
        # Rate limit check (e.g., max 3 requests per 5 minutes)
        attempts_key = f"otp_attempts:{email}"
        attempts = self.redis.get(attempts_key)
        if attempts and int(attempts) >= 3:
            raise Exception("Maximum OTP attempts reached. Please wait 5 minutes.")
            
        otp = str(random.randint(100000, 999999))
        
        # Store OTP
        otp_key = f"otp:{email}"
        self.redis.setex(otp_key, 300, otp) # 5 mins TTL
        
        # Increment attempts
        if not attempts:
            self.redis.setex(attempts_key, 300, 1)
        else:
            self.redis.incr(attempts_key)
            
        return otp
        
    def verify_otp(self, email: str, submitted_otp: str) -> bool:
        """
        Verifies the submitted OTP against Redis.
        """
        email = email.lower().strip()
        otp_key = f"otp:{email}"
        stored_otp = self.redis.get(otp_key)
        
        if not stored_otp:
            return False
        
        # Redis returns bytes - must decode to string before comparison
        stored_otp_str = stored_otp.decode('utf-8') if isinstance(stored_otp, bytes) else stored_otp
            
        if stored_otp_str.strip() == submitted_otp.strip():
            # Clear on success
            self.redis.delete(otp_key)
            self.redis.delete(f"otp_attempts:{email}")
            return True
        
        return False
