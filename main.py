import asyncio
import logging
import uuid
import json
import base64
import sqlite3
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

from config import Config
from database import db
from services.yookassa import yookassa_service
from services.routerai import routerai_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Простая инициализация бота (без кастомных таймаутов)
bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

active_generations = {}
user_conversations = {}

# ========== INLINE КЛАВИАТУРЫ (по центру, без синей кнопки) ==========
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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏹️ Остановить", callback_data="stop_generation")]])

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
🎥 Отправка видео: {plan['video_send']}/день"""
    else:
        return f"""💎 <b>{plan['name_en']}</b>

💰 Price: {plan['price']} RUB/month
📈 Message limit: {plan['daily_limit']}/day
🖼️ Image generation: {plan['image_generate']}/day
📤 Image sending: {plan['image_send']}/day
🎥 Video sending: {plan['video_send']}/day"""

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
            welcome_text = "👋 <b>С возвращением!</b>\n\nВыберите действие:"
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

🤖 Текущая модель: {user['current_model']}""",
        'en': f"""👤 <b>Your Profile</b>

💎 Subscription: {plan['name_en'] if plan else 'Free'}
📅 Days until subscription end: {days_left}
🎁 Days until trial end: {trial_days_left}
👥 Referrals invited: {user['referral_count']}
🎁 Bonus days: {user['referral_bonus_days']}

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

🔗 <b>Ваша реферальная ссылка:</b>
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}""",
        'en': f"""📤 <b>Referral System</b>

👥 Users invited: {user['referral_count']}
🎁 Bonus days: {user['referral_bonus_days']}

🔗 <b>Your referral link:</b>
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}"""
    }
    await message.answer(ref_text[lang], reply_markup=get_referral_keyboard(lang))

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
/help - help

<b>Support:</b> {Config.SUPPORT_USERNAME}"""
    }
    await message.answer(help_text[lang])

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
    await callback.message.answer("👇 <b>Меню:</b>", reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    await callback.message.edit_text("🏠 <b>Главное меню</b>")
    await callback.message.answer("👇 <b>Выберите действие:</b>", reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "models")
async def show_models(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🤖 <b>Выберите AI-модель</b>\n\nℹ️ - информация\n✅ - выбрать",
        'en': "🤖 <b>Choose AI model</b>\n\nℹ️ - info\n✅ - select"
    }
    await callback.message.edit_text(text[lang], reply_markup=get_models_keyboard(user['subscription'], lang))
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
        price = Config.API_KEY_PRICES.get(model_id, 0)
        api_text = {
            'ru': f"{get_model_info_text(model, lang)}\n\n💰 <b>Цена:</b> {price} руб",
            'en': f"{get_model_info_text(model, lang)}\n\n💰 <b>Price:</b> {price} RUB"
        }
        await callback.message.answer(api_text[lang])
    await callback.answer()

@dp.callback_query(F.data.startswith("model_"))
async def select_model(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
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
    success_text = {
        'ru': f"✅ <b>Модель {model_name} выбрана!</b>",
        'en': f"✅ <b>Model {model_name} selected!</b>"
    }
    await callback.message.answer(success_text[lang])
    await callback.answer()

@dp.callback_query(F.data.startswith("sub_"))
async def process_subscription(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
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
            'ru': f"""💳 <b>Оплата {plan['name']}</b>

💰 Сумма: {plan['price']} руб
👉 <a href="{result['confirmation_url']}">Оплатить</a>

⚠️ После оплаты нажмите "✅ Я оплатил".""",
            'en': f"""💳 <b>Payment {plan['name_en']}</b>

💰 Amount: {plan['price']} RUB
👉 <a href="{result['confirmation_url']}">Pay</a>

⚠️ After payment, click "✅ I paid"."""
        }
        await callback.message.answer(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка оплаты</b>",
            'en': "❌ <b>Payment error</b>"
        }
        await callback.message.answer(error_text[user['language']])
    await callback.answer()

@dp.callback_query(F.data.startswith("api_"))
async def process_api(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
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
            'ru': f"""🔑 <b>Покупка API {model_name}</b>

💰 Сумма: {price} руб
👉 <a href="{result['confirmation_url']}">Оплатить</a>

⚠️ После оплаты нажмите "✅ Я оплатил".""",
            'en': f"""🔑 <b>API Purchase {model_name}</b>

💰 Amount: {price} RUB
👉 <a href="{result['confirmation_url']}">Pay</a>

⚠️ After payment, click "✅ I paid"."""
        }
        await callback.message.answer(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка оплаты</b>",
            'en': "❌ <b>Payment error</b>"
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
    
    await callback.message.edit_text("⏳ <b>Проверка платежа...</b>")
    
    result = await check_payment_status(payment_id, payment['yookassa_payment_id'], payment['user_id'])
    if not result:
        not_paid_text = {
            'ru': "❌ <b>Платеж не подтвержден</b>\n\nПопробуйте позже.",
            'en': "❌ <b>Payment not confirmed</b>\n\nTry again later."
        }
        await callback.message.answer(not_paid_text[lang], reply_markup=get_payment_check_keyboard(payment_id))
    await callback.answer()

@dp.callback_query(F.data == "buy_subscription")
async def show_buy_subscription(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
        return
        
    lang = user['language']
    text = {
        'ru': "💎 <b>Выберите подписку</b>",
        'en': "💎 <b>Choose subscription</b>"
    }
    await callback.message.edit_text(text[lang], reply_markup=get_subscription_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "buy_api")
async def show_buy_api(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🔑 <b>Купить API-ключ</b>",
        'en': "🔑 <b>Buy API Key</b>"
    }
    await callback.message.edit_text(text[lang], reply_markup=get_api_key_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "referral")
async def show_referral(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
        return
        
    lang = user['language']
    ref_text = {
        'ru': f"""📤 <b>Реферальная система</b>

👥 Приглашено: {user['referral_count']}
🎁 Бонусных дней: {user['referral_bonus_days']}

🔗 <b>Ваша ссылка:</b>
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}""",
        'en': f"""📤 <b>Referral System</b>

👥 Invited: {user['referral_count']}
🎁 Bonus days: {user['referral_bonus_days']}

🔗 <b>Your link:</b>
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}"""
    }
    await callback.message.edit_text(ref_text[lang], reply_markup=get_referral_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "help")
async def show_help(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    
    help_text = {
        'ru': f"""🆘 <b>Помощь</b>

/start - начать
/menu - меню
/models - модели
/profile - профиль
/buy - купить
/referral - рефералка
/help - помощь

Поддержка: {Config.SUPPORT_USERNAME}""",
        'en': f"""🆘 <b>Help</b>

/start - start
/menu - menu
/models - models
/profile - profile
/buy - buy
/referral - referral
/help - help

Support: {Config.SUPPORT_USERNAME}"""
    }
    await callback.message.edit_text(help_text[lang])
    await callback.answer()

@dp.callback_query(F.data == "generate_image")
async def show_generate_info(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🎨 <b>Генерация изображений</b>\n\nИспользуйте команду /generate с описанием",
        'en': "🎨 <b>Image Generation</b>\n\nUse /generate command with description"
    }
    await callback.message.edit_text(text[lang])
    await callback.answer()

@dp.callback_query(F.data == "share_ref")
async def share_referral(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала /start")
        return
        
    ref_text = {
        'ru': f"""📤 <b>Реферальная ссылка</b>

https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}""",
        'en': f"""📤 <b>Referral link</b>

https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}"""
    }
    await callback.message.answer(ref_text[user['language']])
    await callback.answer()

# ========== ЗАПУСК ==========
async def main():
    logger.info("Starting GobiAI bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
