from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date as date_type

from app.database import get_db
from app.models.ground import Ground, Slot, GroundPricing, GroundStatusEnum
from app.models.booking import Booking, BookingStatusEnum, SlotBlock
from app.utils.redis_client import get_redis

router = APIRouter(prefix="/grounds", tags=["Grounds"])

@router.get("")
def get_all_grounds(db: Session = Depends(get_db)):
    """Returns all active and approved grounds for public discovery."""
    grounds = db.query(Ground).filter(
        Ground.is_active == True,
        Ground.status == GroundStatusEnum.APPROVED
    ).order_by(Ground.id).all()
    result = []
    for g in grounds:
        pricing = db.query(GroundPricing).filter(GroundPricing.ground_id == g.id).all()
        # Get first image if exists
        first_image = g.images[0].image_url if g.images else None
        pricing_dict = {}
        for p in pricing:
            cat_lower = p.category.value.lower()
            dur_lower = p.duration_type.value.lower()
            if cat_lower not in pricing_dict:
                pricing_dict[cat_lower] = {}
            pricing_dict[cat_lower][dur_lower] = float(p.price)
            
        result.append({
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "city": g.city,
            "full_address": g.full_address,
            "amenities": g.amenities,
            "status": g.status.value.lower() if hasattr(g.status, 'value') else str(g.status).lower(),
            "imageUrl": first_image,
            "pricing": pricing_dict,
        })
    return result

@router.get("/{ground_id}")
def get_ground_details(ground_id: int, db: Session = Depends(get_db)):
    """Returns details for a specific ground including per-category pricing and slots."""
    ground = db.query(Ground).filter(
        Ground.id == ground_id,
        Ground.is_active == True,
        Ground.status == GroundStatusEnum.APPROVED
    ).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found")
    
    pricing = db.query(GroundPricing).filter(GroundPricing.ground_id == ground_id).all()
    slots = db.query(Slot).filter(Slot.ground_id == ground_id, Slot.is_active == True).all()
    
    pricing_dict = {}
    for p in pricing:
        cat_lower = p.category.value.lower()
        dur_lower = p.duration_type.value.lower()
        if cat_lower not in pricing_dict:
            pricing_dict[cat_lower] = {}
        pricing_dict[cat_lower][dur_lower] = float(p.price)
        
    return {
        "id": ground.id,
        "name": ground.name,
        "description": ground.description,
        "city": ground.city,
        "full_address": ground.full_address,
        "amenities": ground.amenities,
        "status": ground.status.value,
        "images": [{"image_url": img.image_url} for img in ground.images],
        "pricing": pricing_dict,
        "slots": [{"id": s.id, "start_time": s.start_time.isoformat(), "end_time": s.end_time.isoformat()} for s in slots]
    }

from typing import Optional
from app.services.booking_service import BookingService

@router.get("/{ground_id}/availability")
def get_ground_availability(ground_id: int, date: date_type, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Returns available, locked, and booked slots for a given ground on a specific date."""
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.is_active == True).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found")

    service = BookingService(db)
    slots = db.query(Slot).filter(Slot.ground_id == ground_id, Slot.is_active == True).all()

    blocks = db.query(SlotBlock).filter(
        SlotBlock.ground_id == ground_id,
        SlotBlock.date == date
    ).all()
    blocked_slot_ids = {block.slot_id for block in blocks}
    
    response_slots = []
    date_str = date.isoformat()

    for slot in slots:
        slot_status = "available"
        if slot.id in blocked_slot_ids:
            slot_status = "blocked"
        else:
            # Use unified service logic
            is_avail = service.check_slot_availability(ground_id, slot.id, date_str, user_id)
            if not is_avail:
                # If not available, check if it's because of a lock vs a confirmed booking
                # This is slightly inefficient but keeps logic centralized
                existing_confirmed = db.query(Booking).filter(
                    Booking.ground_id == ground_id,
                    Booking.slot_id == slot.id,
                    Booking.booking_date == date,
                    Booking.status == BookingStatusEnum.CONFIRMED
                ).first()
                
                if existing_confirmed:
                    slot_status = "booked"
                else:
                    slot_status = "locked"

        response_slots.append({
            "slot": {
                "id": slot.id,
                "start_time": slot.start_time.isoformat(),
                "end_time": slot.end_time.isoformat(),
            },
            "status": slot_status
        })

    return {
        "ground_id": ground_id,
        "date": date.isoformat(),
        "slots": response_slots
    }
