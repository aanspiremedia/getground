import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Numeric, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
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

class Booking(Base):
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

    # Relationships
    user = relationship("User", back_populates="bookings")
    ground = relationship("Ground", back_populates="bookings")
    slot = relationship("Slot", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False)

    __table_args__ = (
        Index("ix_bookings_ground_date", "ground_id", "booking_date"),
        Index("ix_bookings_slot_date", "slot_id", "booking_date"),
    )

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True, index=True)
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)
    status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.PENDING)
    amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    # Relationships
    booking = relationship("Booking", back_populates="payment")

class SlotBlock(Base):
    __tablename__ = "slot_blocks"

    id = Column(Integer, primary_key=True, index=True)
    ground_id = Column(Integer, ForeignKey("grounds.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String, nullable=True) # e.g., "Maintenance", "Owner Blocked"
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    # Relationships
    ground = relationship("Ground", back_populates="blocks")
    slot = relationship("Slot", back_populates="blocks")
