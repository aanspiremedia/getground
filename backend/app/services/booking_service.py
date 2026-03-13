import logging
from sqlalchemy.orm import Session
from app.utils.redis_client import get_redis
from app.models.booking import Booking, BookingStatusEnum, Payment, PaymentStatusEnum
from app.models.ground import Slot, GroundPricing, PricingCategoryEnum
from datetime import datetime

logger = logging.getLogger(__name__)

class BookingService:
    def __init__(self, db: Session):
        self.db = db
        self.redis = get_redis()

    def check_slot_availability(self, ground_id: int, slot_id: int, booking_date: str, user_id: int = None) -> bool:
        """
        Check if a slot is available. 
        If user_id is provided, it allows the booking if the lock in Redis belongs to this user.
        """
        # 1. Check DB for existing bookings
        existing_booking = self.db.query(Booking).filter(
            Booking.ground_id == ground_id,
            Booking.slot_id == slot_id,
            Booking.booking_date == booking_date,
            Booking.status.in_([BookingStatusEnum.PENDING, BookingStatusEnum.CONFIRMED])
        ).first()
        if existing_booking:
            return False
            
        # 2. Check Redis for active locks
        lock_key = f"slot_lock:{ground_id}:{slot_id}:{booking_date}"
        lock_owner = self.redis.get(lock_key)
        
        if lock_owner:
            owner_id_str = lock_owner.decode() if hasattr(lock_owner, 'decode') else str(lock_owner)
            # If there's a lock, it's only "available" if the current user owns it
            if user_id and owner_id_str == str(user_id):
                return True
            return False
            
        return True

    def lock_slot(self, ground_id: int, slot_id: int, booking_date: str, user_id: int) -> bool:
        lock_key = f"slot_lock:{ground_id}:{slot_id}:{booking_date}"
        # If already locked by this user, just refresh expiry
        existing_owner = self.redis.get(lock_key)
        if existing_owner:
            owner_str = existing_owner.decode() if hasattr(existing_owner, 'decode') else str(existing_owner)
            if owner_str == str(user_id):
                self.redis.expire(lock_key, 300)
                return True
            
        # Otherwise try to set lock
        success = self.redis.setnx(lock_key, str(user_id))
        if success:
            self.redis.expire(lock_key, 300)
            return True
        return False

    def create_pending_booking(self, user_id: int, ground_id: int, slot_id: int, booking_date: str, category: str, amount: float, parent_id: int = None):
        try:
            if not self.check_slot_availability(ground_id, slot_id, booking_date, user_id):
                return {"success": False, "error": f"Slot {slot_id} on {booking_date} unavailable."}

            slot = self.db.query(Slot).filter(Slot.id == slot_id).first()
            if not slot:
                return {"success": False, "error": "Slot not found."}

            booking_dt = datetime.strptime(booking_date, "%Y-%m-%d") if isinstance(booking_date, str) else booking_date
            if not isinstance(booking_dt, datetime):
                booking_dt = datetime.combine(booking_dt, datetime.min.time())

            slot_start_dt = datetime.combine(booking_dt.date(), slot.start_time)
            slot_end_dt = datetime.combine(booking_dt.date(), slot.end_time)

            try:
                cat_enum = PricingCategoryEnum(category.upper())
            except Exception:
                cat_enum = PricingCategoryEnum.PRACTICE

            new_booking = Booking(
                user_id=user_id,
                ground_id=ground_id,
                slot_id=slot_id,
                booking_date=booking_dt,
                slot_start_time=slot_start_dt,
                slot_end_time=slot_end_dt,
                category=cat_enum,
                status=BookingStatusEnum.PENDING,
                total_amount=amount,
                parent_id=parent_id
            )
            self.db.add(new_booking)
            self.db.flush()

            # Only create Payment for the parent booking
            mock_order_id = None
            if not parent_id:
                mock_order_id = f"order_mock_{new_booking.id}"
                new_payment = Payment(
                    booking_id=new_booking.id,
                    razorpay_order_id=mock_order_id,
                    status=PaymentStatusEnum.PENDING,
                    amount=amount # This should be the consolidated amount for bulk bookings
                )
                self.db.add(new_payment)

            self.db.commit()

            return {
                "success": True,
                "booking_id": new_booking.id,
                "amount": amount,
                "razorpay_order_id": mock_order_id
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating pending booking: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def confirm_payment_and_booking(self, booking_id: int, razorpay_payment_id: str, razorpay_signature: str):
        # We assume the booking_id is the parent_id if it's a bulk booking
        booking = self.db.query(Booking).filter(Booking.id == booking_id).first()
        payment = self.db.query(Payment).filter(Payment.booking_id == booking_id).first()

        if not booking or not payment:
            return {"success": False, "error": "Booking or Payment record not found."}

        is_valid = razorpay_signature == "mock_signature_for_dev" or \
                   razorpay_payment_id.startswith("pay_Mock")

        if not is_valid:
            try:
                from app.utils.payment import verify_razorpay_signature
                is_valid = verify_razorpay_signature(payment.razorpay_order_id, razorpay_payment_id, razorpay_signature)
            except Exception:
                is_valid = False

        if is_valid:
            payment.status = PaymentStatusEnum.SUCCESS
            payment.razorpay_payment_id = razorpay_payment_id
            
            # Confirm THIS booking
            booking.status = BookingStatusEnum.CONFIRMED
            
            # Confirm all CHILD bookings
            child_bookings = self.db.query(Booking).filter(Booking.parent_id == booking_id).all()
            all_involved_bookings = [booking] + child_bookings
            
            for b in all_involved_bookings:
                b.status = BookingStatusEnum.CONFIRMED
                lock_key = f"slot_lock:{b.ground_id}:{b.slot_id}:{b.booking_date.isoformat() if hasattr(b.booking_date, 'isoformat') else b.booking_date}"
                self.redis.delete(lock_key)
            
            self.db.commit()
            return {"success": True, "booking_id": booking.id}
        else:
            payment.status = PaymentStatusEnum.FAILED
            self.db.commit()
            return {"success": False, "error": "Invalid signature"}

    def cancel_booking(self, booking_id: int, user_id: int):
        from datetime import timedelta
        booking = self.db.query(Booking).filter(Booking.id == booking_id, Booking.user_id == user_id).first()
        
        if not booking:
            return {"success": False, "error": "Booking not found."}
            
        if booking.status == BookingStatusEnum.CANCELLED:
            return {"success": False, "error": "Booking is already cancelled."}
            
        # Constraint: Cancellation allowed only if booking date is > 24 hours away
        now = datetime.now()
        if booking.slot_start_time <= now + timedelta(hours=24):
            return {"success": False, "error": "Cancellations are only permitted at least 24 hours before the slot begins."}
            
        # Nominal handling charge (10%)
        refund_amount = float(booking.total_amount) * 0.9
        handling_charge = float(booking.total_amount) * 0.1
        
        booking.status = BookingStatusEnum.CANCELLED
        self.db.commit()
        
        return {
            "success": True, 
            "message": f"Booking cancelled. A refund of ₹{refund_amount:.2f} will be processed after a 10% handling charge (₹{handling_charge:.2f}).",
            "refund_amount": refund_amount,
            "handling_charge": handling_charge
        }
