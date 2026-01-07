import asyncio
import logging
import uuid
import json
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

from config import Config
from database import db
from services.yookassa import yookassa_service
from services.routerai import routerai_service

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

# Хранилище активных генераций
active_generations = {}
user_conversations = {}

# ========== КЛАВИАТУРЫ ==========
def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
    ])

def get_main_keyboard(lang='ru'):
    text = {
        'ru': ['🧠 Модели', '👤 Профиль', '💳 Купить', '🆘 Помощь'],
        'en': ['🧠 Models', '👤 Profile', '💳 Buy', '🆘 Help']
    }
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад" if lang == 'ru' else "🔙 Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_buy_keyboard(lang='ru'):
    text = {
        'ru': ['🔄 Купить подписку', '🔑 Купить API-ключ', '🔙 Назад'],
        'en': ['🔄 Buy subscription', '🔑 Buy API key', '🔙 Back']
    }
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
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад" if lang == 'ru' else "🔙 Back", callback_data="buy")])
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
            if model:
                break
        
        if model:
            name = model['name'] if lang == 'ru' else model['name_en']
            keyboard.append([InlineKeyboardButton(text=f"{name} - {price} руб", callback_data=f"api_{model_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад" if lang == 'ru' else "🔙 Back", callback_data="buy")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_stop_keyboard(lang='ru'):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⏹️ Остановить" if lang == 'ru' else "⏹️ Stop", callback_data="stop_generation")
    ]])

def get_back_keyboard(lang='ru', target='main_menu'):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Назад" if lang == 'ru' else "🔙 Back", callback_data=target)
    ]])

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("👋 <b>Добро пожаловать!</b>\n\nВыберите язык / Choose language:", reply_markup=get_lang_keyboard())
    else:
        lang = user['language']
        welcome_text = {
            'ru': "👋 <b>С возвращением!</b>\n\nИспользуйте кнопки ниже для работы с AI-моделями.",
            'en': "👋 <b>Welcome back!</b>\n\nUse the buttons below to work with AI models."
        }
        await message.answer(welcome_text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите /start")
        return
    
    lang = user['language']
    plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
    
    from datetime import datetime
    days_left = 0
    if user['subscription_end']:
        end_date = datetime.strptime(user['subscription_end'], '%Y-%m-%d')
        days_left = (end_date - datetime.now()).days
    
    trial_days_left = 0
    if user['trial_end']:
        trial_end = datetime.strptime(user['trial_end'], '%Y-%m-%d')
        trial_days_left = (trial_end - datetime.now()).days
    
    profile_text = {
        'ru': f"""👤 <b>Ваш профиль</b>

📊 Подписка: {plan['name'] if plan else 'Free'}
📅 Дней до конца подписки: {max(days_left, 0)}
🎁 Дней до конца триала: {max(trial_days_left, 0)}
📈 Использовано сегодня: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
🤖 Текущая модель: {user['current_model']}""",
        'en': f"""👤 <b>Your Profile</b>

📊 Subscription: {plan['name_en'] if plan else 'Free'}
📅 Days until subscription end: {max(days_left, 0)}
🎁 Days until trial end: {max(trial_days_left, 0)}
📈 Used today: {user['daily_used']}/{plan['daily_limit'] if plan else 100}
🤖 Current model: {user['current_model']}"""
    }
    
    await message.answer(profile_text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("models"))
async def cmd_models(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите /start")
        return
    
    lang = user['language']
    text = {
        'ru': "🧠 <b>Выберите AI-модель:</b>",
        'en': "🧠 <b>Choose AI model:</b>"
    }
    await message.answer(text[lang], reply_markup=get_models_keyboard(user['subscription'], lang))

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите /start")
        return
    
    lang = user['language']
    text = {
        'ru': "💳 <b>Выберите тип покупки:</b>",
        'en': "💳 <b>Choose purchase type:</b>"
    }
    await message.answer(text[lang], reply_markup=get_buy_keyboard(lang))

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user = db.get_user(message.from_user.id)
    lang = user['language'] if user else 'ru'
    
    text = {
        'ru': f"""🆘 <b>Помощь</b>

Для связи с поддержкой: {Config.SUPPORT_USERNAME}

<b>Команды:</b>
/start - начать работу
/profile - ваш профиль  
/models - выбрать модель
/buy - покупка подписок и API-ключей
/stop - остановить генерацию""",
        'en': f"""🆘 <b>Help</b>

Contact support: {Config.SUPPORT_USERNAME}

<b>Commands:</b>
/start - start working
/profile - your profile
/models - choose model
/buy - buy subscriptions and API keys
/stop - stop generation"""
    }
    
    await message.answer(text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    user_id = message.from_user.id
    if user_id in active_generations:
        active_generations[user_id] = False
        await message.answer("⏹️ Генерация остановлена")

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query(F.data == "lang_ru")
@dp.callback_query(F.data == "lang_en")
async def set_language(callback: types.CallbackQuery):
    lang = "ru" if callback.data == "lang_ru" else "en"
    user_id = callback.from_user.id
    
    db.create_user(user_id, callback.from_user.username, lang)
    
    welcome_text = {
        'ru': f"🎉 <b>Отлично!</b> Язык установлен на Русский.\n\n✨ <b>Вам активирован бесплатный пробный период на {Config.TRIAL_MONTHS} месяца!</b>\n\nИспользуйте кнопки ниже для работы с AI-моделями.",
        'en': f"🎉 <b>Great!</b> Language set to English.\n\n✨ <b>You have activated a free trial for {Config.TRIAL_MONTHS} months!</b>\n\nUse the buttons below to work with AI models."
    }
    
    await callback.message.edit_text(welcome_text[lang], reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
        return
    
    lang = user['language']
    text = {
        'ru': "🏠 <b>Главное меню</b>",
        'en': "🏠 <b>Main menu</b>"
    }
    await callback.message.edit_text(text[lang], reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "models")
async def show_models(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
        return
    
    lang = user['language']
    text = {
        'ru': "🧠 <b>Выберите AI-модель:</b>",
        'en': "🧠 <b>Choose AI model:</b>"
    }
    await callback.message.edit_text(text[lang], reply_markup=get_models_keyboard(user['subscription'], lang))
    await callback.answer()

@dp.callback_query(F.data.startswith("model_"))
async def select_model(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
        return
    
    model_id = callback.data.replace("model_", "")
    db.update_user_model(user['user_id'], model_id)
    
    lang = user['language']
    text = {
        'ru': "✅ <b>Модель выбрана!</b>\n\nТеперь отправляйте сообщения для генерации.",
        'en': "✅ <b>Model selected!</b>\n\nNow send messages for generation."
    }
    await callback.message.edit_text(text[lang], reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def show_buy_options(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
        return
    
    lang = user['language']
    text = {
        'ru': "💳 <b>Выберите тип покупки:</b>",
        'en': "💳 <b>Choose purchase type:</b>"
    }
    await callback.message.edit_text(text[lang], reply_markup=get_buy_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "buy_subscription")
async def show_subscriptions(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
        return
    
    lang = user['language']
    await callback.message.edit_text(
        "📊 <b>Выберите подписку:</b>" if lang == 'ru' else "📊 <b>Choose subscription:</b>",
        reply_markup=get_subscription_keyboard(lang)
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_api")
async def show_api_prices(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
        return
    
    lang = user['language']
    await callback.message.edit_text(
        "🔑 <b>Выберите модель для API-ключа:</b>" if lang == 'ru' else "🔑 <b>Choose model for API key:</b>",
        reply_markup=get_api_key_keyboard(lang)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("sub_"))
async def process_subscription_selection(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
        return
    
    plan_id = callback.data.replace("sub_", "")
    plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == plan_id), None)
    
    if not plan:
        await callback.answer("❌ План не найден")
        return
    
    lang = user['language']
    
    # Создаем платеж
    payment_id = str(uuid.uuid4())
    db.create_payment(payment_id, user['user_id'], 'subscription', plan_id, None, plan['price'])
    
    result = await yookassa_service.create_subscription_payment(
        user['user_id'], plan_id, plan['name'], plan['price'], lang
    )
    
    if result['success']:
        db.update_payment_status(payment_id, 'pending', result['yookassa_id'])
        
        payment_text = {
            'ru': f"""💳 <b>Оплата подписки {plan['name']}</b>

💰 Сумма: {plan['price']} руб
📅 Срок: 30 дней
🎯 Лимит: {plan['daily_limit']} сообщений/день

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты подписка активируется автоматически.""",
            'en': f"""💳 <b>Payment for {plan['name_en']}</b>

💰 Amount: {plan['price']} RUB
📅 Duration: 30 days
🎯 Limit: {plan['daily_limit']} messages/day

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ Subscription will be activated automatically after payment."""
        }
        
        await callback.message.edit_text(payment_text[lang], reply_markup=get_back_keyboard(lang, 'buy_subscription'))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже или обратитесь в поддержку.",
            'en': "❌ <b>Payment creation error</b>\n\nTry again later or contact support."
        }
        await callback.message.edit_text(error_text[lang], reply_markup=get_back_keyboard(lang, 'buy_subscription'))
    
    await callback.answer()

@dp.callback_query(F.data.startswith("api_"))
async def process_api_selection(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала запустите /start")
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
        if model:
            break
    
    if not model:
        await callback.answer("❌ Модель не найдена")
        return
    
    lang = user['language']
    model_name = model['name'] if lang == 'ru' else model['name_en']
    
    # Создаем платеж
    payment_id = str(uuid.uuid4())
    db.create_payment(payment_id, user['user_id'], 'api_key', None, model_id, price)
    
    result = await yookassa_service.create_api_key_payment(
        user['user_id'], model_id, model_name, price, lang
    )
    
    if result['success']:
        db.update_payment_status(payment_id, 'pending', result['yookassa_id'])
        
        payment_text = {
            'ru': f"""🔑 <b>Покупка API-ключа</b>

🤖 Модель: {model_name}
💰 Стоимость: {price} руб (за 750K токенов)
📦 После оплаты ключ выдает администратор

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты обратитесь к {Config.SUPPORT_USERNAME} для получения ключа.""",
            'en': f"""🔑 <b>API Key Purchase</b>

🤖 Model: {model_name}
💰 Price: {price} RUB (per 750K tokens)
📦 Key will be provided by admin after payment

👉 <a href="{result['confirmation_url']}">Proceed to payment</a>

⚠️ After payment, contact {Config.SUPPORT_USERNAME} to receive your key."""
        }
        
        await callback.message.edit_text(payment_text[lang], reply_markup=get_back_keyboard(lang, 'buy_api'))
    else:
        error_text = {
            'ru': "❌ <b>Ошибка при создании платежа</b>\n\nПопробуйте позже или обратитесь в поддержку.",
            'en': "❌ <b>Payment creation error</b>\n\nTry again later or contact support."
        }
        await callback.message.edit_text(error_text[lang], reply_markup=get_back_keyboard(lang, 'buy_api'))
    
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
    user_id = callback.from_user.id
    if user_id in active_generations:
        active_generations[user_id] = False
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        await callback.message.edit_text("⏹️ Генерация остановлена", reply_markup=get_main_keyboard(lang))
    await callback.answer()

# ========== ОБРАБОТКА СООБЩЕНИЙ ДЛЯ AI ==========
@dp.message(F.text)
async def handle_message(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала запустите /start")
        return
    
    # Проверяем лимиты
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use:
        lang = user['language']
        error_text = {
            'ru': f"❌ <b>Лимит исчерпан</b>\n\n{error_msg}",
            'en': f"❌ <b>Limit exceeded</b>\n\n{error_msg}"
        }
        await message.answer(error_text[lang])
        return
    
    # Увеличиваем счетчик использования
    db.increment_daily_usage(user['user_id'])
    
    # Подготавливаем историю диалога
    user_id = message.from_user.id
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    # Добавляем новое сообщение в историю (ограничиваем историю последними 10 сообщениями)
    user_conversations[user_id].append({"role": "user", "content": message.text})
    if len(user_conversations[user_id]) > 10:
        user_conversations[user_id] = user_conversations[user_id][-10:]
    
    lang = user['language']
    wait_text = {
        'ru': "⏳ <b>Генерация началась...</b>",
        'en': "⏳ <b>Generation started...</b>"
    }
    
    msg = await message.answer(wait_text[lang], reply_markup=get_stop_keyboard(lang))
    active_generations[user_id] = True
    
    try:
        # Реальный запрос к RouterAI API
        result = await routerai_service.send_message(
            user['current_model'], 
            message.text,
            user_conversations[user_id][:-1]  # Передаем историю без текущего сообщения
        )
        
        if result['success'] and active_generations.get(user_id):
            # Добавляем ответ AI в историю
            user_conversations[user_id].append({"role": "assistant", "content": result['response']})
            
            response_text = f"🤖 <b>Ответ AI:</b>\n\n{result['response']}"
            await msg.edit_text(response_text, reply_markup=get_main_keyboard(lang))
        
        elif not result['success'] and active_generations.get(user_id):
            error_text = {
                'ru': f"❌ <b>Ошибка AI</b>\n\n{result['error']}",
                'en': f"❌ <b>AI Error</b>\n\n{result['error']}"
            }
            await msg.edit_text(error_text[lang], reply_markup=get_main_keyboard(lang))
    
    except Exception as e:
        if active_generations.get(user_id):
            error_text = {
                'ru': "❌ <b>Ошибка соединения</b>\n\nПопробуйте позже.",
                'en': "❌ <b>Connection error</b>\n\nPlease try again later."
            }
            await msg.edit_text(error_text[lang], reply_markup=get_main_keyboard(lang))
    
    finally:
        active_generations.pop(user_id, None)

# ========== ЗАПУСК БОТА (POLLING РЕЖИМ) ==========
async def main():
    logger.info("Starting bot in polling mode...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
