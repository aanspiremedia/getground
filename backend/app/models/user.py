import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
from app.database import Base

class RoleEnum(str, enum.Enum):
    PLAYER = "player"
    OWNER = "owner"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False) # Primary auth for now
    phone_number = Column(String, unique=True, index=True, nullable=True) # Optional initially
    name = Column(String, nullable=True)
    profile_picture = Column(String, nullable=True)
    role = Column(Enum(RoleEnum), default=RoleEnum.PLAYER)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    # Relationships
    grounds = relationship("Ground", back_populates="owner")
    bookings = relationship("Booking", back_populates="user")
    booking_sessions = relationship("BookingSession", back_populates="user")
    owner_requests = relationship("OwnerRequest", back_populates="user")

class OwnerRequest(Base):
    __tablename__ = "owner_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    status = Column(String, default="pending") # pending / approved / rejected
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    user = relationship("User", back_populates="owner_requests")
