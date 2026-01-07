import asyncio
import logging
import uuid
import json
import base64
import sqlite3
import os
from datetime import datetime, timedelta
from aiohttp import web
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

# Увеличиваем таймауты для работы на Heroku/Koyeb
os.environ['AIOHTTP_TIMEOUT'] = '60'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем сессию с увеличенными таймаутами
session = AiohttpSession(timeout=60)

# Создаем бота с кастомной сессией
bot = Bot(
    token=Config.BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode='HTML'),
    session=session
)

dp = Dispatcher()

active_generations = {}
user_conversations = {}

# ========== ЮРИДИЧЕСКИЕ ДОКУМЕНТЫ ==========
LEGAL_DOCUMENTS = {
    'privacy': """
🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
Администрация сервиса GobiAI Bot уважает вашу конфиденциальность и защищает персональные данные.

<b>2. ВЛАДЕЛЕЦ</b>
Симикян Эрик Самвелович
Telegram: @smknnnn

<b>3. ОБРАБАТЫВАЕМЫЕ ДАННЫЕ</b>
• ID пользователя Telegram
• Имя пользователя
• Статистика использования
• История сообщений

<b>4. ЦЕЛИ ОБРАБОТКИ</b>
• Предоставление услуг AI-ассистента
• Обработка платежей
• Улучшение сервиса

<b>5. КОНТАКТЫ</b>
По вопросам: @smknnnn
""",

    'agreement': """
📋 <b>ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ GobiAI Bot</b>

<b>1. ПРЕДМЕТ СОГЛАШЕНИЯ</b>
Предоставление доступа к AI-моделям через Telegram бота.

<b>2. УСЛОВИЯ ИСПОЛЬЗОВАНИЯ</b>
2.1. Использование Сервиса означает согласие с условиями
2.2. Запрещен спам, мошенничество, нарушение законов

<b>3. ОТВЕТСТВЕННОСТЬ</b>
3.1. Администрация не несет ответственности за:
• Точность генерируемого контента
• Убытки пользователей
• Технические сбои

<b>4. ОПЛАТА И ВОЗВРАТЫ</b>
4.1. Оплата через ЮKassa
4.2. Возврат при начале использования невозможен

<b>5. КОНТАКТЫ</b>
Telegram: @smknnnn
""",

    'payment': """
💳 <b>УСЛОВИЯ ОПЛАТЫ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
Оплата услуг осуществляется через платежную систему ЮKassa.

<b>2. ПОРЯДОК ОПЛАТЫ</b>
2.1. Цены в рублях
2.2. Оплата единовременная за период

<b>3. ВОЗВРАТ СРЕДСТВ</b>
3.1. Возврат невозможен после начала использования услуг
3.2. Возврат возможен только при технических ошибках

<b>4. БЕЗОПАСНОСТЬ</b>
4.1. Все платежи защищены PCI DSS
4.2. Данные карт не хранятся на серверах

<b>5. КОНТАКТЫ</b>
По вопросам оплаты: @smknnnn
""",

    'subscription': """
📄 <b>ДОГОВОР ПОДПИСКИ GobiAI Bot</b>

<b>1. ПРЕДМЕТ ДОГОВОРА</b>
Предоставление доступа к AI-моделям по подписке.

<b>2. АКТИВАЦИЯ</b>
2.1. Подписка активируется после оплаты
2.2. Срок: 30 дней с момента активации

<b>3. ПРАВА И ОБЯЗАННОСТИ</b>
3.1. Администрация обеспечивает доступ к функционалу
3.2. Пользователь соблюдает правила использования

<b>4. ПРЕКРАЩЕНИЕ</b>
4.1. Автоматически по истечении срока
4.2. Возврат при досрочном прекращении невозможен

<b>5. РЕКВИЗИТЫ</b>
Владелец: Симикян Эрик Самвелович
Контакт: @smknnnn
"""
}

# ========== МЕНЮ-ПАНЕЛЬ ==========
def get_main_reply_keyboard(lang='ru'):
    if lang == 'ru':
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧠 Выбрать модель"), KeyboardButton(text="👤 Мой профиль")],
                [KeyboardButton(text="💳 Купить подписку"), KeyboardButton(text="🔑 Купить API")],
                [KeyboardButton(text="🎨 Сгенерировать фото"), KeyboardButton(text="📤 Рефералка")],
                [KeyboardButton(text="🆘 Помощь")]
            ],
            resize_keyboard=True
        )
    else:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧠 Choose model"), KeyboardButton(text="👤 My profile")],
                [KeyboardButton(text="💳 Buy subscription"), KeyboardButton(text="🔑 Buy API")],
                [KeyboardButton(text="🎨 Generate image"), KeyboardButton(text="📤 Referral")],
                [KeyboardButton(text="🆘 Help")]
            ],
            resize_keyboard=True
        )

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
                InlineKeyboardButton(text=f"ℹ️ {name} - {price}₽", callback_data=f"api_info_{model_id}"),
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

def get_profile_keyboard(lang='ru'):
    if lang == 'ru':
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Юридические документы", callback_data="legal_docs")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Legal Documents", callback_data="legal_docs")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
        ])

def get_legal_docs_keyboard(lang='ru'):
    if lang == 'ru':
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Политика конфиденциальности", callback_data="doc_privacy")],
            [InlineKeyboardButton(text="📋 Пользовательское соглашение", callback_data="doc_agreement")],
            [InlineKeyboardButton(text="💳 Условия оплаты", callback_data="doc_payment")],
            [InlineKeyboardButton(text="📄 Договор подписки", callback_data="doc_subscription")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Privacy Policy", callback_data="doc_privacy")],
            [InlineKeyboardButton(text="📋 User Agreement", callback_data="doc_agreement")],
            [InlineKeyboardButton(text="💳 Payment Terms", callback_data="doc_payment")],
            [InlineKeyboardButton(text="📄 Subscription Terms", callback_data="doc_subscription")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
        ])

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
    if lang == 'ru':
        return f"""💎 <b>{plan['name']}</b>

💰 Цена: {plan['price']} руб/месяц
📈 Лимит сообщений: {plan['daily_limit']}/день
🖼 Генерация изображений: {plan['image_generate']}/день
📤 Отправка изображений: {plan['image_send']}/день
🎥 Отправка видео: {plan['video_send']}/день"""
    else:
        return f"""💎 <b>{plan['name_en']}</b>

💰 Price: {plan['price']} RUB/month
📈 Message limit: {plan['daily_limit']}/day
🖼 Image generation: {plan['image_generate']}/day
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

# ========== ЮРИДИЧЕСКИЕ ДОКУМЕНТЫ ==========
@dp.callback_query(F.data == "legal_docs")
async def show_legal_docs(callback: types.CallbackQuery):
    await callback.message.answer("📄 <b>Выберите документ:</b>", reply_markup=get_legal_docs_keyboard('ru'))
    await callback.answer()

@dp.callback_query(F.data.startswith("doc_"))
async def show_legal_doc(callback: types.CallbackQuery):
    doc_type = callback.data.replace("doc_", "")
    
    if doc_type in LEGAL_DOCUMENTS:
        await callback.message.answer(LEGAL_DOCUMENTS[doc_type])
    else:
        await callback.answer("❌ Документ не найден")
    await callback.answer()

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    referral_code = None
    if len(message.text.split()) > 1:
        referral_code = message.text.split()[1]
    
    user = db.get_user(message.from_user.id)
    if not user:
        user = db.create_user(message.from_user.id, message.from_user.username, 'ru', referral_code)
        
        welcome_text = f"""👋 <b>Добро пожаловать в GobiAI!</b>

✨ <b>Бесплатный триал на {Config.TRIAL_MONTHS} месяца активирован!</b>"""
        
        if user['referred_by']:
            welcome_text += f"\n\n🎁 <b>Активирована подписка Lite на 10 дней по реферальной ссылке!</b>"
        
        await message.answer(welcome_text, reply_markup=get_main_reply_keyboard('ru'))
    else:
        await message.answer("👋 <b>С возвращением!</b>", reply_markup=get_main_reply_keyboard(user['language']))

@dp.message(F.text == "🧠 Выбрать модель")
@dp.message(F.text == "🧠 Choose model")
async def handle_models(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    await message.answer("🤖 <b>Выберите AI-модель</b>", reply_markup=get_models_keyboard(user['subscription'], lang))

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
    
    profile_text = {
        'ru': f"""👤 <b>Ваш профиль</b>

💎 Подписка: {plan['name'] if plan else 'Free'}
📅 Дней до конца подписки: {days_left}
👥 Приглашено рефералов: {user['referral_count']}

📊 <b>Использовано сегодня:</b>
Сообщения: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
Сгенерировано изображений: {user['images_generated_today']}/{plan['image_generate'] if plan else 0}
Отправлено изображений: {user['images_sent_today']}/{plan['image_send'] if plan else 0}

🤖 Текущая модель: {user['current_model']}""",
        'en': f"""👤 <b>Your Profile</b>

💎 Subscription: {plan['name_en'] if plan else 'Free'}
📅 Days until subscription end: {days_left}
👥 Referrals invited: {user['referral_count']}

📊 <b>Used today:</b>
Messages: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
Images generated: {user['images_generated_today']}/{plan['image_generate'] if plan else 0}
Images sent: {user['images_sent_today']}/{plan['image_send'] if plan else 0}

🤖 Current model: {user['current_model']}"""
    }
    await message.answer(profile_text[lang], reply_markup=get_profile_keyboard(lang))

@dp.message(F.text == "💳 Купить подписку")
@dp.message(F.text == "💳 Buy subscription")
async def handle_buy_subscription(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    await message.answer("💎 <b>Выберите подписку</b>", reply_markup=get_subscription_keyboard(lang))

@dp.message(F.text == "🔑 Купить API")
@dp.message(F.text == "🔑 Buy API")
async def handle_buy_api(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    await message.answer("🔑 <b>Купить API-ключ</b>", reply_markup=get_api_key_keyboard(lang))

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

🔗 <b>Ваша реферальная ссылка:</b>
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}""",
        'en': f"""📤 <b>Referral System</b>

👥 Users invited: {user['referral_count']}

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
🧠 Выбрать модель - выбор AI-моделей
👤 Мой профиль - информация + юр.документы
💳 Купить подписку - покупка подписок
🔑 Купить API - покупка API-ключей
🎨 Сгенерировать фото - генерация изображений
📤 Рефералка - реферальная система
🆘 Помощь - эта справка

<b>Команды:</b>
/start - начать работу
/generate [описание] - сгенерировать изображение

<b>Поддержка:</b> {Config.SUPPORT_USERNAME}""",
        'en': f"""🆘 <b>GobiAI Help</b>

<b>Menu Panel:</b>
🧠 Choose model - select AI models
👤 My profile - info + legal docs
💳 Buy subscription - buy subscriptions
🔑 Buy API - buy API keys
🎨 Generate image - generate images
📤 Referral - referral system
🆘 Help - this help

<b>Commands:</b>
/start - start working
/generate [description] - generate image

<b>Support:</b> {Config.SUPPORT_USERNAME}"""
    }
    await message.answer(help_text[lang])

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    await callback.message.answer("🔙 <b>Возврат в главное меню</b>", reply_markup=get_main_reply_keyboard(lang))
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
    await callback.message.answer(f"✅ <b>Модель {model_name} выбрана!</b>")
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

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил" для проверки статуса.""",
            'en': f"""💳 <b>Payment for {plan['name_en']}</b>

💰 Amount: {plan['price']} RUB
📅 Duration: 30 days

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ After payment, click "✅ I paid" to check status."""
        }
        await callback.message.answer(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        await callback.message.answer("❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже.")
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

💰 Стоимость: {price} руб (750K токенов)

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил"

📩 После подтверждения обратитесь к {Config.SUPPORT_USERNAME}""",
            'en': f"""🔑 <b>API Key Purchase {model_name}</b>

💰 Price: {price} RUB (750K tokens)

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ After payment, click "✅ I paid"

📩 After confirmation, contact {Config.SUPPORT_USERNAME}"""
        }
        await callback.message.answer(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        await callback.message.answer("❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже.")
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
    
    await callback.message.answer("⏳ <b>Проверяем статус платежа...</b>")
    
    result = await check_payment_status(payment_id, payment['yookassa_payment_id'], payment['user_id'])
    if not result:
        await callback.message.answer("❌ <b>Платеж еще не подтвержден</b>\n\nПопробуйте позже.")
    await callback.answer()

@dp.callback_query(F.data == "share_ref")
async def share_referral(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    ref_text = {
        'ru': f"""📤 <b>Поделиться реферальной ссылкой</b>

🔗 Ваша ссылка:
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}

💎 Приглашайте друзей!""",
        'en': f"""📤 <b>Share referral link</b>

🔗 Your link:
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}

💎 Invite friends!"""
    }
    await callback.message.answer(ref_text[user['language']])
    await callback.answer()

# ========== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ ==========
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
        await message.answer(f"❌ {error_msg}")
        return
    
    lang = user['language']
    msg = await message.answer("🎨 <b>Генерация изображения...</b>")
    active_generations[message.from_user.id] = True
    
    try:
        result = await routerai_service.generate_image(prompt, model_id=Config.IMAGE_GENERATION_MODEL)
        
        if result['success'] and active_generations.get(message.from_user.id):
            db.update_media_usage(user['user_id'], 'image_generate')
            
            if result.get('image_data'):
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
        await msg.edit_text("❌ <b>Ошибка при генерации изображения</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
@dp.message(F.text)
async def handle_message(message: types.Message):
    # Пропускаем команды меню
    menu_commands = ["🧠 Выбрать модель", "👤 Мой профиль", "💳 Купить подписку", "🔑 Купить API", 
                    "🎨 Сгенерировать фото", "📤 Рефералка", "🆘 Помощь",
                    "🧠 Choose model", "👤 My profile", "💳 Buy subscription", "🔑 Buy API",
                    "🎨 Generate image", "📤 Referral", "🆘 Help"]
    
    if message.text in menu_commands:
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
    msg = await message.answer("⏳ <b>Генерация началась...</b>")
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
                            'ru': "✅ <b>Платеж автоматически подтвержден! Подписка активирована.</b>",
                            'en': "✅ <b>Payment automatically confirmed! Subscription activated.</b>"
                        }
                    else:
                        success_text = {
                            'ru': f"✅ <b>Платеж автоматически подтвержден!</b>\n\nОбратитесь к {Config.SUPPORT_USERNAME} для получения ключа",
                            'en': f"✅ <b>Payment automatically confirmed!</b>\n\nContact {Config.SUPPORT_USERNAME} for your key"
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
    logger.info("Starting GobiAI bot with all fixes...")
    
    try:
        # Проверяем подключение
        await bot.get_me()
        logger.info("Bot connected successfully")
    except Exception as e:
        logger.error(f"Bot connection failed: {e}")
        return
    
    # Запускаем сервер для вебхуков
    runner = await start_webhook_server()
    
    logger.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
