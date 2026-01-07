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
    InlineKeyboardButton, 
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
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

# ========== МЕНЮ-ПАНЕЛЬ ==========
def get_main_reply_keyboard(lang='ru'):
    if lang == 'ru':
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧠 Выбрать модель"), KeyboardButton(text="👤 Мой профиль")],
                [KeyboardButton(text="💳 Купить подписку"), KeyboardButton(text="🔑 Купить API")],
                [KeyboardButton(text="🎨 Сгенерировать фото"), KeyboardButton(text="📤 Рефералка")],
                [KeyboardButton(text="🆘 Помощь"), KeyboardButton(text="⏹️ Остановить")]
            ],
            resize_keyboard=True
        )
    else:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧠 Choose model"), KeyboardButton(text="👤 My profile")],
                [KeyboardButton(text="💳 Buy subscription"), KeyboardButton(text="🔑 Buy API")],
                [KeyboardButton(text="🎨 Generate image"), KeyboardButton(text="📤 Referral")],
                [KeyboardButton(text="🆘 Help"), KeyboardButton(text="⏹️ Stop")]
            ],
            resize_keyboard=True
        )

def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_keyboard(lang='ru'):
    keyboard = []
    for plan in Config.SUBSCRIPTION_PLANS[1:]:
        name = plan['name'] if lang == 'ru' else plan['name_en']
        keyboard.append([
            InlineKeyboardButton(text=f"ℹ️ {name}", callback_data=f"plan_info_{plan['id']}"),
            InlineKeyboardButton(text="💳 Купить", callback_data=f"sub_{plan['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_referral_keyboard(lang='ru'):
    if lang == 'ru':
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться ссылкой", callback_data="share_ref")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Share link", callback_data="share_ref")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
        ])

def get_generate_image_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Сгенерировать изображение", callback_data="generate_image")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

def get_stop_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏹️ Остановить генерацию", callback_data="stop_generation")]])

def get_payment_check_keyboard(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{payment_id}")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]
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
                model_name = payment['model_id']
                for category_models in Config.AI_MODELS.values():
                    for model in category_models:
                        if model['id'] == payment['model_id']:
                            model_name = model['name'] if lang == 'ru' else model['name_en']
                            break
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
@dp.message(F.text == "🎨 Сгенерировать фото")
@dp.message(F.text == "🎨 Generate image")
async def handle_generate_image_menu(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🎨 <b>Генерация изображений</b>\n\nОтправьте текстовое описание для генерации изображения\n\nПример: <code>красная спортивная машина в горах</code>",
        'en': "🎨 <b>Image Generation</b>\n\nSend text description to generate image\n\nExample: <code>red sports car in mountains</code>"
    }
    await message.answer(text[lang])

@dp.message(F.text.startswith("/generate"))
async def handle_generate_command(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    prompt = message.text.replace("/generate", "").strip()
    if not prompt:
        await message.answer("❌ Укажите описание для генерации изображения")
        return
    
    # Проверяем лимиты генерации изображений
    can_generate, error_msg = db.can_generate_image(user['user_id'])
    if not can_generate:
        lang = user['language']
        await message.answer(f"❌ {error_msg}")
        return
    
    lang = user['language']
    wait_text = {
        'ru': "🎨 <b>Генерация изображения...</b>\n\nЭто может занять несколько минут",
        'en': "🎨 <b>Generating image...</b>\n\nThis may take a few minutes"
    }
    
    msg = await message.answer(wait_text[lang], reply_markup=get_stop_keyboard())
    active_generations[message.from_user.id] = True
    
    try:
        result = await routerai_service.generate_image(prompt)
        
        if result['success'] and active_generations.get(message.from_user.id):
            # Обновляем счетчик генераций
            db.update_media_usage(user['user_id'], 'image_generate')
            
            if result.get('image_data'):
                # Отправляем сгенерированное изображение
                image_data = base64.b64decode(result['image_data'])
                await message.answer_photo(
                    types.BufferedInputFile(image_data, filename="generated_image.jpg"),
                    caption="🎨 <b>Сгенерированное изображение</b>"
                )
                await msg.delete()
            else:
                await msg.edit_text("✅ <b>Изображение сгенерировано!</b>")
        elif not result['success']:
            await msg.edit_text(f"❌ <b>Ошибка генерации:</b>\n\n{result['error']}")
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await msg.edit_text("❌ <b>Ошибка при генерации изображения</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

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
            
            await message.answer(welcome_text, reply_markup=get_main_reply_keyboard('ru'))
        else:
            await message.answer("👋 <b>С возвращением!</b>", reply_markup=get_main_reply_keyboard(user['language']))
    except Exception as e:
        logger.error(f"Start command error: {e}")
        await message.answer("❌ <b>Ошибка при запуске бота</b>\n\nПопробуйте позже")

@dp.message(F.text == "🧠 Выбрать модель")
@dp.message(F.text == "🧠 Choose model")
async def handle_models(message: types.Message):
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

@dp.message(F.text == "👤 Мой профиль")
@dp.message(F.text == "👤 My profile")
async def handle_profile(message: types.Message):
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
        'en': "💎 <b>Choose subscription</b>\n\nℹ️ - plan information\n💳 - buy subscription"
    }
    await message.answer(text[lang], reply_markup=get_subscription_keyboard(lang))

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
        'en': "🔑 <b>Buy API Key</b>\n\nℹ️ - model information\n🔑 - buy API key"
    }
    await message.answer(text[lang], reply_markup=get_api_key_keyboard(lang))

@dp.message(F.text == "📤 Рефералка")
@dp.message(F.text == "📤 Referral")
async def handle_referral(message: types.Message):
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

@dp.message(F.text == "🆘 Помощь")
@dp.message(F.text == "🆘 Help")
async def handle_help(message: types.Message):
    user = db.get_user(message.from_user.id)
    lang = user['language'] if user else 'ru'
    
    help_text = {
        'ru': f"""🆘 <b>Помощь по GobiAI</b>

<b>Панель меню:</b>
🧠 Выбрать модель - просмотр и выбор AI-моделей
👤 Мой профиль - информация о подписке и лимитах
💳 Купить подписку - выбор и покупка подписок
🔑 Купить API - приобретение API-ключей
🎨 Сгенерировать фото - генерация изображений по описанию
📤 Рефералка - реферальная система
🆘 Помощь - эта справка
⏹️ Остановить - прекращение текущей генерации

<b>Команды:</b>
/start - начать работу с ботом
/generate [описание] - сгенерировать изображение

<b>Поддержка:</b> {Config.SUPPORT_USERNAME}""",
        'en': f"""🆘 <b>GobiAI Help</b>

<b>Menu Panel:</b>
🧠 Choose model - view and select AI models
👤 My profile - subscription info and limits
💳 Buy subscription - choose and buy subscriptions
🔑 Buy API - purchase API keys
🎨 Generate image - generate images from text
📤 Referral - referral system
🆘 Help - this help information
⏹️ Stop - stop current generation

<b>Commands:</b>
/start - start working with bot
/generate [description] - generate image

<b>Support:</b> {Config.SUPPORT_USERNAME}"""
    }
    await message.answer(help_text[lang])

@dp.message(F.text == "⏹️ Остановить")
@dp.message(F.text == "⏹️ Stop")
async def handle_stop(message: types.Message):
    if message.from_user.id in active_generations:
        active_generations[message.from_user.id] = False
        stop_text = {
            'ru': "⏹️ <b>Генерация остановлена</b>",
            'en': "⏹️ <b>Generation stopped</b>"
        }
        user = db.get_user(message.from_user.id)
        lang = user['language'] if user else 'ru'
        await message.answer(stop_text[lang])

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
        price = Config.API_KEY_PRICES.get(model_id, 0)
        api_text = {
            'ru': f"{get_model_info_text(model, lang)}\n\n💰 <b>Цена API-ключа:</b> {price} руб (750K токенов)",
            'en': f"{get_model_info_text(model, lang)}\n\n💰 <b>API Key Price:</b> {price} RUB (750K tokens)"
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
    success_text = {
        'ru': f"✅ <b>Модель {model_name} выбрана!</b>\n\nТеперь отправляйте сообщения для генерации.",
        'en': f"✅ <b>Model {model_name} selected!</b>\n\nNow send messages for generation."
    }
    await callback.message.answer(success_text[lang])
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
🖼️ Генерация изображений: {plan['image_generate']}/день
📤 Отправка изображений: {plan['image_send']}/день
🎥 Отправка видео: {plan['video_send']}/день

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил" для проверки статуса.""",
            'en': f"""💳 <b>Payment for {plan['name_en']}</b>

💰 Amount: {plan['price']} RUB
📅 Duration: 30 days
📊 Limit: {plan['daily_limit']} messages/day
🖼️ Image generation: {plan['image_generate']}/day
📤 Image sending: {plan['image_send']}/day
🎥 Video sending: {plan['video_send']}/day

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
    lang = user['language'] if user
