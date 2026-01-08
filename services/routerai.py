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
