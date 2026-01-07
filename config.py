# config.py

# Лимиты токенов в месяц
MAX_MONTHLY_TOKENS = {
    "free": 10000,        # 10K токенов
    "lite": 50000,        # 50K токенов  
    "lite_plus": 100000,  # 100K токенов
    "vip": 500000,        # 500K токенов
    "vip_plus": 600000,   # 600K токенов
    "quantum": 800000,    # 800K токенов
    "quantum_pro": 800000, # 800K токенов
    "quantum_infinite": 1000000, # 1M токенов
}

MAX_COST_PER_USER = 1500  # Максимальные убытки на пользователя

SUBSCRIPTION_PLANS = [
    {"id": "free", "name": "🆓 Бесплатно", "name_en": "🆓 Free", "price": 0, 
     "daily_limit": 100, "image_send": 2, "image_generate": 0, "video_send": 0},
    
    {"id": "lite", "name": "💎 Lite", "name_en": "💎 Lite", "price": 15, 
     "daily_limit": 200, "image_send": 5, "image_generate": 1, "video_send": 1},

    {"id": "lite_plus", "name": "💎 Lite+", "name_en": "💎 Lite+", "price": 399, 
     "daily_limit": 350, "image_send": 10, "image_generate": 3, "video_send": 2},
     
    {"id": "vip", "name": "⭐ VIP", "name_en": "⭐ VIP", "price": 1499, 
     "daily_limit": 500, "image_send": 15, "image_generate": 2, "video_send": 2},
     
    {"id": "vip_plus", "name": "🎨 VIP+", "name_en": "🎨 VIP+", "price": 4999, 
     "daily_limit": 1000, "image_send": 30, "image_generate": 10, "video_send": 5},
     
    {"id": "quantum", "name": "🚀 Quantum", "name_en": "🚀 Quantum", "price": 19999, 
     "daily_limit": 2000, "image_send": 50, "image_generate": 30, "video_send": 10},
     
    {"id": "quantum_pro", "name": "🔬 Quantum Pro", "name_en": "🔬 Quantum Pro", "price": 49999, 
     "daily_limit": 5000, "image_send": 100, "image_generate": 70, "video_send": 20},
     
    {"id": "quantum_infinite", "name": "🌌 Quantum Infinite", "name_en": "🌌 Quantum Infinite", "price": 149999, 
     "daily_limit": 9000, "image_send": 250, "image_generate": 100, "video_send": 50},
]

# AI Models распределение по подпискам
AI_MODELS = {
    "free": [
        {"id": "google/gemma-3-4b-it", "name": "🧠 Gemma 3 4B", "name_en": "🧠 Gemma 3 4B", 
         "description_ru": "Бесплатная мультимодальная модель: текст + изображения", 
         "description_en": "Free multimodal: text + images", "input": "Текст, Изображения", "output": "Текст", 
         "supports_images": True, "supports_video": False, "supports_audio": False},
    ],
    "lite": [
        {"id": "openai/gpt-oss-20b", "name": "🔓 GPT-OSS-20B", "name_en": "🔓 GPT-OSS-20B",
         "description_ru": "Открытая модель для текстовых задач", "description_en": "Open model for text tasks",
         "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
    ],
    "lite_plus": [
        {"id": "google/gemini-2.0-flash-lite-001", "name": "⚡ Gemini 2.0 Flash", "name_en": "⚡ Gemini 2.0 Flash",
         "description_ru": "Быстрая мультимодальная модель", "description_en": "Fast multimodal model",
         "input": "Текст, Изображения", "output": "Текст", "supports_images": True, "supports_video": True, "supports_audio": True},
    ],
    "vip": [
        {"id": "bytedance-seed/seed-1.6-flash", "name": "🎬 Seed 1.6 Flash", "name_en": "🎬 Seed 1.6 Flash",
         "description_ru": "Продвинутая мультимодальная модель", "description_en": "Advanced multimodal model", 
         "input": "Текст, Изображения, Видео", "output": "Текст", "supports_images": True, "supports_video": True, "supports_audio": False},
    ],
    "vip_plus": [
        {"id": "openai/gpt-5-image-mini", "name": "🖼️ GPT-5 Image Mini", "name_en": "🖼️ GPT-5 Image Mini",
         "description_ru": "Специализирован на генерации изображений", "description_en": "Specialized in image generation",
         "input": "Текст, Изображения", "output": "Текст, Изображения", "supports_images": True, "supports_video": False, "supports_audio": False},
    ],
    "quantum": [
        {"id": "google/gemini-2.5-flash-image", "name": "🎨 Nano Banana", "name_en": "🎨 Nano Banana",
         "description_ru": "Мощная генерация изображений", "description_en": "Powerful image generation",
         "input": "Текст, Изображения", "output": "Текст, Изображения", "supports_images": True, "supports_video": False, "supports_audio": False},
    ],
    "quantum_pro": [
        {"id": "openai/gpt-5.2", "name": "🚀 GPT-5.2", "name_en": "🚀 GPT-5.2",
         "description_ru": "Экспертная текстовая модель", "description_en": "Expert text model",
         "input": "Текст", "output": "Текст", "supports_images": False, "supports_video": False, "supports_audio": False},
    ],
    "quantum_infinite": [
        {"id": "google/gemini-3-pro-preview", "name": "🌟 Gemini 3 Pro", "name_en": "🌟 Gemini 3 Pro",
         "description_ru": "Флагманская мультимодальная модель", "description_en": "Flagship multimodal model",
         "input": "Текст, Изображения, Аудио, Видео", "output": "Текст", "supports_images": True, "supports_video": True, "supports_audio": True},
        {"id": "openai/o1-pro", "name": "👑 o1-pro", "name_en": "👑 o1-pro",
         "description_ru": "Премиальная модель для сложных задач", "description_en": "Premium model for complex tasks",
         "input": "Текст, Изображения", "output": "Текст", "supports_images": True, "supports_video": False, "supports_audio": False},
    ],
}

# Для генерации изображений используем GPT-5 Image Mini
IMAGE_GENERATION_MODEL = "openai/gpt-5-image-mini"
