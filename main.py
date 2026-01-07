import asyncio
import logging
import uuid
import json
import base64
import sqlite3
from datetime import datetime, timedelta
from aiohttp import web, ClientTimeout
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from config import Config
from database import db
from services.yookassa import yookassa_service
from services.routerai import routerai_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем сессию с увеличенными таймаутами
session = AiohttpSession(timeout=ClientTimeout(total=60))

# Инициализируем бота с кастомной сессией
bot = Bot(
    token=Config.BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode='HTML'),
    session=session
)
dp = Dispatcher()

active_generations = {}
user_conversations = {}

# ========== INLINE КЛАВИАТУРЫ ==========
def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
    ])

def get_main_keyboard(lang='ru'):
    if lang == 'ru':
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Выбрать модель", callback_data="models")],
            [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🔑 Купить API", callback_data="buy_api")],
            [InlineKeyboardButton(text="🎨 Сгенерировать фото", callback_data="generate_image")],
            [InlineKeyboardButton(text="📤 Рефералка", callback_data="referral")],
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Choose model", callback_data="models")],
            [InlineKeyboardButton(text="👤 My profile", callback_data="profile")],
            [InlineKeyboardButton(text="💳 Buy subscription", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🔑 Buy API", callback_data="buy_api")],
            [InlineKeyboardButton(text="🎨 Generate image", callback_data="generate_image")],
            [InlineKeyboardButton(text="📤 Referral", callback_data="referral")],
            [InlineKeyboardButton(text="🆘 Help", callback_data="help")]
        ])

def get_models_keyboard(user_subscription, lang='ru'):
    keyboard = []
    available_categories = Config.SUBSCRIPTION_ACCESS.get(user_subscription, ['free'])
    
    for category in available_categories:
        if category in Config.AI_MODELS:
            for model in Config.AI_MODELS[category]:
                name = model['name'] if lang == 'ru' else model['name_en']
                keyboard.append([
                    InlineKeyboardButton(text=f"ℹ️ {name}", callback_data=f"info_{model['id']}"),
                    InlineKeyboardButton(text="✅ Выбрать", callback_data=f"model_{model['id']}")
                ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_keyboard(lang='ru'):
    keyboard = []
    for plan in Config.SUBSCRIPTION_PLANS[1:]:
        name = plan['name'] if lang == 'ru' else plan['name_en']
        keyboard.append([
            InlineKeyboardButton(text=f"ℹ️ {name}", callback_data=f"plan_info_{plan['id']}"),
            InlineKeyboardButton(text="💳 Купить", callback_data=f"sub_{plan['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_api_key_keyboard(lang='ru'):
    keyboard = []
    for model_id, price in Config.API_KEY_PRICES.items():
        model = None
        for category_models in Config.AI_MODELS.values():
            for m in category_models:
                if m['id'] == model_id:
                    model = m
                    break
            if model: break
        
        if model:
            name = model['name'] if lang == 'ru' else model['name_en']
            keyboard.append([
                InlineKeyboardButton(text=f"ℹ️ {name}", callback_data=f"api_info_{model_id}"),
                InlineKeyboardButton(text="🔑 Купить", callback_data=f"api_{model_id}")
            ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_referral_keyboard(lang='ru'):
    if lang == 'ru':
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться ссылкой", callback_data="share_ref")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share link", callback_data="share_ref")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="main_menu")]
        ])

def get_stop_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏹️ Остановить генерацию", callback_data="stop_generation")]])

def get_payment_check_keyboard(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{payment_id}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="main_menu")]
    ])

# ========== ТЕКСТЫ ==========
def get_model_info_text(model, lang='ru'):
    if lang == 'ru':
        return f"""🤖 <b>{model['name']}</b>

📝 {model['description_ru']}

<b>Вход:</b> {model['input']}
<b>Выход:</b> {model['output']}

<b>Поддерживает:</b>
{"✅ Изображения" if model['supports_images'] else "❌ Изображения"}
{"✅ Видео" if model['supports_video'] else "❌ Видео"} 
{"✅ Аудио" if model['supports_audio'] else "❌ Аудио"}"""
    else:
        return f"""🤖 <b>{model['name_en']}</b>

📝 {model['description_en']}

<b>Input:</b> {model['input']}
<b>Output:</b> {model['output']}

<b>Supports:</b>
{"✅ Images" if model['supports_images'] else "❌ Images"}
{"✅ Video" if model['supports_video'] else "❌ Video"} 
{"✅ Audio" if model['supports_audio'] else "❌ Audio"}"""

def get_plan_info_text(plan, lang='ru'):
    available_models = []
    for category in Config.SUBSCRIPTION_ACCESS.get(plan['id'], []):
        if category in Config.AI_MODELS:
            available_models.extend([m['name'] if lang == 'ru' else m['name_en'] for m in Config.AI_MODELS[category]])
    
    if lang == 'ru':
        return f"""💎 <b>{plan['name']}</b>

💰 Цена: {plan['price']} руб/месяц
📈 Лимит сообщений: {plan['daily_limit']}/день
🖼️ Генерация изображений: {plan['image_generate']}/день
📤 Отправка изображений: {plan['image_send']}/день
🎥 Отправка видео: {plan['video_send']}/день

<b>Доступные модели:</b>
{', '.join(available_models[:3])}{'...' if len(available_models) > 3 else ''}"""
    else:
        return f"""💎 <b>{plan['name_en']}</b>

💰 Price: {plan['price']} RUB/month
📈 Message limit: {plan['daily_limit']}/day
🖼️ Image generation: {plan['image_generate']}/day
📤 Image sending: {plan['image_send']}/day
🎥 Video sending: {plan['video_send']}/day

<b>Available models:</b>
{', '.join(available_models[:3])}{'...' if len(available_models) > 3 else ''}"""

async def check_payment_status(payment_id, yookassa_id, user_id):
    try:
        result = await yookassa_service.get_payment_status(yookassa_id)
        if result['success'] and result['status'] == 'succeeded':
            db.update_payment_status(payment_id, 'succeeded', yookassa_id)
            payment = db.get_payment(payment_id)
            user = db.get_user(user_id)
            lang = user['language'] if user else 'ru'
            
            if payment['type'] == 'subscription':
                db.update_user_subscription(user_id, payment['plan_id'])
                success_text = {
                    'ru': "✅ <b>Платеж подтвержден! Подписка активирована на 30 дней.</b>",
                    'en': "✅ <b>Payment confirmed! Subscription activated for 30 days.</b>"
                }
            else:
                success_text = {
                    'ru': f"✅ <b>Платеж подтвержден!</b>\n\nДля получения API-ключа обратитесь к {Config.SUPPORT_USERNAME}",
                    'en': f"✅ <b>Payment confirmed!</b>\n\nContact {Config.SUPPORT_USERNAME} for your API key"
                }
            
            await bot.send_message(user_id, success_text[lang])
            return True
        return False
    except Exception as e:
        logger.error(f"Payment check error: {e}")
        return False

# ========== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ ==========
async def handle_generate_image(prompt, user_id):
    """Обработчик генерации изображений"""
    user = db.get_user(user_id)
    if not user: 
        return "❌ Сначала используйте /start"
    
    # Проверяем лимиты генерации изображений
    can_generate, error_msg = db.can_generate_image(user_id)
    if not can_generate:
        return f"❌ {error_msg}"
    
    try:
        result = await routerai_service.generate_image(prompt)
        
        if result['success']:
            # Обновляем счетчик генераций
            db.update_media_usage(user_id, 'image_generate')
            
            if result.get('image_data'):
                # Отправляем сгенерированное изображение
                image_data = base64.b64decode(result['image_data'])
                return {"type": "photo", "data": image_data}
            else:
                return "✅ <b>Изображение сгенерировано!</b>"
        else:
            return f"❌ <b>Ошибка генерации:</b>\n\n{result['error']}"
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return "❌ <b>Ошибка при генерации изображения</b>"

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    try:
        referral_code = None
        if len(message.text.split()) > 1:
            referral_code = message.text.split()[1]
        
        user = db.get_user(message.from_user.id)
        if not user:
            user = db.create_user(message.from_user.id, message.from_user.username, 'ru', referral_code)
            
            welcome_text = f"""👋 <b>Добро пожаловать в GobiAI!</b>

✨ <b>Бесплатный триал на {Config.TRIAL_MONTHS} месяца активирован!</b>"""
            
            if user['referred_by']:
                welcome_text += f"\n\n🎁 +{Config.REFERRAL_REWARD_DAYS} дней VIP за регистрацию по реферальной ссылке!"
            
            await message.answer(welcome_text, reply_markup=get_lang_keyboard())
        else:
            lang = user['language']
            welcome_text = "👋 <b>С возвращением!</b>\n\nИспользуйте команды снизу для навигации:"
            await message.answer(welcome_text, reply_markup=get_main_keyboard(lang))
    except Exception as e:
        logger.error(f"Start command error: {e}")
        await message.answer("❌ <b>Ошибка при запуске бота</b>\n\nПопробуйте позже")

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    menu_text = {
        'ru': "🏠 <b>Главное меню GobiAI</b>\n\nВыберите действие:",
        'en': "🏠 <b>GobiAI Main Menu</b>\n\nChoose action:"
    }
    await message.answer(menu_text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("models"))
async def cmd_models(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🤖 <b>Выберите AI-модель</b>\n\nℹ️ - информация о модели\n✅ - выбрать модель",
        'en': "🤖 <b>Choose AI model</b>\n\nℹ️ - model information\n✅ - select model"
    }
    await message.answer(text[lang], reply_markup=get_models_keyboard(user['subscription'], lang))

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
    
    days_left = 0
    if user['subscription_end']:
        end_date = datetime.strptime(user['subscription_end'], '%Y-%m-%d')
        days_left = max((end_date - datetime.now()).days, 0)
    
    trial_days_left = 0
    if user['trial_end']:
        trial_end = datetime.strptime(user['trial_end'], '%Y-%m-%d')
        trial_days_left = max((trial_end - datetime.now()).days, 0)
    
    profile_text = {
        'ru': f"""👤 <b>Ваш профиль</b>

💎 Подписка: {plan['name'] if plan else 'Free'}
📅 Дней до конца подписки: {days_left}
🎁 Дней до конца триала: {trial_days_left}
👥 Приглашено рефералов: {user['referral_count']}
🎁 Бонусных дней: {user['referral_bonus_days']}

📊 <b>Использовано сегодня:</b>
Сообщения: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
Сгенерировано изображений: {user['images_generated_today']}/{plan['image_generate'] if plan else 0}
Отправлено изображений: {user['images_sent_today']}/{plan['image_send'] if plan else 0}
Отправлено видео: {user['videos_sent_today']}/{plan['video_send'] if plan else 0}

🤖 Текущая модель: {user['current_model']}""",
        'en': f"""👤 <b>Your Profile</b>

💎 Subscription: {plan['name_en'] if plan else 'Free'}
📅 Days until subscription end: {days_left}
🎁 Days until trial end: {trial_days_left}
👥 Referrals invited: {user['referral_count']}
🎁 Bonus days: {user['referral_bonus_days']}

📊 <b>Used today:</b>
Messages: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
Images generated: {user['images_generated_today']}/{plan['image_generate'] if plan else 0}
Images sent: {user['images_sent_today']}/{plan['image_send'] if plan else 0}
Videos sent: {user['videos_sent_today']}/{plan['video_send'] if plan else 0}

🤖 Current model: {user['current_model']}"""
    }
    await message.answer(profile_text[lang])

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    text = {
        'ru': "💎 <b>Выберите тип покупки</b>",
        'en': "💎 <b>Choose purchase type</b>"
    }
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔑 Купить API-ключ", callback_data="buy_api")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    
    await message.answer(text[lang], reply_markup=keyboard)

@dp.message(Command("referral"))
async def cmd_referral(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    ref_text = {
        'ru': f"""📤 <b>Реферальная система</b>

👥 Приглашено пользователей: {user['referral_count']}
🎁 Бонусных дней: {user['referral_bonus_days']}

💎 <b>За каждого приглашенного:</b>
• Вы получаете +{Config.REFERRAL_REWARD_DAYS} дней VIP
• Приглашенный получает +{Config.REFERRAL_REWARD_DAYS} дней VIP

🔗 <b>Ваша реферальная ссылка:</b>
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}""",
        'en': f"""📤 <b>Referral System</b>

👥 Users invited: {user['referral_count']}
🎁 Bonus days: {user['referral_bonus_days']}

💎 <b>For each invited user:</b>
• You get +{Config.REFERRAL_REWARD_DAYS} days VIP
• Invited user gets +{Config.REFERRAL_REWARD_DAYS} days VIP

🔗 <b>Your referral link:</b>
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}"""
    }
    await message.answer(ref_text[lang], reply_markup=get_referral_keyboard(lang))

@dp.message(Command("generate"))
async def cmd_generate(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    prompt = message.text.replace("/generate", "").strip()
    if not prompt:
        await message.answer("❌ Укажите описание для генерации изображения\nПример: /generate красная спортивная машина в горах")
        return
    
    result = await handle_generate_image(prompt, message.from_user.id)
    
    if isinstance(result, dict) and result.get("type") == "photo":
        await message.answer_photo(
            types.BufferedInputFile(result["data"], filename="generated_image.jpg"),
            caption="🎨 <b>Сгенерированное изображение</b>"
        )
    else:
        await message.answer(result)

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user = db.get_user(message.from_user.id)
    lang = user['language'] if user else 'ru'
    
    help_text = {
        'ru': f"""🆘 <b>Помощь по GobiAI</b>

<b>Команды:</b>
/start - начать работу
/menu - главное меню  
/models - выбрать модель
/profile - мой профиль
/buy - покупка подписок и API
/referral - реферальная система
/generate - генерация изображений
/help - помощь

<b>Поддержка:</b> {Config.SUPPORT_USERNAME}""",
        'en': f"""🆘 <b>GobiAI Help</b>

<b>Commands:</b>
/start - start working
/menu - main menu
/models - choose model
/profile - my profile
/buy - buy subscriptions and API
/referral - referral system
/generate - generate images
/help - help

<b>Support:</b> {Config.SUPPORT_USERNAME}"""
    }
    await message.answer(help_text[lang])

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    if message.from_user.id in active_generations:
        active_generations[message.from_user.id] = False
        await message.answer("⏹️ Генерация остановлена")

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query(F.data == "lang_ru")
@dp.callback_query(F.data == "lang_en")
async def set_language(callback: types.CallbackQuery):
    lang = "ru" if callback.data == "lang_ru" else "en"
    db.create_user(callback.from_user.id, callback.from_user.username, lang)
    
    welcome_text = {
        'ru': f"""🎉 <b>Добро пожаловать в GobiAI!</b>

✨ <b>Бесплатный триал на {Config.TRIAL_MONTHS} месяца активирован!</b>

Используйте команды для навигации.""",
        'en': f"""🎉 <b>Welcome to GobiAI!</b>

✨ <b>{Config.TRIAL_MONTHS} months free trial activated!</b>

Use commands for navigation."""
    }
    
    await callback.message.edit_text(welcome_text[lang])
    await callback.message.answer("💡 <b>Используйте команды:</b>\n/menu - главное меню\n/help - помощь", reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    await callback.message.edit_text("🏠 <b>Главное меню</b>")
    await callback.message.answer("💡 <b>Используйте команды для навигации</b>", reply_markup=get_main_keyboard(lang))
    await callback.answer()

# [Все остальные callback обработчики остаются без изменений...]
# [Обработчики info_, plan_info_, api_info_, model_, sub_, api_, paid_, share_ref и т.д.]

# ========== ОБРАБОТКА СООБЩЕНИЙ ДЛЯ AI ==========
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    # Проверяем лимиты отправки изображений
    can_send, error_msg = db.can_send_image(user['user_id'])
    if not can_send: 
        await message.answer(f"❌ {error_msg}")
        return
        
    # Проверяем общие лимиты
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: 
        await message.answer(f"❌ {error_msg}")
        return
        
    db.increment_daily_usage(user['user_id'])
    db.update_media_usage(user['user_id'], 'image_send')
    
    # Проверяем поддерживает ли текущая модель изображения
    current_model_supports_images = False
    for category_models in Config.AI_MODELS.values():
        for model in category_models:
            if model['id'] == user['current_model']:
                current_model_supports_images = model['supports_images']
                break
    
    if not current_model_supports_images:
        lang = user['language']
        error_text = {
            'ru': "❌ Текущая модель не поддерживает изображения",
            'en': "❌ Current model doesn't support images"
        }
        await message.answer(error_text[lang])
        return
    
    # Скачиваем изображение
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = await bot.download_file(file.file_path)
    image_data = base64.b64encode(file_path.read()).decode('utf-8')
    
    lang = user['language']
    msg = await message.answer("⏳ <b>Обработка изображения...</b>", reply_markup=get_stop_keyboard())
    active_generations[message.from_user.id] = True
    
    try:
        result = await routerai_service.send_message(
            user['current_model'], 
            message.caption or "Опиши это изображение",
            extra_data={"image": image_data}
        )
        
        if result['success'] and active_generations.get(message.from_user.id):
            response_text = f"🤖 <b>Ответ:</b>\n\n{result['response']}"
            await msg.edit_text(response_text)
        elif not result['success']:
            error_text = f"❌ <b>Ошибка:</b>\n\n{result['error']}"
            await msg.edit_text(error_text)
            
    except Exception as e:
        error_text = {
            'ru': "❌ <b>Ошибка обработки изображения</b>",
            'en': "❌ <b>Image processing error</b>"
        }
        await msg.edit_text(error_text[lang])
    finally:
        active_generations.pop(message.from_user.id, None)

@dp.message(F.text)
async def handle_message(message: types.Message):
    # Пропускаем команды
    if message.text.startswith('/'):
        return
        
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    # Проверяем общие лимиты
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: 
        lang = user['language']
        await message.answer(f"❌ {error_msg}")
        return
        
    db.increment_daily_usage(user['user_id'])
    
    user_id = message.from_user.id
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    user_conversations[user_id].append({"role": "user", "content": message.text})
    if len(user_conversations[user_id]) > 10:
        user_conversations[user_id] = user_conversations[user_id][-10:]
    
    lang = user['language']
    msg = await message.answer("⏳ <b>Генерация началась...</b>", reply_markup=get_stop_keyboard())
    active_generations[user_id] = True
    
    try:
        result = await routerai_service.send_message(
            user['current_model'], 
            message.text,
            user_conversations[user_id][:-1]
        )
        
        if result['success'] and active_generations.get(user_id):
            user_conversations[user_id].append({"role": "assistant", "content": result['response']})
            response_text = f"🤖 <b>Ответ:</b>\n\n{result['response']}"
            await msg.edit_text(response_text)
        elif not result['success']:
            error_text = f"❌ <b>Ошибка:</b>\n\n{result['error']}"
            await msg.edit_text(error_text)
            
    except Exception as e:
        error_text = {
            'ru': "❌ <b>Ошибка соединения</b>\n\nПопробуйте позже.",
            'en': "❌ <b>Connection error</b>\n\nPlease try again later."
        }
        await msg.edit_text(error_text[lang])
    finally:
        active_generations.pop(user_id, None)

# ========== ВЕБХУК YOOKASSA ==========
async def yookassa_webhook(request):
    try:
        body = await request.text()
        data = json.loads(body)
        logger.info(f"YooKassa webhook received")
        
        if data.get('event') == 'payment.succeeded':
            yookassa_id = data['object']['id']
            metadata = data['object'].get('metadata', {})
            user_id = metadata.get('user_id')
            
            if user_id:
                payment = db.get_payment_by_yookassa_id(yookassa_id)
                if payment and payment['status'] != 'succeeded':
                    db.update_payment_status(payment['payment_id'], 'succeeded', yookassa_id)
                    
                    user = db.get_user(user_id)
                    lang = user['language'] if user else 'ru'
                    
                    if payment['type'] == 'subscription':
                        db.update_user_subscription(user_id, payment['plan_id'])
                        success_text = {
                            'ru': "✅ <b>Платеж автоматически подтвержден!</b>\n\n🎉 Ваша подписка активирована на 30 дней!",
                            'en': "✅ <b>Payment automatically confirmed!</b>\n\n🎉 Your subscription activated for 30 days!"
                        }
                    else:
                        success_text = {
                            'ru': f"✅ <b>Платеж автоматически подтвержден!</b>\n\n📩 Обратитесь к {Config.SUPPORT_USERNAME} для получения ключа",
                            'en': f"✅ <b>Payment automatically confirmed!</b>\n\n📩 Contact {Config.SUPPORT_USERNAME} for your key"
                        }
                    
                    await bot.send_message(user_id, success_text[lang])
        
        return web.Response(status=200, text='OK')
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500, text='Error')

async def start_webhook_server():
    app = web.Application()
    app.router.add_post('/yookassa-webhook', yookassa_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"Webhook server started on port {Config.PORT}")
    return runner

async def main():
    logger.info("Starting GobiAI bot with fixed timeouts...")
    
    # Запускаем сервер для вебхуков
    runner = await start_webhook_server()
    
    logger.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
