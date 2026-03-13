import redis
try:
    r = redis.from_url("redis://localhost:6379/0")
    print(f"Ping: {r.ping()}")
except Exception as e:
    print(f"Connection failed: {e}")
