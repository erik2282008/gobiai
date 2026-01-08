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

# ========== ПОЛНЫЕ ЮРИДИЧЕСКИЕ ДОКУМЕНТЫ С ЛИМИТАМИ ==========
LEGAL_DOCUMENTS = {
    'privacy': """
🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Настоящая Политика конфиденциальности регулирует обработку персональных данных.
1.2. Использование Сервиса означает полное согласие с Политикой.

<b>2. ВЛАДЕЛЕЦ</b>
2.1. Владелец: Симикян Эрик Самвелович
2.2. Контакты: Telegram @smknnnn

<b>3. КОНТАКТЫ</b>
По вопросам: @smknnnn
""",

    'agreement': """
📋 <b>ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Соглашение является публичной офертой.
1.2. Использование Сервиса означает акцепт оферты.

<b>2. ЛИМИТЫ И ОГРАНИЧЕНИЯ</b>
2.1. <b>Бесплатный тариф:</b> 100 сообщений/день
2.2. <b>Lite (15₽):</b> 200 сообщений/день
2.3. <b>Lite+ (399₽):</b> 350 сообщений/день
2.4. <b>VIP (1499₽):</b> 500 сообщений/день
2.5. <b>VIP+ (4999₽):</b> 1000 сообщений/день
2.6. <b>Quantum (19999₽):</b> 2000 сообщений/день
2.7. <b>Quantum Pro (49999₽):</b> 5000 сообщений/день
2.8. <b>Quantum Infinite (149999₽):</b> 9000 сообщений/день

<b>3. ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ</b>
3.1. <b>Бесплатный:</b> 1 генерация/день
3.2. <b>Lite:</b> 3 генерации/день
3.3. <b>Lite+:</b> 5 генераций/день
3.4. <b>VIP:</b> 7 генераций/день
3.5. <b>VIP+:</b> 10 генераций/день
3.6. <b>Quantum:</b> 30 генераций/день
3.7. <b>Quantum Pro:</b> 60 генераций/день
3.8. <b>Quantum Infinite:</b> 85 генераций/день

<b>4. ОТПРАВКА ИЗОБРАЖЕНИЙ</b>
4.1. <b>Бесплатный:</b> 2 изображения/день
4.2. <b>Lite:</b> 5 изображений/день
4.3. <b>Lite+:</b> 20 изображений/день
4.4. <b>VIP:</b> 35 изображений/день
4.5. <b>VIP+:</b> 40 изображений/день
4.6. <b>Quantum:</b> 60 изображений/день
4.7. <b>Quantum Pro:</b> 110 изображений/день
4.8. <b>Quantum Infinite:</b> 250 изображений/день

<b>5. ОТПРАВКА ВИДЕО</b>
5.1. <b>Бесплатный:</b> 1 видео/день
5.2. <b>Lite:</b> 2 видео/день
5.3. <b>Lite+:</b> 4 видео/день
5.4. <b>VIP:</b> 7 видео/день
5.5. <b>VIP+:</b> 10 видео/день
5.6. <b>Quantum:</b> 15 видео/день
5.7. <b>Quantum Pro:</b> 22 видео/день
5.8. <b>Quantum Infinite:</b> 50 видео/день

<b>6. МЕСЯЧНЫЕ ЛИМИТЫ ТОКЕНОВ</b>
6.1. <b>Бесплатный:</b> 15,000 токенов/месяц
6.2. <b>Литe:</b> 100,000 токенов/месяц
6.3. <b>Lite+:</b> 220,000 токенов/месяц
6.4. <b>VIP:</b> 600,000 токенов/месяц
6.5. <b>VIP+:</b> 700,000 токенов/месяц
6.6. <b>Quantum:</b> 750,000 токенов/месяц
6.7. <b>Quantum Pro:</b> 800,000 токенов/месяц
6.8. <b>Quantum Infinite:</b> 900,000 токенов/месяц

<b>7. ОГРАНИЧЕНИЕ ОТВЕТСТВЕННОСТИ</b>
7.1. Администрация НЕ НЕСЕТ ОТВЕТСТВЕННОСТИ.
7.2. Максимальная ответственность ограничена стоимостью подписки.
""",

    'payment': """
💳 <b>УСЛОВИЯ ОПЛАТЫ И ВОЗВРАТОВ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Оплата услуг осуществляется через ЮKassa.
1.2. Цены указаны в российских рублях.

<b>2. ВОЗВРАТ СРЕДСТВ</b>
2.1. <b>ВОЗВРАТ СРЕДСТВ НЕВОЗМОЖЕН</b> при использовании услуг.
2.2. <b>ЗА НЕВНИМАТЕЛЬНОСТЬ ОТВЕТСТВЕННОСТИ НЕ НЕСЕМ</b>
""",

    'subscription': """
📄 <b>ДОГОВОР ПОДПИСКИ GobiAI Bot</b>

<b>1. ПРЕДМЕТ ДОГОВОРА</b>
1.1. Предоставление доступа к AI-моделям по подписке.
1.2. Договор является публичной офертой.

<b>2. УСЛОВИЯ ПОДПИСКИ</b>
2.1. Подписка действует 30 дней с момента активации.
2.2. Подробные лимиты указаны в Пользовательском соглашении.

<b>3. ОТВЕТСТВЕННОСТЬ</b>
3.1. Администрация не гарантирует бесперебойную работу.
3.2. <b>ВОЗВРАТ СРЕДСТВ ПРИ ДОСРОЧНОМ ПРЕКРАЩЕНИИ НЕВОЗМОЖЕН</b>.
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

# ========== ИНФОРМАЦИЯ О ПОДПИСКАХ С МОДЕЛЯМИ ==========
def get_plan_info_text(plan, lang='ru'):
    """Возвращает подробную информацию о подписке с моделями"""
    available_categories = Config.SUBSCRIPTION_ACCESS.get(plan['id'], ['free'])
    models_text = ""
    
    for category in available_categories:
        if category in Config.AI_MODELS:
            for model in Config.AI_MODELS[category]:
                name = model['name'] if lang == 'ru' else model['name_en']
                description = model['description_ru'] if lang == 'ru' else model['description_en']
                models_text += f"• {name}: {description}\n"
    
    if lang == 'ru':
        return f"""💎 <b>{plan['name']}</b>

💰 Цена: {plan['price']} руб/месяц
📅 Срок: 30 дней
✨ Доступ к премиум моделям

<b>Включенные модели:</b>
{models_text}

<b>Лимиты:</b>
📊 {plan['daily_limit']} сообщений/день
🖼 {plan['image_generate']} генераций изображений/день
📤 {plan['image_send']} отправок изображений/день
🎬 {plan['video_send']} отправок видео/день"""
    else:
        return f"""💎 <b>{plan['name_en']}</b>

💰 Price: {plan['price']} RUB/month
📅 Duration: 30 days
✨ Access to premium models

<b>Included models:</b>
{models_text}

<b>Limits:</b>
📊 {plan['daily_limit']} messages/day
🖼 {plan['image_generate']} image generations/day
📤 {plan['image_send']} image sends/day
🎬 {plan['video_send']} video sends/day"""

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

# ========== ЮРИДИЧЕСКИЕ ДОКУМЕНТЫ ОБРАБОТЧИКИ ==========
@dp.callback_query(F.data == "legal_docs")
async def show_legal_docs(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    
    text = {
        'ru': "📄 <b>Юридические документы</b>\n\nВыберите документ для ознакомления:",
        'en': "📄 <b>Legal Documents</b>\n\nSelect a document to review:"
    }
    await callback.message.answer(text[lang], reply_markup=get_legal_docs_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data.startswith("doc_"))
async def show_legal_doc(callback: types.CallbackQuery):
    doc_type = callback.data.replace("doc_", "")
    
    if doc_type in LEGAL_DOCUMENTS:
        await callback.message.answer(LEGAL_DOCUMENTS[doc_type])
    else:
        await callback.answer("❌ Документ не найден")
    await callback.answer()

# ========== УЛУЧШЕННАЯ ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ ==========
@dp.message(F.text == "🎨 Сгенерировать фото")
@dp.message(F.text == "🎨 Generate image")
async def handle_generate_image_menu(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    text = {
        'ru': "🎨 <b>Генерация изображений</b>\n\nИспользуйте команду /generate с описанием:\n\n<code>/generate красная спортивная машина в горах</code>",
        'en': "🎨 <b>Image Generation</b>\n\nUse /generate command with description:\n\n<code>/generate red sports car in mountains</code>"
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
        await message.answer(f"❌ {error_msg}")
        return
    
    lang = user['language']
    msg = await message.answer("🎨 <b>Генерация изображения...</b>")
    active_generations[message.from_user.id] = True
    
    try:
        # Используем специальную модель для генерации изображений
        result = await routerai_service.generate_image(prompt)
        
        if result['success'] and active_generations.get(message.from_user.id):
            db.update_media_usage(user['user_id'], 'image_generate')
            
            if result.get('image_data'):
                image_data = base64.b64decode(result['image_data'])
                await message.answer_photo(
                    types.BufferedInputFile(image_data, filename="generated_image.jpg"),
                    caption=f"🎨 <b>Сгенерированное изображение</b>\n\nЗапрос: {prompt}"
                )
                await msg.delete()
            else:
                await msg.edit_text("❌ Не удалось загрузить изображение")
        elif not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            if "timeout" in error_msg.lower():
                error_msg = "⏳ Время генерации истекло. Попробуйте позже."
            elif "limit" in error_msg.lower():
                error_msg = "🚫 Достигнут лимит генерации. Попробуйте позже."
            else:
                error_msg = f"❌ Ошибка генерации: {error_msg}"
            await msg.edit_text(error_msg)
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await msg.edit_text("❌ <b>Ошибка при генерации изображения</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

# ========== ОБРАБОТКА МЕДИАФАЙЛОВ ==========
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
        await message.answer("❌ Текущая модель не поддерживает изображения")
        return
    
    # Скачиваем изображение
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_data = base64.b64encode(file_bytes.read()).decode('utf-8')
    except Exception as e:
        await message.answer("❌ Ошибка при загрузке изображения")
        return
    
    msg = await message.answer("⏳ <b>Обработка изображения...</b>")
    active_generations[message.from_user.id] = True
    
    try:
        # Проверяем месячные лимиты токенов
        can_use, error_msg = db.check_monthly_token_limits(message.from_user.id, 500, 1500)
        if not can_use:
            await msg.edit_text(f"❌ {error_msg}")
            return
        
        result = await routerai_service.send_message(
            user['current_model'], 
            message.caption or "Опиши это изображение",
            extra_data={"image": image_data}
        )
        
        if result['success'] and active_generations.get(message.from_user.id):
            response_text = f"🤖 <b>Ответ:</b>\n\n{result['response']}"
            await msg.edit_text(response_text)
            
            # Обновляем счетчики токенов
            db.update_token_usage(message.from_user.id, 500, 1500)
        elif not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            if "timeout" in error_msg.lower():
                error_msg = "⏳ Время обработки истекло."
            else:
                error_msg = f"❌ Ошибка: {error_msg}"
            await msg.edit_text(error_msg)
            
    except Exception as e:
        logger.error(f"Photo processing error: {e}")
        await msg.edit_text("❌ <b>Ошибка обработки изображения</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

@dp.message(F.video)
async def handle_video(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    # Проверяем лимиты отправки видео
    can_send, error_msg = db.can_send_video(user['user_id'])
    if not can_send: 
        await message.answer(f"❌ {error_msg}")
        return
        
    # Проверяем общие лимиты
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: 
        await message.answer(f"❌ {error_msg}")
        return
        
    db.increment_daily_usage(user['user_id'])
    db.update_media_usage(user['user_id'], 'video_send')
    
    msg = await message.answer("⏳ <b>Обработка видео...</b>")
    active_generations[message.from_user.id] = True
    
    try:
        result = await routerai_service.send_message(
            user['current_model'], 
            f"Пользователь отправил видео. Описание: {message.caption or 'нет описания'}. Проанализируй видео на основе запроса."
        )
        
        if result['success'] and active_generations.get(message.from_user.id):
            response_text = f"🤖 <b>Анализ видео:</b>\n\n{result['response']}"
            await msg.edit_text(response_text)
        elif not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            await msg.edit_text(f"❌ Ошибка: {error_msg}")
            
    except Exception as e:
        logger.error(f"Video processing error: {e}")
        await msg.edit_text("❌ <b>Ошибка обработки видео</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

@dp.message(F.document)
async def handle_document(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: 
        await message.answer(f"❌ {error_msg}")
        return
        
    db.increment_daily_usage(user['user_id'])
    
    msg = await message.answer("⏳ <b>Обработка документа...</b>")
    active_generations[message.from_user.id] = True
    
    try:
        result = await routerai_service.send_message(
            user['current_model'], 
            f"Пользователь отправил документ. Название: {message.document.file_name}. Описание: {message.caption or 'нет описания'}."
        )
        
        if result['success'] and active_generations.get(message.from_user.id):
            response_text = f"🤖 <b>Анализ документа:</b>\n\n{result['response']}"
            await msg.edit_text(response_text)
        elif not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            await msg.edit_text(f"❌ Ошибка: {error_msg}")
            
    except Exception as e:
        logger.error(f"Document processing error: {e}")
        await msg.edit_text("❌ <b>Ошибка обработки документа</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

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

📊 <b>Использовано сегодня:</b>
Сообщения: {user['daily_used']}
Сгенерировано изображений: {user['images_generated_today']}
Отправлено изображений: {user['images_sent_today']}
Отправлено видео: {user['videos_sent_today']}

🤖 Текущая модель: {user['current_model']}""",
        'en': f"""👤 <b>Your Profile</b>

💎 Subscription: {plan['name_en'] if plan else 'Free'}
📅 Days until subscription end: {days_left}
🎁 Days until trial end: {trial_days_left}
👥 Referrals invited: {user['referral_count']}

📊 <b>Used today:</b>
Messages: {user['daily_used']}
Images generated: {user['images_generated_today']}
Images sent: {user['images_sent_today']}
Videos sent: {user['videos_sent_today']}

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

# ========== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ==========
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
        # Оцениваем токены для запроса
        input_tokens = len(message.text) * 2
        output_estimate = 1500
        total_tokens = input_tokens + output_estimate
        
        # Проверяем месячные лимиты
        can_use, error_msg = db.check_monthly_token_limits(user_id, input_tokens, output_estimate)
        if not can_use:
            await msg.edit_text(f"❌ {error_msg}")
            return
        
        result = await routerai_service.send_message(
            user['current_model'], 
            message.text,
            user_conversations[user_id][:-1]
        )
        
        if result['success'] and active_generations.get(user_id):
            user_conversations[user_id].append({"role": "assistant", "content": result['response']})
            cleaned_response = result['response']
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{cleaned_response}")
            
            # Оцениваем реальное количество токенов
            if 'usage' in result:
                actual_input = result['usage'].get('prompt_tokens', 0)
                actual_output = result['usage'].get('completion_tokens', 0)
                db.update_token_usage(user_id, actual_input, actual_output)
            
        elif not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            if "timeout" in error_msg.lower():
                error_msg = "⏳ Время ответа истекло."
            else:
                error_msg = f"❌ Ошибка: {error_msg}"
            await msg.edit_text(error_msg)
            
    except Exception as e:
        logger.error(f"Message processing error: {e}")
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
    logger.info("Starting GobiAI bot with all features...")
    
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

