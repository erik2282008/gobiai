import asyncio
import logging
import uuid
import json
import base64
import sqlite3
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    BotCommand, 
    BotCommandScopeDefault,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.client.default import DefaultBotProperties

from config import Config
from database import db
from services.yookassa import yookassa_service
from services.routerai import routerai_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

active_generations = {}
user_conversations = {}

# ========== ГЛАВНОЕ МЕНЮ-ПАНЕЛЬ ==========
def get_main_reply_keyboard(lang='ru'):
    """Основная панель меню внизу экрана"""
    if lang == 'ru':
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧠 Выбрать модель"), KeyboardButton(text="👤 Мой профиль")],
                [KeyboardButton(text="💳 Купить подписку"), KeyboardButton(text="🔑 Купить API")],
                [KeyboardButton(text="🆘 Помощь"), KeyboardButton(text="⏹️ Остановить")]
            ],
            resize_keyboard=True,
            input_field_placeholder="Выберите действие..."
        )
    else:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧠 Choose model"), KeyboardButton(text="👤 My profile")],
                [KeyboardButton(text="💳 Buy subscription"), KeyboardButton(text="🔑 Buy API")],
                [KeyboardButton(text="🆘 Help"), KeyboardButton(text="⏹️ Stop")]
            ],
            resize_keyboard=True,
            input_field_placeholder="Choose action..."
        )

def remove_reply_keyboard():
    """Убрать панель меню"""
    return ReplyKeyboardRemove()

# ========== INLINE КЛАВИАТУРЫ ДЛЯ ВЫБОРА ==========
def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
    ])

def get_models_list_keyboard(user_subscription, lang='ru'):
    """Клавиатура со списком моделей с описанием"""
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_plans_keyboard(lang='ru'):
    """Клавиатура с планами подписок"""
    keyboard = []
    for plan in Config.SUBSCRIPTION_PLANS[1:]:
        name = plan['name'] if lang == 'ru' else plan['name_en']
        keyboard.append([
            InlineKeyboardButton(text=f"ℹ️ {name}", callback_data=f"plan_info_{plan['id']}"),
            InlineKeyboardButton(text="💳 Купить", callback_data=f"sub_{plan['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_api_models_keyboard(lang='ru'):
    """Клавиатура с API моделями"""
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_stop_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏹️ Остановить генерацию", callback_data="stop_generation")]])

def get_payment_check_keyboard(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{payment_id}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]
    ])

# ========== ТЕКСТЫ С ОПИСАНИЯМИ ==========
def get_model_info_text(model, lang='ru'):
    """Текст с подробным описанием модели"""
    if lang == 'ru':
        return f"""🤖 <b>{model['name']}</b>

📝 <i>{model['description_ru']}</i>

<b>Вход:</b> {model['input']}
<b>Выход:</b> {model['output']}

<b>Поддерживает:</b>
{"✅ Изображения" if model['supports_images'] else "❌ Изображения"}
{"✅ Видео" if model['supports_video'] else "❌ Видео"} 
{"✅ Аудио" if model['supports_audio'] else "❌ Аудио"}

<b>Для:</b> {model['input'].replace('Текст', 'текстовых').replace('Изображения', 'изображений').replace('Аудио', 'аудио').replace('Видео', 'видео')} задач"""
    else:
        return f"""🤖 <b>{model['name_en']}</b>

📝 <i>{model['description_en']}</i>

<b>Input:</b> {model['input']}
<b>Output:</b> {model['output']}

<b>Supports:</b>
{"✅ Images" if model['supports_images'] else "❌ Images"}
{"✅ Video" if model['supports_video'] else "❌ Video"} 
{"✅ Audio" if model['supports_audio'] else "❌ Audio"}

<b>For:</b> {model['input'].replace('Text', 'text').replace('Images', 'images').replace('Audio', 'audio').replace('Video', 'video')} tasks"""

def get_plan_info_text(plan, lang='ru'):
    """Текст с описанием подписки"""
    available_models = []
    for category in Config.SUBSCRIPTION_ACCESS.get(plan['id'], []):
        if category in Config.AI_MODELS:
            available_models.extend([m['name'] if lang == 'ru' else m['name_en'] for m in Config.AI_MODELS[category]])
    
    target_users = {
        'lite': 'Начинающие пользователи, студенты',
        'vip': 'Опытные пользователи, фрилансеры', 
        'vip_plus': 'Профессионалы, блогеры',
        'quantum': 'Разработчики, исследователи',
        'quantum_pro': 'Премиум пользователи, стартапы',
        'quantum_infinite': 'Корпоративные клиенты, предприятия'
    }
    
    if lang == 'ru':
        return f"""💎 <b>{plan['name']}</b>

💰 <b>Цена:</b> {plan['price']} руб/месяц
📈 <b>Лимит:</b> {plan['daily_limit']} сообщений/день

<b>Доступные модели:</b>
{', '.join(available_models) if available_models else 'Все базовые модели'}

<b>Для кого:</b>
{target_users.get(plan['id'], 'Все пользователи')}"""
    else:
        return f"""💎 <b>{plan['name_en']}</b>

💰 <b>Price:</b> {plan['price']} RUB/month
📈 <b>Limit:</b> {plan['daily_limit']} messages/day

<b>Available models:</b>
{', '.join(available_models) if available_models else 'All basic models'}

<b>For:</b>
{target_users.get(plan['id'], 'All users')}"""

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
                    'ru': "✅ <b>Платеж подтвержден!</b>\n\n🎉 Ваша подписка активирована на 30 дней!",
                    'en': "✅ <b>Payment confirmed!</b>\n\n🎉 Your subscription activated for 30 days!"
                }
            else:
                model_name = payment['model_id']
                for category_models in Config.AI_MODELS.values():
                    for model in category_models:
                        if model['id'] == payment['model_id']:
                            model_name = model['name'] if lang == 'ru' else model['name_en']
                            break
                success_text = {
                    'ru': f"✅ <b>Платеж подтвержден!</b>\n\n🤖 Модель: {model_name}\n📩 Обратитесь к {Config.SUPPORT_USERNAME} для получения ключа",
                    'en': f"✅ <b>Payment confirmed!</b>\n\n🤖 Model: {model_name}\n📩 Contact {Config.SUPPORT_USERNAME} for your key"
                }
            
            await bot.send_message(user_id, success_text[lang])
            return True
        return False
    except Exception as e:
        logger.error(f"Payment check error: {e}")
        return False

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer(
            "👋 <b>Добро пожаловать в GobiAI!</b>\n\nВыберите язык для продолжения:",
            reply_markup=get_lang_keyboard()
        )
    else:
        lang = user['language']
        welcome_text = {
            'ru': "👋 <b>С возвращением в GobiAI!</b>\n\nИспользуйте панель меню внизу для навигации.",
            'en': "👋 <b>Welcome back to GobiAI!</b>\n\nUse the menu panel below for navigation."
        }
        await message.answer(welcome_text[lang], reply_markup=get_main_reply_keyboard(lang))

@dp.message(F.text == "🧠 Выбрать модель")
@dp.message(F.text == "🧠 Choose model")
async def handle_models_menu(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🤖 <b>Выберите AI-модель</b>\n\nℹ️ - информация о модели\n✅ - выбрать модель",
        'en': "🤖 <b>Choose AI model</b>\n\nℹ️ - model info\n✅ - select model"
    }
    await message.answer(text[lang], reply_markup=get_models_list_keyboard(user['subscription'], lang))

@dp.message(F.text == "👤 Мой профиль")
@dp.message(F.text == "👤 My profile")
async def handle_profile_menu(message: types.Message):
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
📅 Дней до конца: {days_left}
🎁 Триал: {trial_days_left} дней
📊 Использовано: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
🤖 Модель: {user['current_model']}""",
        'en': f"""👤 <b>Your Profile</b>

💎 Subscription: {plan['name_en'] if plan else 'Free'}
📅 Days left: {days_left}
🎁 Trial: {trial_days_left} days
📊 Used: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
🤖 Model: {user['current_model']}"""
    }
    await message.answer(profile_text[lang])

@dp.message(F.text == "💳 Купить подписку")
@dp.message(F.text == "💳 Buy subscription")
async def handle_buy_subscription(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    text = {
        'ru': "💎 <b>Выберите подписку</b>\n\nℹ️ - информация о плане\n💳 - купить подписку",
        'en': "💎 <b>Choose subscription</b>\n\nℹ️ - plan info\n💳 - buy subscription"
    }
    await message.answer(text[lang], reply_markup=get_subscription_plans_keyboard(lang))

@dp.message(F.text == "🔑 Купить API")
@dp.message(F.text == "🔑 Buy API")
async def handle_buy_api(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🔑 <b>Купить API-ключ</b>\n\nℹ️ - информация о модели\n🔑 - купить API-ключ",
        'en': "🔑 <b>Buy API Key</b>\n\nℹ️ - model info\n🔑 - buy API key"
    }
    await message.answer(text[lang], reply_markup=get_api_models_keyboard(lang))

@dp.message(F.text == "🆘 Помощь")
@dp.message(F.text == "🆘 Help")
async def handle_help_menu(message: types.Message):
    user = db.get_user(message.from_user.id)
    lang = user['language'] if user else 'ru'
    
    help_text = {
        'ru': f"""🆘 <b>Помощь по GobiAI</b>

<b>Панель меню:</b>
🧠 Выбрать модель - просмотр и выбор AI-моделей
👤 Мой профиль - информация о подписке и лимитах
💳 Купить подписку - выбор и покупка подписок
🔑 Купить API - приобретение API-ключей
🆘 Помощь - эта справка
⏹️ Остановить - прекращение текущей генерации

<b>Поддержка:</b> {Config.SUPPORT_USERNAME}""",
        'en': f"""🆘 <b>GobiAI Help</b>

<b>Menu Panel:</b>
🧠 Choose model - view and select AI models
👤 My profile - subscription info and limits
💳 Buy subscription - choose and buy subscriptions
🔑 Buy API - purchase API keys
🆘 Help - this help information
⏹️ Stop - stop current generation

<b>Support:</b> {Config.SUPPORT_USERNAME}"""
    }
    await message.answer(help_text[lang])

@dp.message(F.text == "⏹️ Остановить")
@dp.message(F.text == "⏹️ Stop")
async def handle_stop_menu(message: types.Message):
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

Используйте панель меню внизу для навигации по боту.""",
        'en': f"""🎉 <b>Welcome to GobiAI!</b>

✨ <b>{Config.TRIAL_MONTHS} months free trial activated!</b>

Use the menu panel below to navigate the bot."""
    }
    
    await callback.message.edit_text(welcome_text[lang])
    await callback.message.answer("👇 <b>Меню готово к использованию:</b>", reply_markup=get_main_reply_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    await callback.message.edit_text("🔙 <b>Возврат в главное меню</b>")
    await callback.message.answer("👇 <b>Используйте панель меню:</b>", reply_markup=get_main_reply_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data.startswith("info_"))
async def show_model_info(callback: types.CallbackQuery):
    model_id = callback.data.replace("info_", "")
    model = None
    for category_models in Config.AI_MODELS.values():
        for m in category_models:
            if m['id'] == model_id:
                model = m
                break
        if model: break
    
    if model:
        user = db.get_user(callback.from_user.id)
        lang = user['language'] if user else 'ru'
        await callback.message.answer(get_model_info_text(model, lang))
    await callback.answer()

@dp.callback_query(F.data.startswith("plan_info_"))
async def show_plan_info(callback: types.CallbackQuery):
    plan_id = callback.data.replace("plan_info_", "")
    plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == plan_id), None)
    
    if plan:
        user = db.get_user(callback.from_user.id)
        lang = user['language'] if user else 'ru'
        await callback.message.answer(get_plan_info_text(plan, lang))
    await callback.answer()

@dp.callback_query(F.data.startswith("api_info_"))
async def show_api_info(callback: types.CallbackQuery):
    model_id = callback.data.replace("api_info_", "")
    model = None
    for category_models in Config.AI_MODELS.values():
        for m in category_models:
            if m['id'] == model_id:
                model = m
                break
        if model: break
    
    if model:
        user = db.get_user(callback.from_user.id)
        lang = user['language'] if user else 'ru'
        api_price = Config.API_KEY_PRICES.get(model_id, 0)
        api_text = {
            'ru': f"{get_model_info_text(model, lang)}\n\n💰 <b>Цена API-ключа:</b> {api_price} руб (750K токенов)",
            'en': f"{get_model_info_text(model, lang)}\n\n💰 <b>API Key Price:</b> {api_price} RUB (750K tokens)"
        }
        await callback.message.answer(api_text[lang])
    await callback.answer()

@dp.callback_query(F.data.startswith("model_"))
async def select_model(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    model_id = callback.data.replace("model_", "")
    db.update_user_model(user['user_id'], model_id)
    
    model_name = model_id
    for category_models in Config.AI_MODELS.values():
        for m in category_models:
            if m['id'] == model_id:
                model_name = m['name'] if user['language'] == 'ru' else m['name_en']
                break
    
    lang = user['language']
    await callback.message.answer(f"✅ <b>Модель {model_name} выбрана!</b>\n\nТеперь отправляйте сообщения для генерации.")
    await callback.answer()

@dp.callback_query(F.data.startswith("sub_"))
async def process_subscription(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    plan_id = callback.data.replace("sub_", "")
    plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == plan_id), None)
    if not plan: 
        await callback.answer("❌ План не найден")
        return
    
    payment_id = str(uuid.uuid4())
    db.create_payment(payment_id, user['user_id'], 'subscription', plan_id, None, plan['price'])
    result = await yookassa_service.create_subscription_payment(user['user_id'], plan_id, plan['name'], plan['price'], user['language'])
    
    if result['success']:
        db.update_payment_status(payment_id, 'pending', result['yookassa_id'])
        payment_text = {
            'ru': f"""💳 <b>Оплата подписки {plan['name']}</b>

💰 Сумма: {plan['price']} руб
📅 Срок: 30 дней
📊 Лимит: {plan['daily_limit']} сообщений/день

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил" для проверки статуса.""",
            'en': f"""💳 <b>Payment for {plan['name_en']}</b>

💰 Amount: {plan['price']} RUB
📅 Duration: 30 days
📊 Limit: {plan['daily_limit']} messages/day

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ After payment, click "✅ I paid" to check status."""
        }
        await callback.message.answer(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже.",
            'en': "❌ <b>Payment creation error</b>\n\nTry again later."
        }
        await callback.message.answer(error_text[user['language']])
    await callback.answer()

@dp.callback_query(F.data.startswith("api_"))
async def process_api(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    model_id = callback.data.replace("api_", "")
    price = Config.API_KEY_PRICES.get(model_id)
    if not price: 
        await callback.answer("❌ Модель не найдена")
        return
    
    model = None
    for category_models in Config.AI_MODELS.values():
        for m in category_models:
            if m['id'] == model_id:
                model = m
                break
        if model: break
    
    payment_id = str(uuid.uuid4())
    db.create_payment(payment_id, user['user_id'], 'api_key', None, model_id, price)
    model_name = model['name'] if user['language'] == 'ru' else model['name_en']
    result = await yookassa_service.create_api_key_payment(user['user_id'], model_id, model_name, price, user['language'])
    
    if result['success']:
        db.update_payment_status(payment_id, 'pending', result['yookassa_id'])
        payment_text = {
            'ru': f"""🔑 <b>Покупка API-ключа {model_name}</b>

💰 Стоимость: {price} руб (за 750K токенов)

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил"

📩 После подтверждения обратитесь к {Config.SUPPORT_USERNAME} для получения ключа.""",
            'en': f"""🔑 <b>API Key Purchase {model_name}</b>

💰 Price: {price} RUB (per 750K tokens)

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ After payment, click "✅ I paid"

📩 After confirmation, contact {Config.SUPPORT_USERNAME} for your key."""
        }
        await callback.message.answer(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже.",
            'en': "❌ <b>Payment creation error</b>\n\nTry again later."
        }
        await callback.message.answer(error_text[user['language']])
    await callback.answer()

@dp.callback_query(F.data.startswith("paid_"))
async def check_payment(callback: types.CallbackQuery):
    payment_id = callback.data.replace("paid_", "")
    payment = db.get_payment(payment_id)
    if not payment: 
        await callback.answer("❌ Платеж не найден")
        return
    
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    
    await callback.message.edit_text("⏳ <b>Проверяем статус платежа...</b>")
    
    result = await check_payment_status(payment_id, payment['yookassa_payment_id'], payment['user_id'])
    if not result:
        await callback.message.answer("❌ <b>Платеж еще не подтвержден</b>\n\nПожалуйста, подождите несколько минут и попробуйте снова.", reply_markup=get_payment_check_keyboard(payment_id))
    await callback.answer()

@dp.callback_query(F.data == "stop_generation")
async def stop_generation(callback: types.CallbackQuery):
    if callback.from_user.id in active_generations:
        active_generations[callback.from_user.id] = False
        user = db.get_user(callback.from_user.id)
        lang = user['language'] if user else 'ru'
        await callback.message.answer("⏹️ Генерация остановлена", reply_markup=get_main_reply_keyboard(lang))
    await callback.answer()

# ========== ОБРАБОТКА СООБЩЕНИЙ ДЛЯ AI ==========
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: 
        lang = user['language']
        await message.answer(f"❌ <b>Лимит исчерпан</b>\n\n{error_msg}")
        return
        
    db.increment_daily_usage(user['user_id'])
    
    current_model_supports_images = False
    for category_models in Config.AI_MODELS.values():
        for model in category_models:
            if model['id'] == user['current_model']:
                current_model_supports_images = model['supports_images']
                break
    
    if not current_model_supports_images:
        lang = user['language']
        await message.answer("❌ Текущая модель не поддерживает изображения")
        return
    
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
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{result['response']}")
        elif not result['success']:
            await msg.edit_text(f"❌ <b>Ошибка:</b>\n\n{result['error']}")
            
    except Exception as e:
        await msg.edit_text("❌ <b>Ошибка обработки изображения</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

@dp.message(F.text)
async def handle_message(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: 
        lang = user['language']
        await message.answer(f"❌ <b>Лимит исчерпан</b>\n\n{error_msg}")
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
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{result['response']}")
        elif not result['success']:
            await msg.edit_text(f"❌ <b>Ошибка:</b>\n\n{result['error']}")
            
    except Exception as e:
        await msg.edit_text("❌ <b>Ошибка соединения</b>\n\nПопробуйте позже.")
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
                        model_name = payment['model_id']
                        for category_models in Config.AI_MODELS.values():
                            for model in category_models:
                                if model['id'] == payment['model_id']:
                                    model_name = model['name'] if lang == 'ru' else model['name_en']
                                    break
                        success_text = {
                            'ru': f"✅ <b>Платеж автоматически подтвержден!</b>\n\n🤖 Модель: {model_name}\n📩 Обратитесь к {Config.SUPPORT_USERNAME} для получения ключа",
                            'en': f"✅ <b>Payment automatically confirmed!</b>\n\n🤖 Model: {model_name}\n📩 Contact {Config.SUPPORT_USERNAME} for your key"
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
    logger.info("Starting GobiAI bot...")
    runner = await start_webhook_server()
    
    logger.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
