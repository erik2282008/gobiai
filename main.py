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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
from aiogram.client.default import DefaultBotProperties

from config import Config
from database import db
from services.yookassa import yookassa_service
from services.routerai import routerai_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Исправленная инициализация бота
bot = Bot(
    token=Config.BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode='HTML')
)
dp = Dispatcher()

active_generations = {}
user_conversations = {}

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="profile", description="Ваш профиль"),
        BotCommand(command="models", description="Выбрать модель AI"),
        BotCommand(command="buy", description="Купить подписку/API"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="stop", description="Остановить генерацию")
    ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())

def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
    ])

def get_main_keyboard(lang='ru'):
    text = {'ru': ['🧠 Модели', '👤 Профиль', '💳 Купить', '🆘 Помощь'], 'en': ['🧠 Models', '👤 Profile', '💳 Buy', '🆘 Help']}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text[lang][0], callback_data="models"),
         InlineKeyboardButton(text=text[lang][1], callback_data="profile")],
        [InlineKeyboardButton(text=text[lang][2], callback_data="buy"),
         InlineKeyboardButton(text=text[lang][3], callback_data="help")]
    ])

def get_models_keyboard(user_subscription, lang='ru'):
    keyboard = []
    available_categories = Config.SUBSCRIPTION_ACCESS.get(user_subscription, ['free'])
    for category in available_categories:
        if category in Config.AI_MODELS:
            for model in Config.AI_MODELS[category]:
                name = model['name'] if lang == 'ru' else model['name_en']
                keyboard.append([InlineKeyboardButton(text=name, callback_data=f"model_{model['id']}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_buy_keyboard(lang='ru'):
    text = {'ru': ['🔄 Купить подписку', '🔑 Купить API-ключ', '🔙 Назад'], 'en': ['🔄 Buy subscription', '🔑 Buy API key', '🔙 Back']}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text[lang][0], callback_data="buy_subscription")],
        [InlineKeyboardButton(text=text[lang][1], callback_data="buy_api")],
        [InlineKeyboardButton(text=text[lang][2], callback_data="main_menu")]
    ])

def get_subscription_keyboard(lang='ru'):
    keyboard = []
    for plan in Config.SUBSCRIPTION_PLANS[1:]:
        name = plan['name'] if lang == 'ru' else plan['name_en']
        keyboard.append([InlineKeyboardButton(text=f"{name} - {plan['price']} руб", callback_data=f"sub_{plan['id']}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy")])
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
            keyboard.append([InlineKeyboardButton(text=f"{name} - {price} руб", callback_data=f"api_{model_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_stop_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏹️ Остановить", callback_data="stop_generation")]])

def get_back_keyboard(target='main_menu'):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=target)]])

def get_payment_check_keyboard(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{payment_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="buy")]
    ])

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
                    'ru': "✅ <b>Платеж подтвержден!</b>\n\n🎉 Подписка активирована на 30 дней.",
                    'en': "✅ <b>Payment confirmed!</b>\n\n🎉 Subscription activated for 30 days."
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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("👋 <b>Добро пожаловать!</b>\n\nВыберите язык:", reply_markup=get_lang_keyboard())
    else:
        lang = user['language']
        await message.answer("👋 <b>С возвращением!</b>", reply_markup=get_main_keyboard(lang))

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

📊 Подписка: {plan['name'] if plan else 'Free'}
📅 Дней до конца подписки: {days_left}
🎁 Дней до конца триала: {trial_days_left}
📈 Использовано сегодня: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
🤖 Текущая модель: {user['current_model']}""",
        'en': f"""👤 <b>Your Profile</b>

📊 Subscription: {plan['name_en'] if plan else 'Free'}
📅 Days until subscription end: {days_left}
🎁 Days until trial end: {trial_days_left}
📈 Used today: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
🤖 Current model: {user['current_model']}"""
    }
    await message.answer(profile_text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("models"))
async def cmd_models(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    await message.answer("🧠 <b>Выберите AI-модель:</b>", reply_markup=get_models_keyboard(user['subscription'], lang))

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    lang = user['language']
    await message.answer("💳 <b>Выберите тип покупки:</b>", reply_markup=get_buy_keyboard(lang))

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user = db.get_user(message.from_user.id)
    lang = user['language'] if user else 'ru'
    
    help_text = {
        'ru': f"""🆘 <b>Помощь</b>

Для связи с поддержкой: {Config.SUPPORT_USERNAME}

<b>Команды:</b>
/start - начать работу с ботом
/profile - посмотреть ваш профиль  
/models - выбрать AI-модель
/buy - купить подписку или API-ключ
/stop - остановить генерацию""",
        'en': f"""🆘 <b>Help</b>

Contact support: {Config.SUPPORT_USERNAME}

<b>Commands:</b>
/start - start working with bot
/profile - view your profile
/models - choose AI model
/buy - buy subscription or API key
/stop - stop generation"""
    }
    await message.answer(help_text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    if message.from_user.id in active_generations:
        active_generations[message.from_user.id] = False
        await message.answer("⏹️ Генерация остановлена")

@dp.callback_query(F.data == "lang_ru")
@dp.callback_query(F.data == "lang_en")
async def set_language(callback: types.CallbackQuery):
    lang = "ru" if callback.data == "lang_ru" else "en"
    db.create_user(callback.from_user.id, callback.from_user.username, lang)
    
    welcome_text = {
        'ru': f"🎉 <b>Отлично! Язык установлен на Русский.</b>\n\n✨ <b>Вам активирован бесплатный пробный период на {Config.TRIAL_MONTHS} месяца!</b>",
        'en': f"🎉 <b>Great! Language set to English.</b>\n\n✨ <b>You have activated a free trial for {Config.TRIAL_MONTHS} months!</b>"
    }
    
    await callback.message.edit_text(welcome_text[lang], reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    lang = user['language']
    await callback.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "models")
async def show_models(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    lang = user['language']
    await callback.message.edit_text("🧠 <b>Выберите AI-модель:</b>", reply_markup=get_models_keyboard(user['subscription'], lang))
    await callback.answer()

@dp.callback_query(F.data.startswith("model_"))
async def select_model(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    model_id = callback.data.replace("model_", "")
    db.update_user_model(user['user_id'], model_id)
    
    lang = user['language']
    await callback.message.edit_text("✅ <b>Модель выбрана!</b>\n\nТеперь отправляйте сообщения для генерации.", reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def show_buy_options(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    lang = user['language']
    await callback.message.edit_text("💳 <b>Выберите тип покупки:</b>", reply_markup=get_buy_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "buy_subscription")
async def show_subscriptions(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    lang = user['language']
    await callback.message.edit_text("📊 <b>Выберите подписку:</b>", reply_markup=get_subscription_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "buy_api")
async def show_api_prices(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    lang = user['language']
    await callback.message.edit_text("🔑 <b>Выберите модель для API-ключа:</b>", reply_markup=get_api_key_keyboard(lang))
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
🎯 Лимит: {plan['daily_limit']} сообщений/день

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил" для проверки статуса.""",
            'en': f"""💳 <b>Payment for {plan['name_en']}</b>

💰 Amount: {plan['price']} RUB
📅 Duration: 30 days
🎯 Limit: {plan['daily_limit']} messages/day

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ After payment, click "✅ I paid" to check status."""
        }
        await callback.message.edit_text(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже.",
            'en': "❌ <b>Payment creation error</b>\n\nTry again later."
        }
        await callback.message.edit_text(error_text[user['language']], reply_markup=get_back_keyboard('buy_subscription'))
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
            'ru': f"""🔑 <b>Покупка API-ключа</b>

🤖 Модель: {model_name}
💰 Стоимость: {price} руб (за 750K токенов)

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил"

📩 После подтверждения обратитесь к {Config.SUPPORT_USERNAME} для получения ключа.""",
            'en': f"""🔑 <b>API Key Purchase</b>

🤖 Model: {model_name}
💰 Price: {price} RUB (per 750K tokens)

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ After payment, click "✅ I paid"

📩 After confirmation, contact {Config.SUPPORT_USERNAME} for your key."""
        }
        await callback.message.edit_text(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже.",
            'en': "❌ <b>Payment creation error</b>\n\nTry again later."
        }
        await callback.message.edit_text(error_text[user['language']], reply_markup=get_back_keyboard('buy_api'))
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
        await callback.message.edit_text("❌ <b>Платеж еще не подтвержден</b>\n\nПожалуйста, подождите несколько минут и попробуйте снова.", reply_markup=get_payment_check_keyboard(payment_id))
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    await cmd_profile(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "help")
async def show_help(callback: types.CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "stop_generation")
async def stop_generation(callback: types.CallbackQuery):
    if callback.from_user.id in active_generations:
        active_generations[callback.from_user.id] = False
        user = db.get_user(callback.from_user.id)
        lang = user['language'] if user else 'ru'
        await callback.message.edit_text("⏹️ Генерация остановлена", reply_markup=get_main_keyboard(lang))
    await callback.answer()

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
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{result['response']}", reply_markup=get_main_keyboard(lang))
        elif not result['success']:
            await msg.edit_text(f"❌ <b>Ошибка:</b>\n\n{result['error']}", reply_markup=get_main_keyboard(lang))
            
    except Exception as e:
        await msg.edit_text("❌ <b>Ошибка обработки изображения</b>", reply_markup=get_main_keyboard(lang))
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
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{result['response']}", reply_markup=get_main_keyboard(lang))
        elif not result['success']:
            await msg.edit_text(f"❌ <b>Ошибка:</b>\n\n{result['error']}", reply_markup=get_main_keyboard(lang))
            
    except Exception as e:
        await msg.edit_text("❌ <b>Ошибка соединения</b>\n\nПопробуйте позже.", reply_markup=get_main_keyboard(lang))
    finally:
        active_generations.pop(user_id, None)

async def yookassa_webhook(request):
    try:
        body = await request.text()
        data = json.loads(body)
        logger.info(f"YooKassa webhook received: {data}")
        
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
                            'en': "✅ <b>Payment automatically confirmed!</b>\n\n🎉 Your subscription has been activated for 30 days!"
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
    logger.info("Setting up bot commands...")
    await set_bot_commands()
    
    logger.info("Starting webhook server...")
    runner = await start_webhook_server()
    
    logger.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
