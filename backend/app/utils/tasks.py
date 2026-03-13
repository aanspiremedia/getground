from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.booking import Booking, BookingStatusEnum

scheduler = BackgroundScheduler()

def cleanup_abandoned_bookings():
    db = SessionLocal()
    try:
        # Find pending bookings older than 10 minutes
        ten_mins_ago = datetime.utcnow() - timedelta(minutes=10)
        abandoned_bookings = db.query(Booking).filter(
            Booking.status == BookingStatusEnum.PENDING,
            Booking.created_at <= ten_mins_ago
        ).all()
        
        for booking in abandoned_bookings:
            booking.status = BookingStatusEnum.CANCELLED
            print(f"Cancelled abandoned booking {booking.id}")
            
        db.commit()
    except Exception as e:
        print(f"Error cleaning up bookings: {e}")
        db.rollback()
    finally:
        db.close()

def start_scheduler():
    # Run every 5 minutes
    scheduler.add_job(cleanup_abandoned_bookings, 'interval', minutes=5)
    scheduler.start()
