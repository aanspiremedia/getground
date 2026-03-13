from app.database import Base

# Import all models here so that Alembic can automatically discover them
from app.models.user import User, OwnerRequest
from app.models.ground import Ground, GroundImage, Slot, GroundPricing
from app.models.booking import Booking, Payment, SlotBlock
