from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.utils.auth import get_current_user, require_role
from app.models.user import User, RoleEnum, OwnerRequest
from app.models.ground import Ground, GroundStatusEnum
from app.models.booking import BookingSession, BookingStatusEnum

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/grounds")
def get_all_grounds(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    grounds = db.query(Ground).order_by(Ground.id).all()
    result = []
    for g in grounds:
        status_val = g.status.value if hasattr(g.status, 'value') else str(g.status)
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
            "owner_id": g.owner_id,
            "status": status_val.lower(),
            "pricing": pricing_dict,
            "images": [img.image_url for img in g.images]
        })
    return result

@router.get("/grounds/pending")
def get_pending_grounds(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    grounds = db.query(Ground).filter(Ground.status == GroundStatusEnum.PENDING_APPROVAL).order_by(Ground.id).all()
    result = []
    for g in grounds:
        status_val = g.status.value if hasattr(g.status, 'value') else str(g.status)
        result.append({
            "id": g.id,
            "name": g.name,
            "city": g.city,
            "owner_id": g.owner_id,
            "status": status_val.lower()
        })
    return result

@router.get("/users")
def get_all_users(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    users = db.query(User).all()
    return [{"id": u.id, "email": u.email, "name": u.name, "role": u.role.value if hasattr(u.role, 'value') else u.role} for u in users]

@router.get("/bookings")
def get_all_bookings(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    # Only return parent sessions for consolidation
    sessions = db.query(BookingSession).filter(BookingSession.parent_id == None).order_by(BookingSession.created_at.desc()).all()
    
    result = []
    for s in sessions:
        # Aggregate child dates
        all_dates = [str(s.booking_date)]
        children = db.query(BookingSession).filter(BookingSession.parent_id == s.id).all()
        for c in children:
            all_dates.append(str(c.booking_date))
        
        # Aggregate total revenue for the session
        total_revenue = float(s.total_amount)
        for c in children:
            total_revenue += float(c.total_amount)

        result.append({
            "id": s.id,
            "ground_id": s.ground_id,
            "ground_name": s.ground.name if s.ground else "Unknown",
            "player_name": s.user.name or s.user.email if s.user else "System",
            "booking_dates": all_dates,
            "status": s.status.value,
            "total_amount": total_revenue,
            "session_type": s.session_type.value,
            "is_offline": bool(s.is_offline)
        })
    return result

# --- Approval Handlers ---

@router.post("/grounds/{ground_id}/approve")
def approve_ground(ground_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    ground = db.query(Ground).filter(Ground.id == ground_id).first()
    if not ground: raise HTTPException(status_code=404, detail="Not found")
    ground.status = GroundStatusEnum.APPROVED
    db.commit()
    return {"message": "Approved"}

@router.post("/grounds/{ground_id}/reject")
def reject_ground(ground_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    ground = db.query(Ground).filter(Ground.id == ground_id).first()
    if not ground: raise HTTPException(status_code=404, detail="Not found")
    ground.status = GroundStatusEnum.REJECTED
    db.commit()
    return {"message": "Rejected"}

@router.get("/owner-requests/pending")
def get_pending_owner_requests(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    return db.query(OwnerRequest).filter(OwnerRequest.status == "pending").all()

@router.post("/owner-requests/{request_id}/approve")
def approve_owner_request(request_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    req = db.query(OwnerRequest).filter(OwnerRequest.id == request_id).first()
    if not req: raise HTTPException(status_code=404)
    req.status = "approved"
    req.user.role = RoleEnum.OWNER
    db.commit()
    return {"message": "Upgraded user to owner"}

@router.post("/grounds/{ground_id}/regenerate-slots")
def regenerate_slots(ground_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    from app.models.ground import Slot
    from datetime import time
    ground = db.query(Ground).filter(Ground.id == ground_id).first()
    if not ground: raise HTTPException(status_code=404)
    db.query(Slot).filter(Slot.ground_id == ground_id).delete()
    for hour in range(6, 23):
        db.add(Slot(ground_id=ground_id, start_time=time(hour, 0), end_time=time(hour + 1, 0), is_active=True))
    db.commit()
    return {"message": "Regenerated slots"}
