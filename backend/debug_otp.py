import requests

API_URL = "http://127.0.0.1:8000/api"

# Step 1: Send OTP
res = requests.post(f"{API_URL}/auth/send-otp", json={"email": "admin@getground.com"})
print(f"Send OTP status: {res.status_code}")
print(f"Send OTP body: {res.text}")

# Step 2: Get OTP from Redis
import redis
r = redis.from_url("redis://localhost:6379/0")
otp = r.get("otp:admin@getground.com")
print(f"OTP from Redis: {otp!r}")

# Step 3: Verify OTP
if otp:
    res2 = requests.post(f"{API_URL}/auth/verify-otp", json={"email": "admin@getground.com", "otp": otp})
    print(f"Verify OTP status: {res2.status_code}")
    print(f"Verify OTP body: {res2.text}")
