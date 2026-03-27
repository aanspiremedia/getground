from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import date as date_type
from typing import Optional, List, Dict
from pydantic import BaseModel

from app.database import get_db
from app.services.booking_service import BookingService
from app.utils.auth import get_current_user
from app.models.user import User, RoleEnum
from app.models.booking import BookingSession, BookingStatusEnum

router = APIRouter(prefix="/bookings", tags=["Bookings"])

class SlotLockRequest(BaseModel):
    ground_id: int
    slot_ids: List[int]
    booking_dates: List[date_type]

class CreateBookingRequest(BaseModel):
    ground_id: int
    # slots_per_day: { "2023-10-01": [1, 2, 3], "2023-10-02": [4, 5] }
    slots_per_day: Optional[Dict[str, List[int]]] = None
    # For backward compatibility if single day
    slot_ids: Optional[List[int]] = None
    booking_dates: Optional[List[date_type]] = None
    
    category: str
    session_type: str = "hourly"
    total_amount: float = 0.0
    note: Optional[str] = None

class VerifyPaymentRequest(BaseModel):
    session_id: int # Changed from booking_id
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: str
    razorpay_signature: str

@router.post("/lock-slot")
def lock_slot(request: SlotLockRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = BookingService(db)
    for b_date in request.booking_dates:
        date_str = b_date.isoformat()
        for s_id in request.slot_ids:
            if not service.check_slot_availability(request.ground_id, s_id, date_str, current_user.id):
                raise HTTPException(status_code=400, detail=f"Slot {s_id} on {date_str} unavailable.")
            if not service.lock_slot(request.ground_id, s_id, date_str, current_user.id):
                raise HTTPException(status_code=409, detail=f"Slot {s_id} on {date_str} busy.")
    return {"message": "Locked"}

@router.post("")
def create_booking(request: CreateBookingRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = BookingService(db)
    
    # Normalize dates and slots
    # Map from date string to list of slots
    final_planner = request.slots_per_day
    if not final_planner:
        if request.slot_ids and request.booking_dates:
             final_planner = {d.isoformat(): request.slot_ids for d in request.booking_dates}
        else:
             raise HTTPException(status_code=400, detail="Invalid booking data.")

    date_strs = sorted(final_planner.keys())
    parent_session_id = None
    razorpay_order_id = None
    all_session_ids = []

    # Create sessions for each day
    # The first day is the parent and carries the FULL total_amount in its payment record
    for i, date_str in enumerate(date_strs):
        slot_ids = final_planner[date_str]
        res = service.create_unified_booking(
            user_id=current_user.id,
            ground_id=request.ground_id,
            slot_ids=slot_ids,
            booking_date=date_str,
            category=request.category,
            session_type=request.session_type,
            total_amount=request.total_amount if i == 0 else 0, # Only parent has the amount for online payment
            is_offline=False,
            note=request.note,
            parent_id=parent_session_id
        )
        
        if not res["success"]:
            # Potentially cleanup previously created sessions here if needed
            raise HTTPException(status_code=400, detail=res["error"])
        
        all_session_ids.append(res["session_id"])
        if i == 0:
            parent_session_id = res["session_id"]
            razorpay_order_id = res.get("razorpay_order_id")

    return {
        "session_id": parent_session_id, # Frontend should use this for payment
        "all_session_ids": all_session_ids,
        "razorpay_order_id": razorpay_order_id,
        "amount": request.total_amount
    }

@router.get("/me")
def get_my_bookings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Get top-level sessions (those without parent_id OR where parent_id == id)
    sessions = db.query(BookingSession).filter(
        BookingSession.user_id == current_user.id,
        BookingSession.parent_id == None
    ).order_by(BookingSession.created_at.desc()).all()
    
    result = []
    for s in sessions:
        result.append({
            "id": s.id,
            "ground_name": s.ground.name if s.ground else "Unknown",
            "booking_date": str(s.booking_date),
            "start_time": s.slot_start_time[:5],
            "end_time": s.slot_end_time[:5],
            "status": s.status.value,
            "total_amount": float(s.total_amount),
            "session_type": s.session_type.value,
            "is_offline": bool(s.is_offline)
        })
    return result

@router.post("/{session_id}/cancel")
def cancel_booking(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = BookingService(db)
    res = service.cancel_booking(session_id, current_user.id)
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.post("/verify-payment")
def verify_payment(request: VerifyPaymentRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    service = BookingService(db)
    res = service.confirm_payment_and_booking(
        session_id=request.session_id,
        razorpay_payment_id=request.razorpay_payment_id,
        razorpay_signature=request.razorpay_signature
    )
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res
