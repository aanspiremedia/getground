from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.services.auth_service import AuthService
from app.utils.email_client import send_email_otp
from app.utils.auth import create_access_token, get_current_user
from app.models.user import User, RoleEnum

router = APIRouter(prefix="/auth", tags=["Auth"])

class SendOTPRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

@router.post("/send-otp")
def send_otp(request: SendOTPRequest):
    auth_service = AuthService()
    try:
        otp = auth_service.generate_otp(request.email)
        # Mock send email
        send_email_otp(request.email, otp)
        return {"message": "OTP sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

@router.post("/verify-otp")
def verify_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    auth_service = AuthService()
    is_valid = auth_service.verify_otp(request.email, request.otp)
    
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        
    # Auto-create user if doesn't exist
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        user = User(email=request.email, role=RoleEnum.PLAYER)
        db.add(user)
        db.commit()
        db.refresh(user)
        
    # Generate JWT
    access_token = create_access_token(data={"sub": user.email, "role": user.role.value})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value
        }
    }

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    profile_picture: Optional[str] = None

@router.get("/me")
def get_user_profile(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "phone_number": current_user.phone_number,
        "profile_picture": current_user.profile_picture,
        "role": current_user.role.value
    }

@router.put("/profile")
def update_user_profile(
    request: UpdateProfileRequest, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if request.name is not None:
        current_user.name = request.name
    if request.phone_number is not None:
        current_user.phone_number = request.phone_number
    if request.profile_picture is not None:
        current_user.profile_picture = request.profile_picture
        
    db.commit()
    return {"message": "Profile updated successfully"}

@router.get("/dev-otp/{email}")
def get_dev_otp(email: str):
    """
    DEV ONLY: Returns the latest OTP for an email so the frontend can auto-fill it.
    Do not use in production!
    """
    from app.utils.redis_client import get_redis
    redis = get_redis()
    otp = redis.get(f"otp:{email}")
    if otp:
        # Decode bytes to string if necessary
        otp_str = otp.decode('utf-8') if isinstance(otp, bytes) else otp
        return {"otp": otp_str}
    raise HTTPException(status_code=404, detail="No OTP found for this email")
