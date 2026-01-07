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
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
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

# ========== ЮРИДИЧЕСКИЕ ДОКУМЕНТЫ (ПОЛНЫЕ) ==========
LEGAL_DOCUMENTS = {
    'privacy_policy': """
🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Настоящая Политика конфиденциальности регулирует отношения между Администрацией сервиса GobiAI Bot и Пользователем относительно обработки персональных данных.
1.2. Используя Сервис, Вы выражаете свое безусловное согласие с настоящей Политикой.

<b>2. ВЛАДЕЛЕЦ И АДМИНИСТРАТОР</b>
2.1. Владелец: Симикян Эрик Самвелович
2.2. Контактные данные: Telegram @smknnnn

<b>3. ОБРАБАТЫВАЕМЫЕ ДАННЫЕ</b>
3.1. Персональные данные:
• Идентификатор пользователя Telegram (User ID)
• Имя пользователя (username)
• Статистика использования сервиса
• История сообщений и запросов
• Данные о платежах и подписках

<b>4. ЦЕЛИ ОБРАБОТКИ ДАННЫХ</b>
4.1. Предоставление услуг AI-ассистента
4.2. Обработка платежей и управление подписками
4.3. Улучшение качества Сервиса
4.4. Соблюдение законодательства Российской Федерации

<b>5. ХРАНЕНИЕ И ЗАЩИТА ДАННЫХ</b>
5.1. Данные хранятся в зашифрованном виде на защищенных серверах
5.2. Срок хранения: 5 лет с момента последней активности
5.3. Доступ к данным имеют только уполномоченные сотрудники

<b>6. ПРАВА ПОЛЬЗОВАТЕЛЯ</b>
6.1. Право на доступ к своим персональным данным
6.2. Право на исправление неточных данных
6.3. Право на удаление данных
6.4. Право на отзыв согласия на обработку данных

<b>7. КОНТАКТЫ</b>
По всем вопросам: Telegram @smknnnn
""",

    'user_agreement': """
📋 <b>ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Настоящее Соглашение регулирует отношения между Администрацией сервиса GobiAI Bot и Пользователем.
1.2. Соглашение является публичной офертой в соответствии со ст. 437 ГК РФ.

<b>2. ПРЕДМЕТ СОГЛАШЕНИЯ</b>
2.1. Администрация предоставляет Пользователю доступ к AI-моделям через Telegram бота.
2.2. Услуги предоставляются на условиях «как есть» (as is).

<b>3. ОГРАНИЧЕНИЯ ИСПОЛЬЗОВАНИЯ</b>
3.1. Запрещается:
• Распространение незаконного контента
• Нарушение авторских прав
• Мошеннические действия
• Спам и массовые рассылки

<b>4. ОТВЕТСТВЕННОСТЬ</b>
4.1. Администрация не несет ответственности за:
• Точность генерируемого контента
• Убытки Пользователя
• Технические сбои

<b>5. ОПЛАТА И ВОЗВРАТЫ</b>
5.1. Оплата услуг производится через ЮKassa.
5.2. При начале использования услуг возврат невозможен.

<b>6. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ</b>
6.1. Соглашение действует с момента начала использования Сервиса.
6.2. Администрация вправе вносить изменения в Соглашение.
""",

    'payment_terms': """
💳 <b>УСЛОВИЯ ОПЛАТЫ И ВОЗВРАТОВ GobiAI Bot</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Настоящие Условия оплаты регулируют порядок расчетов между Пользователем и Администрацией.

<b>2. ПОРЯДОК ОПЛАТЫ</b>
2.1. Цены указаны в российских рублях (RUB).
2.2. Оплата производится единовременно за выбранный период.

<b>3. ВОЗВРАТ СРЕДСТВ</b>
3.1. Возврат средств НЕВОЗМОЖЕН в случаях:
• Начала использования оплаченных услуг
• Истечения 14 дней с момента оплаты

<b>4. БЕЗОПАСНОСТЬ ПЛАТЕЖЕЙ</b>
4.1. Все транзакции защищены стандартом PCI DSS.
4.2. Данные банковских карт не хранятся на серверах.

<b>5. КОНТАКТЫ</b>
По вопросам оплаты: Telegram @smknnnn
""",

    'subscription_terms': """
📄 <b>ДОГОВОР ПОДПИСКИ НА УСЛУГИ GobiAI Bot</b>

<b>1. ПРЕДМЕТ ДОГОВОРА</b>
1.1. Настоящий Договор является публичной офертой на предоставление услуг доступа к AI-моделям.

<b>2. ПОРЯДОК АКТИВАЦИИ</b>
2.1. Подписка активируется после успешного поступления оплаты.
2.2. Срок действия: 30 календарных дней с момента активации.

<b>3. ПРАВА И ОБЯЗАННОСТИ</b>
3.1. Администрация обязуется обеспечивать доступ к заявленному функционалу.
3.2. Пользователь обязуется соблюдать условия использования.

<b>4. ПРЕКРАЩЕНИЕ ДЕЙСТВИЯ</b>
4.1. Подписка автоматически прекращается по истечении оплаченного периода.
4.2. Возврат средств при досрочном прекращении не производится.

<b>5. РЕКВИЗИТЫ</b>
Владелец: Симикян Эрик Самвелович
Контакт: Telegram @smknnnn
"""
}

# ========== МЕНЮ-ПАНЕЛЬ (БЕЗ КНОПКИ ОСТАНОВИТЬ) ==========
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
    for plan in Config.SUBSCRIPTION_PLANS[1:]:  # Пропускаем бесплатный
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
🖼 Генерация изображений: {plan['image_generate']}/день
📤 Отправка изображений: {plan['image_send']}/день
🎥 Отправка видео: {plan['video_send']}/день

<b>Доступные модели:</b>
{', '.join(available_models[:3])}{'...' if len(available_models) > 3 else ''}"""
    else:
        return f"""💎 <b>{plan['name_en']}</b>

💰 Price: {plan['price']} RUB/month
📈 Message limit: {plan['daily_limit']}/day
🖼 Image generation: {plan['image_generate']}/day
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
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    
    if doc_type in LEGAL_DOCUMENTS:
        doc_text = LEGAL_DOCUMENTS[doc_type]
        
        # Разбиваем на части по 4000 символов
        if len(doc_text) > 4000:
            parts = []
            current_part = ""
            for paragraph in doc_text.split('\n\n'):
                if len(current_part + paragraph) < 4000:
                    current_part += paragraph + '\n\n'
                else:
                    parts.append(current_part)
                    current_part = paragraph + '\n\n'
            if current_part:
                parts.append(current_part)
        else:
            parts = [doc_text]
        
        # Отправляем части последовательно
        for i, part in enumerate(parts):
            if i == 0:
                await callback.message.answer(part)
            else:
                await callback.message.answer(part)
        
        await callback.answer("✅ Документ загружен")
    else:
        await callback.answer("❌ Документ не найден")

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
    wait_text = {
        'ru': "🎨 <b>Генерация изображения...</b>",
        'en': "🎨 <b>Generating image...</b>"
    }
    
    msg = await message.answer(wait_text[lang])
    active_generations[message.from_user.id] = True
    
    try:
        # Используем GPT-5 Image Mini для генерации
        result = await routerai_service.generate_image(prompt, model_id=Config.IMAGE_GENERATION_MODEL)
        
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
        await msg.edit_text("❌ <b>Ошибка при генерации изображения</b>")
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
        
        # Отправляем юридическое уведомление
        legal_notice = """
⚠️ <b>Важная информация</b>

Используя бота, вы соглашаетесь с:
• Политикой конфиденциальности
• Пользовательским соглашением  
• Условиями оплаты
• Договором подписки

Полные версии документов доступны в разделе "👤 Мой профиль" → "📄 Юридические документы"
        """
        await message.answer(legal_notice)
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

📊 <b>Used today:</b>
Messages: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
Images generated: {user['images_generated_today']}/{plan['image_generate'] if plan else 0}
Images sent: {user['images_sent_today']}/{plan['image_send'] if plan else 0}
Videos sent: {user['videos_sent_today']}/{plan['video_send'] if plan else 0}

🤖 Current model: {user['current_model']}"""
    }
    await message.answer(profile_text[lang], reply_markup=get_profile_keyboard(lang))

# ... (остальные обработчики остаются такими же как в предыдущей версии)

# ========== ВЕБХУК YOOKASSA ==========
async def yookassa_webhook(request):
    try:
        body = await request.text()
        data = json.loads(body)
        logger.info(f"YooKassa webhook received: {data.get('event')}")
        
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
                    logger.info(f"Payment {yookassa_id} confirmed for user {user_id}")
        
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
    
    # Запускаем сервер для вебхуков
    runner = await start_webhook_server()
    
    logger.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
