"""YooKassa webhooks handler."""
import json
from django.http import HttpResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

@csrf_exempt
@require_POST
def yookassa_webhook(request: HttpRequest) -> HttpResponse:
    """
    Обработчик уведомлений от YooKassa.
    """
    try:
        # Получаем данные из запроса
        event_json = json.loads(request.body.decode('utf-8'))
        print(f"=== YOOKASSA WEBHOOK RECEIVED ===")
        print(f"Event: {event_json}")
        
        # Обрабатываем событие
        event_type = event_json.get('event')
        payment_object = event_json.get('object', {})
        payment_id = payment_object.get('id')
        
        print(f"Payment ID: {payment_id}")
        print(f"Event type: {event_type}")
        
        if event_type == 'payment.succeeded':
            print("💰 Payment SUCCEEDED!")
            # Здесь ваша логика активации подписки
        elif event_type == 'payment.canceled':
            print("❌ Payment CANCELED")
        elif event_type == 'payment.waiting_for_capture':
            print("⏳ Payment WAITING")
        else:
            print(f"🤔 Unknown event: {event_type}")
        
        return HttpResponse(status=200)
        
    except Exception as e:
        print(f"🚨 Webhook error: {e}")
        return HttpResponse(status=500)