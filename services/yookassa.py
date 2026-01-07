import uuid
import base64
import hashlib
import hmac
import json
import aiohttp
from datetime import datetime
from config import Config

class YooKassaService:
    def __init__(self):
        self.shop_id = Config.YUKASSA_SHOP_ID
        self.secret_key = Config.YUKASSA_SECRET_KEY
        self.base_url = "https://api.yookassa.ru/v3"
        self.auth = base64.b64encode(f"{self.shop_id}:{self.secret_key}".encode()).decode()
    
    async def create_payment(self, amount, description, return_url, metadata=None):
        """Создает платеж в YooKassa"""
        payment_id = str(uuid.uuid4())
        
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": Config.CURRENCY
            },
            "payment_method_data": {
                "type": "bank_card"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "capture": True,
            "description": description,
            "metadata": metadata or {}
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {self.auth}",
            "Idempotence-Key": payment_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/payments",
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "payment_id": payment_id,
                        "yookassa_id": data["id"],
                        "confirmation_url": data["confirmation"]["confirmation_url"],
                        "status": data["status"]
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"YooKassa error: {response.status} - {error_text}"
                    }
    
    async def get_payment_status(self, payment_id):
        """Получает статус платежа"""
        headers = {
            "Authorization": f"Basic {self.auth}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/payments/{payment_id}",
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "status": data["status"],
                        "amount": data["amount"],
                        "metadata": data.get("metadata", {})
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to get payment status: {response.status}"
                    }
    
    def verify_webhook_signature(self, body, signature):
        """Проверяет подпись вебхука от YooKassa"""
        # Для тестового режима пропускаем проверку подписи
        if self.secret_key.startswith('test_'):
            return True
            
        message = f"{body}"
        secret = self.secret_key.encode()
        signature_calculated = base64.b64encode(
            hmac.new(secret, message.encode(), hashlib.sha256).digest()
        ).decode()
        
        return signature_calculated == signature
    
    async def create_subscription_payment(self, user_id, plan_id, plan_name, amount, lang='ru'):
        """Создает платеж для подписки"""
        description_ru = f"Подписка {plan_name} на AI-модели"
        description_en = f"Subscription {plan_name} for AI models"
        description = description_ru if lang == 'ru' else description_en
        
        return_url = f"https://t.me/{Config.SUPPORT_USERNAME.replace('@', '')}"
        
        metadata = {
            "user_id": user_id,
            "plan_id": plan_id,
            "type": "subscription",
            "lang": lang
        }
        
        return await self.create_payment(amount, description, return_url, metadata)
    
    async def create_api_key_payment(self, user_id, model_id, model_name, amount, lang='ru'):
        """Создает платеж для API ключа"""
        description_ru = f"API ключ для модели {model_name} (750K токенов)"
        description_en = f"API key for model {model_name} (750K tokens)"
        description = description_ru if lang == 'ru' else description_en
        
        return_url = f"https://t.me/{Config.SUPPORT_USERNAME.replace('@', '')}"
        
        metadata = {
            "user_id": user_id,
            "model_id": model_id,
            "type": "api_key",
            "lang": lang
        }
        
        return await self.create_payment(amount, description, return_url, metadata)

# Глобальный экземпляр сервиса
yookassa_service = YooKassaService()
