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
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self.headers,
                    timeout=30
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "response": data["choices"][0]["message"]["content"],
                            "usage": data.get("usage", {})
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"RouterAI API error: {response.status} - {error_text}"
                        }
                        
        except aiohttp.ClientError as e:
            return {
                "success": False,
                "error": f"Connection error: {str(e)}"
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Request timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }
    
    async def generate_image(self, prompt, model_id="google/gemini-3-pro-preview"):
        """Генерация изображения через RouterAI"""
        try:
            payload = {
                "model": model_id,
                "prompt": prompt,
                "size": "1024x1024",
                "quality": "standard",
                "n": 1
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/images/generations",
                    json=payload,
                    headers=self.headers,
                    timeout=60
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        if data.get("data") and len(data["data"]) > 0:
                            image_url = data["data"][0]["url"]
                            
                            # Скачиваем изображение и конвертируем в base64
                            async with session.get(image_url) as img_response:
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
                        "error": f"Image generation error: {response.status} - {error_text}"
                    }
                        
        except Exception as e:
            return {
                "success": False,
                "error": f"Image generation error: {str(e)}"
            }

routerai_service = RouterAIService()
