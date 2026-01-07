import os
from datetime import timedelta

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN", "8181189288:AAFUSATnYi4VYg79yCOobemoW8TCQqZzgE0")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "7979729060"))
    SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@smknerik")
    
    # RouterAI
    ROUTERAI_API_KEY = os.getenv("ROUTERAI_API_KEY", "sk-q3x47IGel2Cv4g-DCxIEf4WNDbQiEAqG")
    ROUTERAI_ENDPOINT = os.getenv("ROUTERAI_ENDPOINT", "https://routerai.ru/api/v1")
    
    # YooKassa
    YUKASSA_SHOP_ID = os.getenv("YUKASSA_SHOP_ID", "1241024")
    YUKASSA_SECRET_KEY = os.getenv("YUKASSA_SECRET_KEY", "test_dovNMVr5Rjt6Ez5W5atO2a1RDpzNKLlQh6dcp-fDpsI")
    
    # Server
    PORT = int(os.getenv("PORT", "8000"))
    WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN", "conceptual-loralyn-erikos-353df1d3.koyeb.app")
    
    # Limits
    FREE_DAILY_LIMIT = 1000  # сообщений в день
    TRIAL_MONTHS = 3
    CURRENCY = "RUB"

    # AI Models
    AI_MODELS = {
        "free": [
            {"id": "google/gemma-3-4b-it", "name": "🧠 Google Gemma 3 4B", "name_en": "🧠 Google Gemma 3 4B", "description_ru": "Базовая текстовая модель. Только текст.", "description_en": "Basic text model. Text only.", "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
            {"id": "google/gemma-3n-e4b-it", "name": "⚡ Google Gemma 3n 4B", "name_en": "⚡ Google Gemma 3n 4B", "description_ru": "Быстрая текстовая модель. Только текст.", "description_en": "Fast text model. Text only.", "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
            {"id": "openai/gpt-oss-20b", "name": "🔓 OpenAI GPT-OSS-20B", "name_en": "🔓 OpenAI GPT-OSS-20B", "description_ru": "Открытая модель для рассуждений. Только текст.", "description_en": "Open model for reasoning. Text only.", "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
        ],
        "lite": [
            {"id": "bytedance-seed/seed-1.6-flash", "name": "🎬 ByteDance Seed 1.6 Flash", "name_en": "🎬 ByteDance Seed 1.6 Flash", "description_ru": "Мультимодальная: текст и изображения.", "description_en": "Multimodal: text and images.", "input": "Текст, Изображения", "output": "Текст, Изображения", "supports_images": True, "supports_video": False, "supports_audio": False},
        ],
        "vip": [
            {"id": "google/gemini-2.0-flash-lite-001", "name": "🌈 Google Gemini 2.0 Flash Lite", "name_en": "🌈 Google Gemini 2.0 Flash Lite", "description_ru": "Умная модель от Google. Только текст.", "description_en": "Smart Google model. Text only.", "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
        ],
        "vip_plus": [
            {"id": "openai/gpt-5-image-mini", "name": "🖼️ OpenAI GPT-5 Image Mini", "name_en": "🖼️ OpenAI GPT-5 Image Mini", "description_ru": "Специализирован на изображениях.", "description_en": "Specialized in images.", "input": "Текст, Изображения", "output": "Текст, Изображения", "supports_images": True, "supports_video": False, "supports_audio": False},
            {"id": "google/gemini-2.5-flash-lite", "name": "🚀 Google Gemini 2.5 Flash Lite", "name_en": "🚀 Google Gemini 2.5 Flash Lite", "description_ru": "Улучшенная Gemini. Только текст.", "description_en": "Enhanced Gemini. Text only.", "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
        ],
        "quantum": [
            {"id": "openai/gpt-5.2", "name": "⚡ OpenAI GPT-5.2", "name_en": "⚡ OpenAI GPT-5.2", "description_ru": "Продвинутая модель для сложных задач.", "description_en": "Advanced model for complex tasks.", "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
            {"id": "google/gemini-3-pro-preview", "name": "🌟 Google Gemini 3 Pro Preview", "name_en": "🌟 Google Gemini 3 Pro Preview", "description_ru": "Профессиональная мультимодальная модель.", "description_en": "Professional multimodal model.", "input": "Текст, Изображения, Аудио, Видео", "output": "Текст, Изображения", "supports_images": True, "supports_video": True, "supports_audio": True},
        ],
        "quantum_pro": [
            {"id": "google/gemini-3-pro-image-preview", "name": "🍌 Google Nano Banana Pro", "name_en": "🍌 Google Nano Banana Pro", "description_ru": "Экспериментальная для креативной генерации изображений.", "description_en": "Experimental for creative image generation.", "input": "Текст, Изображения", "output": "Текст, Изображения", "supports_images": True, "supports_video": False, "supports_audio": False},
        ],
        "quantum_infinite": [
            {"id": "openai/o1-pro", "name": "👑 OpenAI o1-pro", "name_en": "👑 OpenAI o1-pro", "description_ru": "Флагманская для сверхсложных задач.", "description_en": "Flagship for ultra-complex tasks.", "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
        ],
    }

    # Subscription access
    SUBSCRIPTION_ACCESS = {
        "free": ["free"],
        "lite": ["free", "lite"],
        "vip": ["free", "lite", "vip"],
        "vip_plus": ["free", "lite", "vip", "vip_plus"],
        "quantum": ["free", "lite", "vip", "vip_plus", "quantum"],
        "quantum_pro": ["free", "lite", "vip", "vip_plus", "quantum", "quantum_pro"],
        "quantum_infinite": ["free", "lite", "vip", "vip_plus", "quantum", "quantum_pro", "quantum_infinite"]
    }

    # API Key prices
    API_KEY_PRICES = {
        "openai/o1-pro": 94999,
        "openai/gpt-5.2": 3999,
        "google/gemini-3-pro-image-preview": 8000,
        "bytedance-seed/seed-1.6-flash": 700,
        "openai/gpt-oss-20b": 6,
        "google/gemma-3n-e4b-it": 6,
        "openai/gpt-5-image-mini": 400,
        "google/gemini-2.0-flash-lite-001": 40,
        "google/gemini-2.5-flash-lite": 80,
        "google/gemini-3-pro-preview": 8000,
        "google/gemma-3-4b-it": 6,
    }

    # Subscription plans
    SUBSCRIPTION_PLANS = [
        {"id": "free", "name": "🆓 Бесплатно", "name_en": "🆓 Free", "price": 0, "daily_limit": 100},
        {"id": "lite", "name": "💎 Lite", "name_en": "💎 Lite", "price": 9, "daily_limit": 250},
        {"id": "vip", "name": "⭐ VIP", "name_en": "⭐ VIP", "price": 15, "daily_limit": 250},
        {"id": "vip_plus", "name": "🎨 VIP+", "name_en": "🎨 VIP+", "price": 149, "daily_limit": 500},
        {"id": "quantum", "name": "🚀 Quantum", "name_en": "🚀 Quantum", "price": 6999, "daily_limit": 1500},
        {"id": "quantum_pro", "name": "🔬 Quantum Pro", "name_en": "🔬 Quantum Pro", "price": 9499, "daily_limit": 2500},
        {"id": "quantum_infinite", "name": "🌌 Quantum Infinite", "name_en": "🌌 Quantum Infinite", "price": 49990, "daily_limit": 5000},
    ]
