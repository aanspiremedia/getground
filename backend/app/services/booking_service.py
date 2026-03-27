import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.utils.redis_client import get_redis
from app.models.booking import (
    BookingSession, BookingSlotUsage, BookingPayment, 
    BookingStatusEnum, PaymentStatusEnum, SessionTypeEnum
)
from app.models.ground import Slot, PricingCategoryEnum
from datetime import datetime, date as date_type

logger = logging.getLogger(__name__)

class BookingService:
    def __init__(self, db: Session):
        self.db = db
        self.redis = get_redis()

    def check_slot_availability(self, ground_id: int, slot_id: int, booking_date: str, user_id: int = None) -> bool:
        """
        Check if a slot is available on a specific date.
        Checks new BookingSlotUsage, legacy Booking table, and active Redis locks.
        """
        try:
            b_date = datetime.strptime(booking_date, "%Y-%m-%d").date() if isinstance(booking_date, str) else booking_date
        except:
             b_date = booking_date # fallback for date_type
        
        # 1. Check NEW architecture (BookingSlotUsage)
        existing_usage = self.db.query(BookingSlotUsage).join(BookingSession).filter(
            BookingSlotUsage.slot_id == slot_id,
            BookingSlotUsage.booking_date == b_date,
            BookingSession.status.in_([BookingStatusEnum.PENDING, BookingStatusEnum.CONFIRMED])
        ).first()
        
        if existing_usage:
            session = existing_usage.session
            if session.status == BookingStatusEnum.CONFIRMED:
                return False
            # If PENDING, only available to the owner of the session
            if user_id and session.user_id == user_id:
                return True
            return False

        # 2. Check LEGACY architecture (Booking table)
        from app.models.booking import Booking
        legacy_booking = self.db.query(Booking).filter(
            Booking.ground_id == ground_id,
            Booking.slot_id == slot_id,
            Booking.booking_date == b_date,
            Booking.status.in_([BookingStatusEnum.PENDING, BookingStatusEnum.CONFIRMED])
        ).first()
        
        if legacy_booking:
            if legacy_booking.status == BookingStatusEnum.CONFIRMED:
                return False
            if user_id and legacy_booking.user_id == user_id:
                return True
            return False
            
        # 3. Check Redis locks
        lock_key = f"slot_lock:{ground_id}:{slot_id}:{booking_date}"
        lock_owner = self.redis.get(lock_key)
        
        if lock_owner:
            owner_id_str = lock_owner.decode() if hasattr(lock_owner, 'decode') else str(lock_owner)
            if user_id and owner_id_str == str(user_id):
                return True
            return False
            
        return True

    def lock_slot(self, ground_id: int, slot_id: int, booking_date: str, user_id: int) -> bool:
        lock_key = f"slot_lock:{ground_id}:{slot_id}:{booking_date}"
        existing_owner = self.redis.get(lock_key)
        if existing_owner:
            owner_str = existing_owner.decode() if hasattr(existing_owner, 'decode') else str(existing_owner)
            if owner_str == str(user_id):
                self.redis.expire(lock_key, 300)
                return True
        
        success = self.redis.setnx(lock_key, str(user_id))
        if success:
            self.redis.expire(lock_key, 300)
            return True
        return False

    def create_unified_booking(self, user_id: int, ground_id: int, slot_ids: list[int], 
                             booking_date: str, category: str, session_type: str, 
                             total_amount: float, is_offline: bool = False, note: str = None,
                             parent_id: int = None):
        """
        Creates ONE BookingSession and multiple BookingSlotUsage records.
        Returns the created session and status.
        """
        try:
            b_date = datetime.strptime(booking_date, "%Y-%m-%d").date() if isinstance(booking_date, str) else booking_date
            
            # Check availability for all slots first
            for s_id in slot_ids:
                if not self.check_slot_availability(ground_id, s_id, booking_date, user_id):
                    return {"success": False, "error": f"Slot {s_id} on {booking_date} is busy."}

            # Map category and session type to Enums
            cat_val = category.lower()
            try:
                # Direct check for Enum values
                cat_enum = next(c for c in PricingCategoryEnum if c.value.lower() == cat_val)
            except:
                cat_enum = PricingCategoryEnum.PRACTICE
            
            sess_val = session_type.lower()
            try:
                sess_enum = next(s for s in SessionTypeEnum if s.value.lower() == sess_val)
            except:
                sess_enum = SessionTypeEnum.HOURLY

            # Create session
            slots_data = self.db.query(Slot).filter(Slot.id.in_(slot_ids)).all()
            if not slots_data:
                return {"success": False, "error": "Slots not found."}
            
            sorted_slots = sorted(slots_data, key=lambda s: s.start_time)
            start_t = sorted_slots[0].start_time.isoformat()
            end_t = sorted_slots[-1].end_time.isoformat() if hasattr(sorted_slots[-1].end_time, 'isoformat') else str(sorted_slots[-1].end_time)

            new_session = BookingSession(
                user_id=user_id,
                ground_id=ground_id,
                booking_date=b_date,
                category=cat_enum,
                session_type=sess_enum,
                slot_start_time=start_t,
                slot_end_time=end_t,
                status=BookingStatusEnum.CONFIRMED if is_offline else BookingStatusEnum.PENDING,
                total_amount=total_amount,
                is_offline=1 if is_offline else 0,
                note=note,
                parent_id=parent_id
            )
            self.db.add(new_session)
            self.db.flush()

            # Create slot usage records
            for s_id in slot_ids:
                usage = BookingSlotUsage(
                    session_id=new_session.id,
                    slot_id=s_id,
                    booking_date=b_date
                )
                self.db.add(usage)
            
            # Create payment record
            mock_order_id = None
            if not is_offline:
                payment_amount = total_amount if not parent_id else 0
                mock_order_id = f"order_sess_{new_session.id}"
                
                new_payment = BookingPayment(
                    session_id=new_session.id,
                    razorpay_order_id=mock_order_id,
                    status=PaymentStatusEnum.PENDING,
                    amount=payment_amount
                )
                self.db.add(new_payment)

            self.db.commit()

            return {
                "success": True,
                "session_id": new_session.id,
                "amount": total_amount,
                "razorpay_order_id": mock_order_id,
                "status": "confirmed" if is_offline else "pending"
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating unified booking: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def confirm_payment_and_booking(self, session_id: int, razorpay_payment_id: str, razorpay_signature: str):
        session = self.db.query(BookingSession).filter(BookingSession.id == session_id).first()
        payment = self.db.query(BookingPayment).filter(BookingPayment.session_id == session_id).first()

        if not session or not payment:
            return {"success": False, "error": "Booking Session or Payment record not found."}

        is_valid = razorpay_payment_id.startswith("pay_Mock") or razorpay_signature == "mock_signature_for_dev"
        
        if is_valid:
            payment.status = PaymentStatusEnum.SUCCESS
            payment.razorpay_payment_id = razorpay_payment_id
            
            # Confirm THIS session
            session.status = BookingStatusEnum.CONFIRMED
            
            # Confirm all days (including self)
            all_sessions = self.db.query(BookingSession).filter(or_(BookingSession.id == session_id, BookingSession.parent_id == session_id)).all()
            for s in all_sessions:
                s.status = BookingStatusEnum.CONFIRMED
                # Clean redis locks
                for usage in s.slot_usages:
                    lock_key = f"slot_lock:{s.ground_id}:{usage.slot_id}:{s.booking_date.isoformat()}"
                    self.redis.delete(lock_key)

            self.db.commit()
            return {"success": True, "session_id": session.id}
        else:
            payment.status = PaymentStatusEnum.FAILED
            self.db.commit()
            return {"success": False, "error": "Invalid payment signature"}

    def cancel_booking(self, session_id: int, user_id: int):
        from datetime import timedelta
        # If it's a child, we must find the parent to cancel the whole session properly
        session = self.db.query(BookingSession).filter(BookingSession.id == session_id).first()
        if not session:
            return {"success": False, "error": "Booking not found."}
            
        if user_id and session.user_id != user_id:
             return {"success": False, "error": "Unauthorized."}

        if session.status == BookingStatusEnum.CANCELLED:
            return {"success": False, "error": "Already cancelled."}
            
        now = datetime.now()
        start_dt = datetime.combine(session.booking_date, datetime.strptime(session.slot_start_time, "%H:%M:%S").time())
        # Add 5h 30m if server time is UTC but booking is Nashik (IST) - for safety, assume booking start_time is local
        
        if start_dt <= now + timedelta(hours=24):
            return {"success": False, "error": "Cancellation window closed (< 24h)."}
            
        root_parent_id = session.parent_id or session.id
        all_related = self.db.query(BookingSession).filter(or_(BookingSession.id == root_parent_id, BookingSession.parent_id == root_parent_id)).all()
        
        total_refund_basis = 0
        for s in all_related:
            s.status = BookingStatusEnum.CANCELLED
            total_refund_basis += float(s.total_amount)
            
        refund_amount = total_refund_basis * 0.9
        
        self.db.commit()
        return {"success": True, "message": f"Cancelled successfully. Refund ₹{refund_amount:.2f} (10% fee)."}
