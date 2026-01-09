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
            timeout = aiohttp.ClientTimeout(total=120)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self.headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            response_content = data["choices"][0].get("message", {}).get("content", "")
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
    
    async def generate_image(self, prompt, model_id=None):
        """Генерация изображения через RouterAI"""
        # ИСПРАВЛЕНИЕ: Используем правильную модель для генерации
        if model_id is None:
            model_id = Config.IMAGE_GENERATION_MODEL
        
        # Формируем сообщение для генерации изображения
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Сгенерируй изображение: {prompt}"
                        }
                    ]
                }
            ],
            "stream": False
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=120)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self.headers
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Обрабатываем ответ с изображением
                        if "choices" in data and len(data["choices"]) > 0:
                            choice = data["choices"][0]
                            
                            # Проверяем разные форматы ответа с изображением
                            if "message" in choice:
                                message = choice["message"]
                                
                                # Если есть изображение в контенте
                                if "content" in message:
                                    content = message["content"]
                                    
                                    # Если контент - массив (мультимодальный ответ)
                                    if isinstance(content, list):
                                        for item in content:
                                            if isinstance(item, dict) and item.get("type") == "image":
                                                # Извлекаем base64 изображение
                                                image_url = item.get("image_url", {})
                                                if isinstance(image_url, dict):
                                                    url = image_url.get("url", "")
                                                    if url.startswith("data:image"):
                                                        # Извлекаем base64 данные
                                                        base64_data = url.split(",")[1]
                                                        return {
                                                            "success": True,
                                                            "image_data": base64_data,
                                                            "response": f"Изображение сгенерировано: {prompt}"
                                                        }
                                    
                                    # Если контент - текст с описанием изображения
                                    elif isinstance(content, str):
                                        return {
                                            "success": True,
                                            "response": content,
                                            "image_data": None
                                        }
                        
                        # Если изображение не найдено, возвращаем текстовый ответ
                        return {
                            "success": True,
                            "response": f"Модель ответила на запрос генерации изображения: {prompt}\n\nОтвет: {data.get('choices', [{}])[0].get('message', {}).get('content', 'Нет ответа')}",
                            "image_data": None
                        }
                        
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"RouterAI API error: {response.status} - {error_text}"
                        }
                        
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Request timeout (120 seconds) for image generation"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection error: {str(e)}"
            }
    
    def clean_response(self, text):
        if not text:
            return ""
        
        import re
        text = re.sub(r'<\?xml[^>]*\?>', '', text)
        text = re.sub(r'<[^>]*>', '', text)
        
        if len(text) > 4000:
            text = text[:4000] + "..."
        
        return text.strip()

routerai_service = RouterAIService()
