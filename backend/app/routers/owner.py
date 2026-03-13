from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import time as time_type

from app.database import get_db
from app.utils.auth import get_current_user, require_role
from app.models.user import User, RoleEnum, OwnerRequest
from app.models.ground import Ground, GroundStatusEnum, Slot, GroundPricing, PricingCategoryEnum
from app.models.booking import Booking

router = APIRouter(prefix="/owner", tags=["Owner"])

class GroundCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    city: str
    full_address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: Optional[List[str]] = None
    pricing: Optional[Dict[str, float]] = None
    images: List[str] # List of image URLs, min 3

class GroundUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    city: Optional[str] = None
    full_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    amenities: Optional[List[str]] = None

class SlotTemplateRequest(BaseModel):
    start_time: time_type
    end_time: time_type

class PricingRequest(BaseModel):
    category: PricingCategoryEnum
    price: float

@router.post("/request-role")
def request_owner_role(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == RoleEnum.OWNER:
        raise HTTPException(status_code=400, detail="User is already an owner")
        
    existing_req = db.query(OwnerRequest).filter(OwnerRequest.user_id == current_user.id).first()
    if existing_req:
        return {"message": f"Your request is currently {existing_req.status}"}
        
    new_req = OwnerRequest(user_id=current_user.id)
    db.add(new_req)
    db.commit()
    
    return {"message": "Owner role requested successfully. Pending admin approval."}

@router.post("/grounds")
def create_ground(request: GroundCreateRequest, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    if not request.images or len(request.images) < 3:
        raise HTTPException(status_code=400, detail="Minimum 3 images are compulsory")

    new_ground = Ground(
        owner_id=current_user.id,
        name=request.name,
        description=request.description,
        city=request.city,
        full_address=request.full_address,
        latitude=request.latitude,
        longitude=request.longitude,
        amenities=request.amenities,
        status=GroundStatusEnum.PENDING_APPROVAL
    )
    db.add(new_ground)
    db.flush() # Get the ground ID

    from app.models.ground import GroundImage
    for img_url in request.images:
        new_img = GroundImage(ground_id=new_ground.id, image_url=img_url)
        db.add(new_img)
    
    # Create default hourly slots (06:00 to 23:00)
    from datetime import time
    for hour in range(6, 23):
        default_slot = Slot(
            ground_id=new_ground.id,
            start_time=time(hour, 0),
            end_time=time(hour + 1, 0)
        )
        db.add(default_slot)
    
    # Save pricing if provided
    if request.pricing:
        for cat_str, price in request.pricing.items():
            try:
                cat_enum = PricingCategoryEnum(cat_str.upper())
                new_pricing = GroundPricing(
                    ground_id=new_ground.id,
                    category=cat_enum,
                    price=price
                )
                db.add(new_pricing)
            except Exception as e:
                print(f"Error adding pricing for category {cat_str}: {e}")
                
    db.commit()
    db.refresh(new_ground)
    return {"message": "Ground created successfully", "ground_id": new_ground.id, "status": new_ground.status.value}

@router.post("/grounds/{ground_id}/images")
def upload_ground_images(ground_id: int):
    # Dummy placeholder for S3 upload
    # Real implementation would use UploadFile and boto3
    return {"message": "Image uploaded successfully (stub)"}

@router.post("/grounds/{ground_id}/slots")
def add_slot_template(ground_id: int, request: SlotTemplateRequest, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found or not owned by user")
        
    new_slot = Slot(
        ground_id=ground.id,
        start_time=request.start_time,
        end_time=request.end_time
    )
    db.add(new_slot)
    db.commit()
    return {"message": "Slot template added"}

@router.post("/grounds/{ground_id}/pricing")
def set_pricing(ground_id: int, request: PricingRequest, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found or not owned by user")
        
    existing_price = db.query(GroundPricing).filter(GroundPricing.ground_id == ground.id, GroundPricing.category == request.category).first()
    if existing_price:
        existing_price.price = request.price
    else:
        new_price = GroundPricing(ground_id=ground.id, category=request.category, price=request.price)
        db.add(new_price)
    db.commit()
    return {"message": "Pricing updated"}

@router.get("/grounds")
def get_owner_grounds(current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    grounds = db.query(Ground).filter(Ground.owner_id == current_user.id).order_by(Ground.id).all()
    result = []
    for g in grounds:
        pricing = db.query(GroundPricing).filter(GroundPricing.ground_id == g.id).all()
        # Get first image if exists
        first_image = g.images[0].image_url if g.images else None
        
        # Calculate a display price (min or practice)
        display_price = 0
        if pricing:
            practice_p = next((p for p in pricing if p.category == PricingCategoryEnum.PRACTICE), None)
            if practice_p:
                display_price = float(practice_p.price)
            else:
                display_price = min([float(p.price) for p in pricing])
        
        result.append({
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "city": g.city,
            "full_address": g.full_address,
            "amenities": g.amenities,
            "status": g.status.value.lower() if hasattr(g.status, 'value') else str(g.status).lower(),
            "imageUrl": first_image,
            "price_per_hour": display_price,
            "pricing": [{"category": p.category.value.lower(), "price": float(p.price)} for p in pricing]
        })
    return result

@router.get("/grounds/{ground_id}")
def get_owner_ground(ground_id: int, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found or not owned by you")
    
    pricing = db.query(GroundPricing).filter(GroundPricing.ground_id == ground.id).all()
    # Serialize for frontend - use lowercase keys to match form fields
    return {
        "id": ground.id,
        "name": ground.name,
        "description": ground.description,
        "city": ground.city,
        "full_address": ground.full_address,
        "amenities": ground.amenities,
        "status": ground.status.value.lower() if hasattr(ground.status, 'value') else str(ground.status).lower(),
        "images": [{"image_url": img.image_url} for img in ground.images],
        "pricing": {p.category.value.lower(): float(p.price) for p in pricing}
    }

@router.put("/grounds/{ground_id}")
def update_ground(ground_id: int, request: GroundCreateRequest, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found or not owned by you")
    
    if not request.images or len(request.images) < 3:
        raise HTTPException(status_code=400, detail="Minimum 3 images are compulsory")

    ground.name = request.name
    ground.description = request.description
    ground.city = request.city
    ground.full_address = request.full_address
    ground.amenities = request.amenities

    # Update images
    from app.models.ground import GroundImage
    db.query(GroundImage).filter(GroundImage.ground_id == ground.id).delete()
    for img_url in request.images:
        new_img = GroundImage(ground_id=ground.id, image_url=img_url)
        db.add(new_img)
    
    # Update pricing if provided
    if request.pricing:
        for cat_str, price in request.pricing.items():
            try:
                cat_enum = PricingCategoryEnum(cat_str.upper())
                existing_p = db.query(GroundPricing).filter(GroundPricing.ground_id == ground.id, GroundPricing.category == cat_enum).first()
                if existing_p:
                    existing_p.price = price
                else:
                    new_p = GroundPricing(ground_id=ground.id, category=cat_enum, price=price)
                    db.add(new_p)
            except Exception as e:
                print(f"Error updating pricing: {e}")
    
    db.commit()
    return {"message": "Ground updated successfully"}

@router.delete("/grounds/{ground_id}")
def delete_ground(ground_id: int, current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    ground = db.query(Ground).filter(Ground.id == ground_id, Ground.owner_id == current_user.id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found or not owned by you")
    
    # Check for active bookings
    from app.models.booking import Booking, BookingStatusEnum
    active_bookings = db.query(Booking).filter(
        Booking.ground_id == ground_id, 
        Booking.status == BookingStatusEnum.CONFIRMED
    ).count()
    
    if active_bookings > 0:
        raise HTTPException(status_code=400, detail="Cannot delete ground with active confirmed bookings.")

    # Cleanup related records manually to avoid FK constraint issues if cascades aren't fully set
    from app.models.ground import GroundPricing, Slot, GroundImage
    from app.models.booking import SlotBlock
    
    db.query(GroundPricing).filter(GroundPricing.ground_id == ground_id).delete()
    db.query(SlotBlock).filter(SlotBlock.ground_id == ground_id).delete()
    db.query(Slot).filter(Slot.ground_id == ground_id).delete()
    db.query(GroundImage).filter(GroundImage.ground_id == ground_id).delete()
    
    db.delete(ground)
    db.commit()
    return {"message": "Ground deleted successfully"}

@router.get("/bookings")
def get_owner_bookings(current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    from app.models.ground import Ground
    from app.models.booking import Booking
    
    # Join bookings through owned grounds
    bookings = db.query(Booking).join(Ground).filter(Ground.owner_id == current_user.id).order_by(Booking.created_at.desc()).all()
    
    # Return serializable dicts
    result = []
    for b in bookings:
        result.append({
            "id": b.id,
            "player_id": b.user_id,
            "player_name": b.user.name if b.user else f"Player #{b.user_id}",
            "ground_id": b.ground_id,
            "ground_name": b.ground.name if b.ground else "Ground",
            "booking_date": str(b.booking_date.date() if hasattr(b.booking_date, 'date') else b.booking_date),
            "status": b.status.value,
            "total_amount": float(b.total_amount) if b.total_amount is not None else 0.0
        })
    return result

@router.get("/dashboard-metrics")
def get_dashboard_metrics(current_user: User = Depends(require_role([RoleEnum.OWNER])), db: Session = Depends(get_db)):
    from app.models.booking import Booking
    from app.models.ground import Ground
    from datetime import date, datetime
    
    bookings = db.query(Booking).join(Ground).filter(Ground.owner_id == current_user.id).all()
    today = date.today()
    
    total_bookings = len(bookings)
    
    def get_date_obj(d):
        if not d: return None
        if isinstance(d, datetime): return d.date()
        if isinstance(d, date): return d
        if isinstance(d, str):
            try: return datetime.strptime(d.split(' ')[0], '%Y-%m-%d').date()
            except: return None
        return None

    upcoming_bookings = [b for b in bookings if b.status == "confirmed" and get_date_obj(b.booking_date) and get_date_obj(b.booking_date) >= today]
    revenue = sum([float(b.total_amount) for b in bookings if b.status == "confirmed" and b.total_amount is not None])
    
    return {
        "total_bookings": total_bookings,
        "upcoming_bookings": len(upcoming_bookings),
        "revenue_estimate": revenue
    }
