import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Time, Enum, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
from app.database import Base

class GroundStatusEnum(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"

class Ground(Base):
    __tablename__ = "grounds"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    city = Column(String, nullable=False)
    full_address = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    amenities = Column(JSON, nullable=True) # e.g. ["lights", "parking"]
    status = Column(Enum(GroundStatusEnum), default=GroundStatusEnum.PENDING_APPROVAL)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'))

    # Relationships
    owner = relationship("User", back_populates="grounds")
    images = relationship("GroundImage", back_populates="ground")
    slots = relationship("Slot", back_populates="ground")
    pricing = relationship("GroundPricing", back_populates="ground")
    bookings = relationship("Booking", back_populates="ground")
    blocks = relationship("SlotBlock", back_populates="ground")

class GroundImage(Base):
    __tablename__ = "ground_images"

    id = Column(Integer, primary_key=True, index=True)
    ground_id = Column(Integer, ForeignKey("grounds.id"), nullable=False)
    image_url = Column(String, nullable=False)

    # Relationships
    ground = relationship("Ground", back_populates="images")

class Slot(Base):
    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, index=True)
    ground_id = Column(Integer, ForeignKey("grounds.id"), nullable=False)
    start_time = Column(Time, nullable=False) # e.g., 09:00:00 (template)
    end_time = Column(Time, nullable=False) # e.g., 10:00:00
    is_active = Column(Boolean, default=True)

    # Relationships
    ground = relationship("Ground", back_populates="slots")
    bookings = relationship("Booking", back_populates="slot")
    blocks = relationship("SlotBlock", back_populates="slot")

class PricingCategoryEnum(str, enum.Enum):
    PRACTICE = "PRACTICE"
    MATCH = "MATCH"
    TOURNAMENT = "TOURNAMENT"
    CORPORATE = "CORPORATE"
    FULL_DAY = "FULL_DAY"

class GroundPricing(Base):
    __tablename__ = "ground_pricing"

    id = Column(Integer, primary_key=True, index=True)
    ground_id = Column(Integer, ForeignKey("grounds.id"), nullable=False)
    category = Column(Enum(PricingCategoryEnum), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    # Relationships
    ground = relationship("Ground", back_populates="pricing")
