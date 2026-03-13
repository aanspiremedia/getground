import os
import sys
import requests
from datetime import date, timedelta

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.user import User, RoleEnum
from app.utils.redis_client import get_redis

API_URL = "http://localhost:8000/api"
redis_client = get_redis()

def login(email):
    # Skip send-otp and just check redis or manually verify if user exists
    # For seeding, we'll just ensure the user exists and has the role
    print(f"Sending OTP to {email}")
    res1 = requests.post(f"{API_URL}/auth/send-otp", json={"email": email})
    if res1.status_code != 200:
        print(f"Failed to send OTP: {res1.status_code} {res1.text}")
        sys.exit(1)
        
    otp = redis_client.get(f"otp:{email}")
    print(f"Retrieved OTP from Redis: {otp!r}")
    if otp is None:
        print("No OTP found in Redis!")
        sys.exit(1)
    
    # Decode bytes to string if necessary
    otp_str = otp.decode('utf-8') if isinstance(otp, bytes) else str(otp)
    
    res = requests.post(f"{API_URL}/auth/verify-otp", json={"email": email, "otp": otp_str})
    if res.status_code != 200:
        print(f"Failed to verify OTP: {res.status_code} {res.text}")
        sys.exit(1)
        
    return res.json()["access_token"]

def set_role(email, role):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.role = role
        db.commit()
    db.close()

def seed():
    print("Seeding Demo Environment...")
    
    # 1. Ensure Admin
    admin_email = "admin@getground.com"
    token = login(admin_email)
    set_role(admin_email, RoleEnum.ADMIN)
    
    # 2. Ensure Owner
    owner_email = "owner@getground.com"
    owner_token = login(owner_email)
    set_role(owner_email, RoleEnum.OWNER)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    
    # 3. Add Grounds if they don't exist
    grounds = [
        {
            "name": "Maestro Cricket Arena",
            "description": "Premium floodlight stadium with real turf.",
            "city": "Nashik",
            "full_address": "Gangapur Road, Nashik",
            "amenities": ["Lights", "Parking", "Pavilion", "Washroom"]
        },
        {
            "name": "Spartans Sports Club",
            "description": "Excellently maintained pitch, perfect for Box Cricket.",
            "city": "Nashik",
            "full_address": "College Road, Nashik",
            "amenities": ["Parking", "Umpires", "Canteen"]
        }
    ]
    
    for gd in grounds:
        # Check if ground already exists to avoid duplicates on multiple runs
        res = requests.get(f"{API_URL}/grounds")
        existing = res.json()
        if any(g["name"] == gd["name"] for g in existing):
            print(f"Ground {gd['name']} already exists.")
            continue
            
        res = requests.post(f"{API_URL}/owner/grounds", json=gd, headers=owner_headers)
        if res.status_code == 200:
            gid = res.json()["ground_id"]
            # Add slots
            requests.post(f"{API_URL}/owner/grounds/{gid}/slots", json={"start_time": "16:00:00", "end_time": "18:00:00"}, headers=owner_headers)
            requests.post(f"{API_URL}/owner/grounds/{gid}/slots", json={"start_time": "18:00:00", "end_time": "20:00:00"}, headers=owner_headers)
            # Add pricing
            requests.post(f"{API_URL}/owner/grounds/{gid}/pricing", json={"category": "practice", "price": 1500.0}, headers=owner_headers)
            # Approve
            requests.post(f"{API_URL}/admin/grounds/{gid}/approve", headers={"Authorization": f"Bearer {token}"})
            print(f"✅ Seeded {gd['name']}")

    print("Demo Seeding Complete.")
    print(f"Admin: {admin_email}")
    print(f"Owner: {owner_email}")
    print(f"Player: player@getground.com (will be created on first login)")

if __name__ == "__main__":
    seed()
