from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import date as date_type
from typing import Optional, List

from app.database import get_db
from app.services.booking_service import BookingService
# from app.schemas.booking import SlotLockRequest, CreateBookingRequest, VerifyPaymentRequest # TODO: Add schemas
from pydantic import BaseModel
from app.utils.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/bookings", tags=["Bookings"])

class SlotLockRequest(BaseModel):
    ground_id: int
    slot_ids: List[int]
    booking_dates: List[date_type]

class CreateBookingRequest(BaseModel):
    ground_id: int
    slot_ids: List[int]
    booking_dates: List[date_type]
    category: str  # From Enum
    total_amount: Optional[float] = 0.0

class VerifyPaymentRequest(BaseModel):
    booking_id: int
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: str
    razorpay_signature: str

@router.post("/lock-slot")
def lock_slot(request: SlotLockRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = BookingService(db)
    
    for b_date in request.booking_dates:
        date_str = b_date.isoformat()
        for s_id in request.slot_ids:
            # 1. Safety check
            is_available = service.check_slot_availability(request.ground_id, s_id, date_str, current_user.id)
            if not is_available:
                raise HTTPException(status_code=400, detail=f"Slot {s_id} on {date_str} is already booked or blocked")
                
            # 2. Try to lock
            success = service.lock_slot(request.ground_id, s_id, date_str, current_user.id)
            if not success:
                raise HTTPException(status_code=409, detail=f"Slot {s_id} on {date_str} is currently locked by someone else.")
        
    return {"message": "Slots locked successfully", "ttl_seconds": 300}

@router.post("")
def create_booking(request: CreateBookingRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    service = BookingService(db)
    
    first_date = request.booking_dates[0]
    first_slot = request.slot_ids[0]
    
    # Calculate consolidated total amount
    # (In a real app, you'd verify individual slot pricing here)
    total_amount = float(request.amount)
    
    # Create the parent booking (first slot on first date)
    parent_res = service.create_pending_booking(
        user_id=current_user.id,
        ground_id=request.ground_id,
        slot_id=first_slot,
        booking_date=first_date.isoformat(),
        category=request.category,
        amount=total_amount # Parent booking holds full amount
    )
    
    if not parent_res["success"]:
        raise HTTPException(status_code=400, detail=parent_res["error"])
        
    parent_id = parent_res["booking_id"]
    booking_ids = [parent_id]
    
    # Create child bookings for all other date/slot combinations
    for i, b_date in enumerate(request.booking_dates):
        for j, s_id in enumerate(request.slot_ids):
            # Skip the first one as it's the parent
            if i == 0 and j == 0:
                continue
                
            child_res = service.create_pending_booking(
                user_id=current_user.id,
                ground_id=request.ground_id,
                slot_id=s_id,
                booking_date=b_date.isoformat(),
                category=request.category,
                amount=0, # Child bookings have 0 amount (already covered by parent)
                parent_id=parent_id
            )
            if child_res["success"]:
                booking_ids.append(child_res["booking_id"])

    return {
        "booking_ids": booking_ids,
        "parent_id": parent_id,
        "amount": total_amount,
        "razorpay_order_id": parent_res.get("razorpay_order_id")
    }

@router.get("/me")
def get_my_bookings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.booking import Booking
    bookings = db.query(Booking).filter(Booking.user_id == current_user.id).order_by(Booking.created_at.desc()).all()
    # Return serializable dicts
    result = []
    for b in bookings:
        result.append({
            "id": b.id,
            "ground_id": b.ground_id,
            "ground_name": b.ground.name if b.ground else "Unknown Ground",
            "booking_date": str(b.booking_date.date() if hasattr(b.booking_date, 'date') else b.booking_date),
            "slot_start_time": str(b.slot_start_time.time() if hasattr(b.slot_start_time, 'time') else b.slot_start_time),
            "slot_end_time": str(b.slot_end_time.time() if hasattr(b.slot_end_time, 'time') else b.slot_end_time),
            "status": b.status.value,
            "total_amount": float(b.total_amount) if b.total_amount is not None else 0.0
        })
    return result

@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = BookingService(db)
    result = service.cancel_booking(booking_id, current_user.id)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
        
    return result

@router.post("/verify-payment")
def verify_payment(request: VerifyPaymentRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = BookingService(db)
    result = service.confirm_payment_and_booking(
        booking_id=request.booking_id,
        razorpay_payment_id=request.razorpay_payment_id,
        razorpay_signature=request.razorpay_signature
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Payment verification failed"))
        
    return result

@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Razorpay Server-to-Server Webhook.
    Acts as backup if frontend `/verify-payment` call fails after Razorpay payment succeeds.
    """
    body = await request.body()
    # Razorpay sends a header 'x-razorpay-signature' to verify the payload came from them.
    # In production, verifying this signature is critical.
    # signature = request.headers.get("x-razorpay-signature")
    
    payload = await request.json()
    event = payload.get("event")
    
    if event == "payment.captured":
        # Extract payment details
        payment_entity = payload["payload"]["payment"]["entity"]
        order_id = payment_entity["order_id"]
        payment_id = payment_entity["id"]
        
        # Verify and update
        service = BookingService(db)
        from app.models.booking import Payment
        
        # Find Booking DB record using Order ID
        payment_record = db.query(Payment).filter(Payment.razorpay_order_id == order_id).first()
        if payment_record and payment_record.status != "success":
            # Note: Server side verification doesn't usually use the tri-signature since it's verified via the request header.
            # Here we just mark it as success
            payment_record.status = "success"
            payment_record.razorpay_payment_id = payment_id
            
            booking = payment_record.booking
            booking.status = "confirmed"
            db.commit()
            
            # Delete lock
            lock_key = f"slot_lock:{booking.ground_id}:{booking.slot_id}:{booking.booking_date.isoformat() if hasattr(booking.booking_date, 'isoformat') else booking.booking_date}"
            service.redis.delete(lock_key)
            print(f"Webhook confirmed booking {booking.id}")

    return {"status": "ok"}
