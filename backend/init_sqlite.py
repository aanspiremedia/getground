import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base
from app.models.user import User, OwnerRequest
from app.models.ground import Ground, GroundImage, Slot, GroundPricing
from app.models.booking import Booking, SlotBlock, Payment

def init_db():
    print("Creating tables in SQLite...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    init_db()
