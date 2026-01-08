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
6.2. <b>Лите:</b> 100,000 токенов/месяц
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

# ========== ИНФОРМАЦИЯ О ПОДПИСКАХ БЕЗ ЛИМИТОВ ==========
def get_plan_info_text(plan, lang='ru'):
    """Возвращает информацию о подписке без лимитов"""
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

<i>Подробные лимиты использования указаны в Пользовательском соглашении</i>"""
    else:
        return f"""💎 <b>{plan['name_en']}</b>

💰 Price: {plan['price']} RUB/month
📅 Duration: 30 days
✨ Access to premium models

<b>Included models:</b>
{models_text}

<i>Detailed usage limits are specified in the User Agreement</i>"""

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
        # Используем модель, которая умеет генерировать изображения
        result = await routerai_service.send_message(
            "google/gemini-2.5-flash-image", 
            f"Сгенерируй изображение по описанию: '{prompt}'. Верни только URL готового изображения."
        )
        
        if result['success'] and active_generations.get(message.from_user.id):
            response_text = result['response'].strip()
            db.update_media_usage(user['user_id'], 'image_generate')
            
            # Проверяем наличие URL изображения
            if response_text.startswith('http') and any(ext in response_text.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                try:
                    await message.answer_photo(
                        response_text,
                        caption=f"🎨 <b>Сгенерированное изображение</b>\n\nЗапрос: {prompt}"
                    )
                    await msg.delete()
                except:
                    await msg.edit_text(f"🖼️ <b>Изображение сгенерировано!</b>\n\nURL: {response_text}\n\nЗапрос: {prompt}")
            else:
                await msg.edit_text(f"🎨 <b>Результат генерации:</b>\n\n{response_text}")
                
        elif not result['success']:
            error_msg = result.get('error', 'Неизвестная ошибка')
            await msg.edit_text(f"❌ Ошибка генерации: {error_msg}")
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await msg.edit_text("❌ <b>Ошибка при генерации изображения</b>")
    finally:
        active_generations.pop(message.from_user.id, None)

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
        # Проверяем, является ли запрос просьбой сгенерировать изображение
        is_image_request = any(word in message.text.lower() for word in [
            'сгенерируй', 'генерация', 'изображение', 'картинка', 'фото', 'picture', 'generate', 'image',
            'нарисуй', 'draw', 'создай', 'create', 'иллюстрация', 'illustration'
        ])
        
        if is_image_request:
            # Проверяем лимиты генерации изображений
            can_generate, error_msg = db.can_generate_image(user_id)
            if not can_generate:
                await msg.edit_text(f"❌ {error_msg}")
                return
            
            # Используем модель для генерации изображений
            result = await routerai_service.send_message(
                "google/gemini-2.5-flash-image", 
                f"Пользователь просит сгенерировать изображение: '{message.text}'. Верни только URL готового изображения."
            )
            
            if result['success'] and active_generations.get(user_id):
                response_text = result['response'].strip()
                db.update_media_usage(user_id, 'image_generate')
                
                # Проверяем наличие URL изображения
                if response_text.startswith('http') and any(ext in response_text.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    try:
                        await message.answer_photo(
                            response_text,
                            caption=f"🎨 <b>Сгенерированное изображение</b>\n\nЗапрос: {message.text}"
                        )
                        await msg.delete()
                    except:
                        await msg.edit_text(f"🖼️ <b>Изображение сгенерировано!</b>\n\nURL: {response_text}\n\nЗапрос: {message.text}")
                else:
                    await msg.edit_text(f"🎨 <b>Результат генерации:</b>\n\n{response_text}")
                
                return
        
        # Обычный текстовый запрос
        input_tokens = len(message.text) * 2
        output_estimate = 1500
        
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
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{result['response']}")
            
            # Обновляем счетчики токенов
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
            
            # Обновляем
