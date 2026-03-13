from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.utils.auth import get_current_user, require_role
from app.models.user import User, RoleEnum, OwnerRequest
from app.models.ground import Ground, GroundStatusEnum

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/grounds")
def get_all_grounds(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    grounds = db.query(Ground).order_by(Ground.id).all()
    # Ensure they have consistent serialization
    result = []
    for g in grounds:
        # Standardize status to lowercase and ensure it's a string
        status_val = g.status.value if hasattr(g.status, 'value') else str(g.status)
        
        # Get actual price (practice or min)
        from app.models.ground import GroundPricing, PricingCategoryEnum
        pricing = db.query(GroundPricing).filter(GroundPricing.ground_id == g.id, GroundPricing.category == PricingCategoryEnum.PRACTICE).first()
        price = float(pricing.price) if pricing else 1200.0
        
        result.append({
            "id": g.id,
            "name": g.name,
            "city": g.city,
            "owner_id": g.owner_id,
            "status": status_val.lower(),
            "price_per_hour": price
        })
    return result

@router.get("/grounds/pending")
def get_pending_grounds(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    from app.models.ground import GroundStatusEnum
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
    from app.models.booking import Booking
    bookings = db.query(Booking).all()
    return [{
        "id": b.id,
        "ground_id": b.ground_id,
        "booking_date": str(b.booking_date.date() if hasattr(b.booking_date, 'date') else b.booking_date),
        "status": b.status.value if hasattr(b.status, 'value') else b.status,
        "total_amount": float(b.total_amount) if b.total_amount is not None else 0.0
    } for b in bookings]

@router.post("/grounds/{ground_id}/approve")
def approve_ground(ground_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    ground = db.query(Ground).filter(Ground.id == ground_id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found")
        
    ground.status = GroundStatusEnum.APPROVED
    db.commit()
    return {"message": "Ground approved successfully"}

@router.post("/grounds/{ground_id}/reject")
def reject_ground(ground_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    ground = db.query(Ground).filter(Ground.id == ground_id).first()
    if not ground:
        raise HTTPException(status_code=404, detail="Ground not found")
        
    ground.status = GroundStatusEnum.REJECTED
    db.commit()
    return {"message": "Ground rejected successfully"}

@router.get("/owner-requests/pending")
def get_pending_owner_requests(db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    reqs = db.query(OwnerRequest).filter(OwnerRequest.status == "pending").all()
    return reqs

@router.post("/owner-requests/{request_id}/approve")
def approve_owner_request(request_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    req = db.query(OwnerRequest).filter(OwnerRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    req.status = "approved"
    user = req.user
    user.role = RoleEnum.OWNER
    db.commit()
    return {"message": "User upgraded to owner successfully"}

@router.post("/owner-requests/{request_id}/reject")
def reject_owner_request(request_id: int, db: Session = Depends(get_db), admin_user: User = Depends(require_role([RoleEnum.ADMIN]))):
    req = db.query(OwnerRequest).filter(OwnerRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    req.status = "rejected"
    db.commit()
    return {"message": "Owner request rejected"}
