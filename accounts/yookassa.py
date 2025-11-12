"""YooKassa payment integration"""
from yookassa import Configuration, Payment
from django.conf import settings
import uuid


def create_payment(amount, description, return_url, metadata=None):
    """Простая функция создания платежа в YooKassa"""
    
    # Настройка YooKassa
    Configuration.account_id = settings.YOOKASSA_SHOP_ID
    Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
    
    # Создание платежа
    payment = Payment.create({
        "amount": {
            "value": f"{float(amount):.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect", 
            "return_url": return_url
        },
        "capture": True,
        "description": description[:128],
        "metadata": metadata or {}
    }, str(uuid.uuid4()))  # idempotence key
    
    return {
        'id': payment.id,
        'confirmation_url': payment.confirmation.confirmation_url,
        'status': payment.status
    }
    