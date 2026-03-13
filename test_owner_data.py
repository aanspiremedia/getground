
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.database import SessionLocal
from app.models.user import User, RoleEnum
from app.models.ground import Ground
from app.models.booking import Booking
from datetime import date

db = SessionLocal()
try:
    user = db.query(User).filter(User.id == 2).first()
    print(f"User: {user.email}, Role: {user.role}")
    
    grounds = db.query(Ground).filter(Ground.owner_id == user.id).all()
    print(f"Grounds found: {len(grounds)}")
    
    for g in grounds:
        print(f" - {g.name} (ID: {g.id})")
        
    bookings = db.query(Booking).join(Ground).filter(Ground.owner_id == user.id).all()
    print(f"Bookings found: {len(bookings)}")
    
finally:
    db.close()
