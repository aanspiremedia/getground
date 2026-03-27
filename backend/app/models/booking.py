import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Numeric, Date, Text
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import text
from app.database import Base
from app.models.ground import PricingCategoryEnum


class BookingStatusEnum(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PaymentStatusEnum(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class SessionTypeEnum(str, enum.Enum):
    HOURLY = "hourly"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"
    FULL_DAY = "full_day"


# ─── NEW: One row per booking transaction ────────────────────────────────────────
class BookingSession(Base):
    """
    Represents a single booking transaction.
    One record per date booked (or one record for a multi-slot same-day session).
    For multi-day bookings, a parent_id links child sessions to the parent.
    """
    __tablename__ = "booking_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ground_id = Column(Integer, ForeignKey("grounds.id"), nullable=False)

    booking_date = Column(Date, nullable=False)               # The actual date of play
    category = Column(Enum(PricingCategoryEnum), nullable=False)
    session_type = Column(Enum(SessionTypeEnum), nullable=False, default=SessionTypeEnum.HOURLY)

    # Convenience: store start/end for the full block
    slot_start_time = Column(String(8), nullable=True)        # "06:00:00"
    slot_end_time = Column(String(8), nullable=True)          # "23:00:00"

    status = Column(Enum(BookingStatusEnum), default=BookingStatusEnum.PENDING)
    total_amount = Column(Numeric(10, 2), nullable=False, default=0)

    # Multi-day: child sessions link to a parent session
    parent_id = Column(Integer, ForeignKey("booking_sessions.id"), nullable=True)

    # Offline booking flag and note
    is_offline = Column(Integer, default=0)                   # 0 = online, 1 = offline
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    # Relationships
    user = relationship("User", back_populates="booking_sessions")
    ground = relationship("Ground", back_populates="booking_sessions")
    slot_usages = relationship("BookingSlotUsage", back_populates="session", cascade="all, delete-orphan")
    payment = relationship("BookingPayment", back_populates="session", uselist=False)
    parent = relationship("BookingSession", remote_side=[id], backref="children")


class BookingSlotUsage(Base):
    """
    Tracks which physical slots are reserved by a BookingSession.
    There is one row per slot per booking session.
    """
    __tablename__ = "booking_slot_usages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("booking_sessions.id", ondelete="CASCADE"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False)
    booking_date = Column(Date, nullable=False)

    # Relationships
    session = relationship("BookingSession", back_populates="slot_usages")
    slot = relationship("Slot")


class BookingPayment(Base):
    """One payment record per parent BookingSession."""
    __tablename__ = "booking_payments"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("booking_sessions.id"), nullable=False, unique=True)
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.PENDING)
    amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    session = relationship("BookingSession", back_populates="payment")


# ─── LEGACY: Keep old tables alive for migration compatibility ──────────────────
class Booking(Base):
    """Legacy table – kept for backward compatibility. New bookings use BookingSession."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ground_id = Column(Integer, ForeignKey("grounds.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False)
    booking_date = Column(DateTime(timezone=True), nullable=False)
    slot_start_time = Column(DateTime(timezone=True), nullable=False)
    slot_end_time = Column(DateTime(timezone=True), nullable=False)
    category = Column(Enum(PricingCategoryEnum), nullable=False)
    status = Column(Enum(BookingStatusEnum), default=BookingStatusEnum.PENDING)
    total_amount = Column(Numeric(10, 2), nullable=False)
    parent_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    user = relationship("User", back_populates="bookings")
    ground = relationship("Ground", back_populates="bookings")
    slot = relationship("Slot", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False)


class Payment(Base):
    """Legacy payment – kept for backward compatibility."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True, index=True)
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.PENDING)
    amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    booking = relationship("Booking", back_populates="payment")


class SlotBlock(Base):
    __tablename__ = "slot_blocks"

    id = Column(Integer, primary_key=True, index=True)
    ground_id = Column(Integer, ForeignKey("grounds.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    ground = relationship("Ground", back_populates="blocks")
    slot = relationship("Slot", back_populates="blocks")
