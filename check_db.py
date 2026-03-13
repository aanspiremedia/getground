
import sys
import os
# Set CWD to backend to match relative paths in .env
os.chdir(os.path.join(os.getcwd(), 'backend'))
sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.models.user import User
from app.models.ground import Ground

db = SessionLocal()
try:
    users = db.query(User).all()
    print("--- USERS ---")
    for u in users:
        print(f"ID: {u.id}, Email: {u.email}, Role: {u.role}")
        
    grounds = db.query(Ground).all()
    print("\n--- GROUNDS ---")
    for g in grounds:
        print(f"ID: {g.id}, Name: {g.name}, OwnerID: {g.owner_id}, Status: {g.status}")
finally:
    db.close()
