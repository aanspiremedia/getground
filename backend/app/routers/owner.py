from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import time as time_type, date as date_type

from app.database import get_db
from app.utils.auth import get_current_user, require_role
from app.models.user import User, RoleEnum, OwnerRequest
from app.models.ground import Ground, GroundStatusEnum, Slot, GroundPricing, PricingCategoryEnum, DurationTypeEnum
from app.models.booking import BookingSession, BookingStatusEnum, SessionTypeEnum
from app.services.booking_service import BookingService

router = APIRouter(prefix="/owner", tags=["Owner"])

class GroundCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    city: str
    full_address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: Optional[List[str]] = None
    pricing: Optional[Dict[str, Dict[str, float]]] = None
    images: List[str]

class OfflineBookingRequest(BaseModel):
    ground_id: int
    player_email: str
    # slots_per_day: { "2023-10-01": {"slot_ids": [1,2], "category": "practice", "session_type": "hourly", "amount": 500} }
    slots_per_day: Dict[str, Dict[str, Any]]
    note: Optional[str] = None

@router.post("/offline-booking")
def create_offline_booking(request: OfflineBookingRequest, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    service = BookingService(db)
    
    # Verify ground ownership
    ground = db.query(Ground).filter(Ground.id == request.ground_id, Ground.owner_id == current_user.id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found or not owned by you.")

    # Find or create a mock user for the player email if provided
    # For offline, we might just store the email in the note or link to a real user
    player = db.query(User).filter(User.email == request.player_email).first()
    player_id = player.id if player else current_user.id # fallback to owner if player not found (internal booking)

    date_strs = sorted(request.slots_per_day.keys())
    parent_id = None
    created_ids = []

    for i, d_str in enumerate(date_strs):
        day_info = request.slots_per_day[d_str]
        res = service.create_unified_booking(
            user_id=player_id,
            ground_id=request.ground_id,
            slot_ids=day_info["slot_ids"],
            booking_date=d_str,
            category=day_info["category"],
            session_type=day_info["session_type"],
            total_amount=day_info["amount"],
            is_offline=True,
            note=request.note,
            parent_id=parent_id
        )
        if not res["success"]:
            raise HTTPException(status_code=400, detail=res["error"])
        
        created_ids.append(res["session_id"])
        if i == 0:
            parent_id = res["session_id"]

    return {"message": "Offline booking created successfully", "session_ids": created_ids}

@router.get("/grounds")
def get_owner_grounds(current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    grounds = db.query(Ground).filter(Ground.owner_id == current_user.id).order_by(Ground.id).all()
    result = []
    for g in grounds:
        pricing_dict = {}
        for p in g.pricing:
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
            "status": g.status.value.lower(),
            "imageUrl": g.images[0].image_url if g.images else None,
            "pricing": pricing_dict
        })
    return result

@router.get("/grounds/{ground_id}")
def get_owner_ground(ground_id: int, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Not found")
    
    pricing_dict = {}
    for p in ground.pricing:
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
        "status": ground.status.value.lower(),
        "images": [{"image_url": img.image_url} for img in ground.images],
        "pricing": pricing_dict,
        "slots": [{"id": s.id, "start_time": str(s.start_time), "end_time": str(s.end_time), "is_active": s.is_active} for s in ground.slots]
    }

@router.get("/bookings")
def get_owner_bookings(current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    # Return root sessions (parent_id is null) for owned grounds
    sessions = db.query(BookingSession).join(Ground).filter(
        Ground.owner_id == current_user.id,
        BookingSession.parent_id == None
    ).order_by(BookingSession.created_at.desc()).all()
    
    result = []
    for s in sessions:
        # For multi-day, aggregate dates
        all_days = [str(s.booking_date)]
        children = db.query(BookingSession).filter(BookingSession.parent_id == s.id).all()
        for child in children:
            all_days.append(str(child.booking_date))
        
        # Calculate true total amount for the whole transaction
        total_revenue = float(s.total_amount)
        for child in children:
            total_revenue += float(child.total_amount)

        result.append({
            "id": s.id,
            "player_name": s.user.name or s.user.email if s.user else "Unknown",
            "ground_name": s.ground.name,
            "booking_dates": all_days,
            "status": s.status.value,
            "total_amount": total_revenue,
            "is_offline": bool(s.is_offline),
            "session_type": s.session_type.value,
            "created_at": s.created_at.isoformat()
        })
    return result

@router.get("/dashboard-metrics")
def get_dashboard_metrics(current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    from datetime import date
    
    # We only count root sessions to avoid over-counting multi-day as separate bookings
    sessions = db.query(BookingSession).join(Ground).filter(
        Ground.owner_id == current_user.id,
        BookingSession.parent_id == None
    ).all()
    
    confirmed = [s for s in sessions if s.status == BookingStatusEnum.CONFIRMED]
    
    # Revenue needs to include children amounts if they exist (though usually parent holds it)
    total_rev = 0
    for s in confirmed:
        total_rev += float(s.total_amount)
        # Sum children if they have values (rare in current split but good for safety)
        children = db.query(BookingSession).filter(BookingSession.parent_id == s.id, BookingSession.status == BookingStatusEnum.CONFIRMED).all()
        for child in children:
            total_rev += float(child.total_amount)

    today = date.today()
    upcoming = [s for s in confirmed if s.booking_date >= today]
    
    return {
        "total_bookings": len(sessions),
        "upcoming_bookings": len(upcoming),
        "revenue_estimate": total_rev
    }

# --- Standard ground CRUD ---
@router.post("/grounds")
def create_ground(request: GroundCreateRequest, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    new_ground = Ground(
        owner_id=current_user.id,
        name=request.name,
        description=request.description,
        city=request.city,
        full_address=request.full_address,
        amenities=request.amenities,
        status=GroundStatusEnum.PENDING_APPROVAL
    )
    db.add(new_ground)
    db.flush()

    from app.models.ground import GroundImage
    for img_url in request.images:
        db.add(GroundImage(ground_id=new_ground.id, image_url=img_url))
    
    from datetime import time
    for hour in range(6, 23):
        db.add(Slot(ground_id=new_ground.id, start_time=time(hour, 0), end_time=time(hour + 1, 0)))
    
    if request.pricing:
        for cat_str, duration_prices in request.pricing.items():
            try:
                cat_enum = next(c for c in PricingCategoryEnum if c.value.lower() == cat_str.lower())
                for dur_str, price in duration_prices.items():
                    dur_enum = next(d for d in DurationTypeEnum if d.value.lower() == dur_str.lower())
                    db.add(GroundPricing(ground_id=new_ground.id, category=cat_enum, duration_type=dur_enum, price=price))
            except: pass
                
    db.commit()
    return {"message": "Success", "ground_id": new_ground.id}

@router.put("/grounds/{ground_id}")
def update_ground(ground_id: int, request: GroundCreateRequest, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground: raise HTTPException(status_code=404)
    
    ground.name = request.name
    ground.description = request.description
    ground.city = request.city
    ground.full_address = request.full_address
    ground.amenities = request.amenities

    from app.models.ground import GroundImage
    db.query(GroundImage).filter(GroundImage.ground_id == ground.id).delete()
    for img_url in request.images:
        db.add(GroundImage(ground_id=ground.id, image_url=img_url))
    
    if request.pricing:
        db.query(GroundPricing).filter(GroundPricing.ground_id == ground.id).delete()
        for cat_str, duration_prices in request.pricing.items():
            try:
                cat_enum = next(c for c in PricingCategoryEnum if c.value.lower() == cat_str.lower())
                for dur_str, price in duration_prices.items():
                    dur_enum = next(d for d in DurationTypeEnum if d.value.lower() == dur_str.lower())
                    db.add(GroundPricing(ground_id=ground.id, category=cat_enum, duration_type=dur_enum, price=price))
            except: pass
    
    db.commit()
    return {"message": "Updated"}

@router.delete("/grounds/{ground_id}")
def delete_ground(ground_id: int, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground: raise HTTPException(status_code=404)
    
    confirmed = db.query(BookingSession).filter(BookingSession.ground_id == ground_id, BookingSession.status == BookingStatusEnum.CONFIRMED).count()
    if confirmed > 0: raise HTTPException(status_code=400, detail="Active bookings exist.")

    from app.models.ground import GroundPricing, Slot, GroundImage
    db.query(GroundPricing).filter(GroundPricing.ground_id == ground_id).delete()
    db.query(Slot).filter(Slot.ground_id == ground_id).delete()
    db.query(BookingSession).filter(BookingSession.ground_id == ground_id).delete()
    db.query(GroundImage).filter(GroundImage.ground_id == ground_id).delete()
    
    db.delete(ground)
    db.commit()
    return {"message": "Deleted"}
