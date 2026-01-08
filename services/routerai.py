import aiohttp
import asyncio
import base64
from io import BytesIO
from config import Config

class RouterAIService:
    def __init__(self):
        self.api_key = Config.ROUTERAI_API_KEY
        self.base_url = Config.ROUTERAI_ENDPOINT
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def send_message(self, model_id, message, conversation_history=None, extra_data=None):
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ],
            "stream": False
        }
        
        if conversation_history:
            payload["messages"] = conversation_history + payload["messages"]
        
        if extra_data and "image" in extra_data:
            payload["messages"][0]["content"] = [
                {
                    "type": "text",
                    "text": message
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{extra_data['image']}"
                    }
                }
            ]
        
        try:
            # Увеличиваем таймаут до 120 секунд
            timeout = aiohttp.ClientTimeout(total=120)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self.headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        # Безопасное извлечение ответа
                        if "choices" in data and len(data["choices"]) > 0:
                            response_content = data["choices"][0].get("message", {}).get("content", "")
                            # Очистка ответа от XML тегов
                            cleaned_response = self.clean_response(response_content)
                            
                            return {
                                "success": True,
                                "response": cleaned_response,
                                "usage": data.get("usage", {})
                            }
                        else:
                            return {
                                "success": False,
                                "error": "Invalid response format from AI"
                            }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"RouterAI API error: {response.status}"
                        }
                        
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Request timeout (120 seconds)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection error: {str(e)}"
            }
    
    async def generate_image(self, prompt, model_id="google/gemma-3-4b-it"):
        """Генерация изображения через RouterAI"""
        try:
            payload = {
                "model": model_id,
                "prompt": prompt,
                "size": "1024x1024",
                "quality": "standard",
                "n": 1
            }
            
            # Увеличиваем таймаут для генерации изображений
            timeout = aiohttp.ClientTimeout(total=180)  # 3 минуты
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/images/generations",
                    json=payload,
                    headers=self.headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Проверяем корректность ответа
                        if data.get("data") and len(data["data"]) > 0:
                            image_url = data["data"][0].get("url")
                            
                            if image_url:
                                # Скачиваем изображение с увеличенным таймаутом
                                async with session.get(image_url, timeout=60) as img_response:
                                    if img_response.status == 200:
                                        image_data = await img_response.read()
                                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                                        
                                        return {
                                            "success": True,
                                            "image_data": image_base64,
                                            "image_url": image_url
                                        }
                    
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Image generation error: {response.status}"
                    }
                        
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Image generation timeout (3 minutes)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Image generation error: {str(e)}"
            }
    
    def clean_response(self, text):
        """Очистка ответа от неподдерживаемых Telegram тегов"""
        if not text:
            return ""
        
        # Удаляем XML теги которые Telegram не поддерживает
        import re
        text = re.sub(r'<\?xml[^>]*\?>', '', text)  # Удаляем <?xml?>
        text = re.sub(r'<[^>]*>', '', text)  # Удаляем все остальные теги
        
        # Ограничение длины сообщения для Telegram
        if len(text) > 4000:
            text = text[:4000] + "..."
        
        return text.strip()

routerai_service = RouterAIService()
