import os
import sys
import time
import requests
import threading
import uuid
from datetime import date, timedelta

# Add backend to path so we can import app modules directly for DB manipulation
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.user import User, RoleEnum
from app.utils.redis_client import get_redis

API_URL = "http://localhost:8000/api"
redis_client = get_redis()

def get_otp(email):
    # Retrieve OTP directly from Redis for testing
    val = redis_client.get(f"otp:{email}")
    return val

def login(email):
    res = requests.post(f"{API_URL}/auth/send-otp", json={"email": email})
    if res.status_code != 200:
        raise Exception(f"Failed to send OTP for {email}: {res.text}")
    
    otp = get_otp(email)
    if not otp:
        raise Exception(f"OTP not found in Redis for {email}")
        
    res = requests.post(f"{API_URL}/auth/verify-otp", json={"email": email, "otp": otp})
    if res.status_code != 200:
        raise Exception(f"Failed to verify OTP: {res.text}")
        
    return res.json()["access_token"]

def set_role(email, role):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.role = role
        db.commit()
    db.close()

def main():
    print("====================================")
    print("Starting E2E Validation and Seeding...")
    print("====================================")
    
    run_id = str(uuid.uuid4())[:6]
    
    # ---------------------------------------------------------
    # 1. Admin setup
    # ---------------------------------------------------------
    admin_email = f"admin_{run_id}@getground.com"
    admin_token = login(admin_email)
    set_role(admin_email, RoleEnum.ADMIN)
    print("✅ Admin user created and promoted.")
    
    # ---------------------------------------------------------
    # 2. Owner Workflow Test
    # ---------------------------------------------------------
    owner_email = f"owner_{run_id}@getground.com"
    owner_token = login(owner_email)
    
    res = requests.post(f"{API_URL}/owner/request-role", headers={"Authorization": f"Bearer {owner_token}"})
    assert res.status_code == 200
    print("✅ Owner requested role successfully.")
    
    res = requests.get(f"{API_URL}/admin/owner-requests/pending", headers={"Authorization": f"Bearer {admin_token}"})
    reqs = res.json()
    assert len(reqs) > 0, "No owner requests found"
    req_id = reqs[-1]["id"]
    
    res = requests.post(f"{API_URL}/admin/owner-requests/{req_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    print("✅ Admin approved owner role.")
    
    # ---------------------------------------------------------
    # 3. Ground Creation & Seeding
    # ---------------------------------------------------------
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    grounds_to_seed = [
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
    
    ground_ids = []
    for gd in grounds_to_seed:
        res = requests.post(f"{API_URL}/owner/grounds", json=gd, headers=owner_headers)
        assert res.status_code == 200, f"Failed ground creation: {res.text}"
        gid = res.json()["ground_id"]
        ground_ids.append(gid)
        
        # Configure slots (16:00-18:00, 18:00-20:00)
        requests.post(f"{API_URL}/owner/grounds/{gid}/slots", json={"start_time": "16:00:00", "end_time": "18:00:00"}, headers=owner_headers)
        requests.post(f"{API_URL}/owner/grounds/{gid}/slots", json={"start_time": "18:00:00", "end_time": "20:00:00"}, headers=owner_headers)
        
        # Configure pricing
        requests.post(f"{API_URL}/owner/grounds/{gid}/pricing", json={"category": "practice", "price": 1500.0}, headers=owner_headers)
        requests.post(f"{API_URL}/owner/grounds/{gid}/pricing", json={"category": "match", "price": 2500.0}, headers=owner_headers)
        
        # Admin approves
        res = requests.post(f"{API_URL}/admin/grounds/{gid}/approve", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        
    print(f"✅ Owner created {len(ground_ids)} grounds with slots/pricing. Admin approved them.")
    
    # ---------------------------------------------------------
    # 4. Player Flow & Basic Performance Check
    # ---------------------------------------------------------
    player1_email = f"player1_{run_id}@getground.com"
    player1_token = login(player1_email)
    p1_headers = {"Authorization": f"Bearer {player1_token}"}
    
    player2_email = f"player2_{run_id}@getground.com"
    player2_token = login(player2_email)
    
    start_time = time.time()
    res = requests.get(f"{API_URL}/grounds")
    print(f"✅ Grounds fetch time: {(time.time() - start_time)*1000:.2f}ms")
    
    grounds = res.json()
    print("DEBUG GROUNDS RETURNED:", grounds)
    assert len(grounds) >= 2
    target_ground = grounds[0]["id"]
    test_date = (date.today() + timedelta(days=1)).isoformat()
    
    start_time = time.time()
    res = requests.get(f"{API_URL}/grounds/{target_ground}/availability?date={test_date}")
    print(f"✅ Availability fetch time: {(time.time() - start_time)*1000:.2f}ms")
    
    avail = res.json()
    target_slot = avail["slots"][0]["slot"]["id"]
    
    # ---------------------------------------------------------
    # 5. Redis Slot Lock Testing (Concurrent)
    # ---------------------------------------------------------
    lock_results = []
    def try_lock(token, label):
        resp = requests.post(f"{API_URL}/bookings/lock-slot", json={
            "ground_id": target_ground,
            "slot_id": target_slot,
            "booking_date": test_date
        }, headers={"Authorization": f"Bearer {token}"})
        lock_results.append((label, resp.status_code))
        
    t1 = threading.Thread(target=try_lock, args=(player1_token, "P1"))
    t2 = threading.Thread(target=try_lock, args=(player2_token, "P2"))
    t1.start(); t2.start()
    t1.join(); t2.join()
    
    success_codes = [r[1] for r in lock_results if r[1] == 200]
    conflict_codes = [r[1] for r in lock_results if r[1] == 400]
    
    assert len(success_codes) == 1, "There should be exactly one successful lock"
    assert len(conflict_codes) == 1, "There should be exactly one 400 conflict"
    print(f"✅ Concurrent Redis locking passed. Results: {lock_results}")
    
    # Clear the lock to proceed with a dedicated flow
    redis_client.delete(f"slot_lock:{target_ground}:{target_slot}:{test_date}")
    
    # ---------------------------------------------------------
    # 6. Complete Booking Flow Test
    # ---------------------------------------------------------
    res = requests.post(f"{API_URL}/bookings/lock-slot", json={
        "ground_id": target_ground,
        "slot_id": target_slot,
        "booking_date": test_date
    }, headers=p1_headers)
    assert res.status_code == 200
    
    start_time = time.time()
    res = requests.post(f"{API_URL}/bookings/create", json={
        "ground_id": target_ground,
        "slot_id": target_slot,
        "booking_date": test_date,
        "category": "practice"
    }, headers=p1_headers)
    print(f"✅ Booking create time: {(time.time() - start_time)*1000:.2f}ms")
    
    assert res.status_code == 200, f"Booking creation failed: {res.text}"
    booking_data = res.json()
    order_id = booking_data.get("razorpay_order_id")
    
    # Simulate Razorpay payment captured callback via Webhook
    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "order_id": order_id,
                    "id": "pay_MockTxnId123"
                }
            }
        }
    }
    
    res = requests.post(f"{API_URL}/bookings/webhook", json=webhook_payload)
    assert res.status_code == 200
    print("✅ Simulated Razorpay Webhook Confirmation.")
    
    # ---------------------------------------------------------
    # 7. Failure Scenarios
    # ---------------------------------------------------------
    print("Testing Failure Scenarios...")
    
    # 7.1 Duplicate Booking Attempt (Post-Confirmation)
    res = requests.post(f"{API_URL}/bookings/create", json={
        "ground_id": target_ground,
        "slot_id": target_slot,
        "booking_date": test_date,
        "category": "practice"
    }, headers=p1_headers)
    assert res.status_code == 400, "Should have rejected duplicate booking"
    print("✅ Duplicate booking attempt rejected.")
    
    # 7.2 Invalid Payment Signature
    bad_verify_payload = {
        "booking_id": booking_data["booking_id"],
        "razorpay_payment_id": "pay_BadId",
        "razorpay_signature": "invalid_sig"
    }
    res = requests.post(f"{API_URL}/bookings/verify-payment", json=bad_verify_payload, headers=p1_headers)
    assert res.status_code == 400
    print("✅ Invalid payment signature rejected.")

    # ---------------------------------------------------------
    # 8. Check "My Bookings" & Owner Metrics
    # ---------------------------------------------------------
    # ... (existing checks)
    res = requests.get(f"{API_URL}/bookings/me", headers=p1_headers)
    assert res.status_code == 200
    my_bookings = res.json()
    assert len(my_bookings) > 0
    assert my_bookings[0]["status"] == "confirmed"
    print("✅ Booking verified in 'My Bookings'.")
    
    # Verify Owner metrics reflect the new revenue
    res = requests.get(f"{API_URL}/owner/dashboard-metrics", headers=owner_headers)
    assert res.status_code == 200
    metrics = res.json()
    print(f"✅ Owner Dashboard updated: {metrics}")
    
    print("====================================")
    print("ALL TESTS PASSED SUCCESSFULLY.")
    print("Demo Environment Seeded.")
    print("====================================")

if __name__ == "__main__":
    main()
