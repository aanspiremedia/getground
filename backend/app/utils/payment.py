import razorpay
import os
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY = os.getenv("RAZORPAY_KEY", "test_key")
RAZORPAY_SECRET = os.getenv("RAZORPAY_SECRET", "test_secret")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY, RAZORPAY_SECRET))

def create_razorpay_order(amount: float, receipt: str, currency: str = "INR") -> dict:
    """
    amount: In rupees (will be converted to paise internally)
    receipt: Unique string identifier (like DB booking_id)
    """
    total_amount_paise = int(amount * 100)
    data = {
        "amount": total_amount_paise,
        "currency": currency,
        "receipt": str(receipt)
    }
    return razorpay_client.order.create(data=data)

def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    try:
        data = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }
        razorpay_client.utility.verify_payment_signature(data)
        return True
    except Exception as e:
        return False
