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
from PIL import Image

from config import Config
from database import db
from services.yookassa import yookassa_service
from services.routerai import routerai_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=Config.BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode='HTML', timeout=60)
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
                    'ru': f"✅ <b>Платеж подтвержден!</b>\n\n🤖 Модель: {model_name}\n📩 Обратитесь к {Config.SUPPORT_USERNAME}",
                    'en': f"✅ <b>Payment confirmed!</b>\n\n🤖 Model: {model_name}\n📩 Contact {Config.SUPPORT_USERNAME}"
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
    if not user: return await message.answer("❌ Сначала /start")
    lang = user['language']
    plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
    days_left = (datetime.strptime(user['subscription_end'], '%Y-%m-%d') - datetime.now()).days if user['subscription_end'] else 0
    trial_days_left = (datetime.strptime(user['trial_end'], '%Y-%m-%d') - datetime.now()).days if user['trial_end'] else 0
    profile_text = {
        'ru': f"👤 <b>Профиль</b>\n\n📊 Подписка: {plan['name'] if plan else 'Free'}\n📅 Дней: {max(days_left, 0)}\n🎁 Триал: {max(trial_days_left, 0)}\n📈 Использовано: {user['daily_used']}/{plan['daily_limit'] if plan else 100}",
        'en': f"👤 <b>Profile</b>\n\n📊 Subscription: {plan['name_en'] if plan else 'Free'}\n📅 Days: {max(days_left, 0)}\n🎁 Trial: {max(trial_days_left, 0)}\n📈 Used: {user['daily_used']}/{plan['daily_limit'] if plan else 100}"
    }
    await message.answer(profile_text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("models"))
async def cmd_models(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: return await message.answer("❌ Сначала /start")
    lang = user['language']
    await message.answer("🧠 <b>Выберите модель:</b>", reply_markup=get_models_keyboard(user['subscription'], lang))

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: return await message.answer("❌ Сначала /start")
    await message.answer("💳 <b>Выберите тип покупки:</b>", reply_markup=get_buy_keyboard(user['language']))

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    user = db.get_user(message.from_user.id)
    lang = user['language'] if user else 'ru'
    help_text = {
        'ru': f"🆘 <b>Помощь</b>\n\nПоддержка: {Config.SUPPORT_USERNAME}\n\nКоманды:\n/start - начать\n/profile - профиль\n/models - модели\n/buy - покупка\n/stop - остановить",
        'en': f"🆘 <b>Help</b>\n\nSupport: {Config.SUPPORT_USERNAME}\n\nCommands:\n/start - start\n/profile - profile\n/models - models\n/buy - buy\n/stop - stop"
    }
    await message.answer(help_text[lang], reply_markup=get_main_keyboard(lang))

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    if message.from_user.id in active_generations:
        active_generations[message.from_user.id] = False
        await message.answer("⏹️ Остановлено")

@dp.callback_query(F.data == "lang_ru")
@dp.callback_query(F.data == "lang_en")
async def set_language(callback: types.CallbackQuery):
    lang = "ru" if callback.data == "lang_ru" else "en"
    db.create_user(callback.from_user.id, callback.from_user.username, lang)
    welcome_text = {
        'ru': f"🎉 <b>Язык: Русский</b>\n\n✨ Триал на {Config.TRIAL_MONTHS} месяца активирован!",
        'en': f"🎉 <b>Language: English</b>\n\n✨ {Config.TRIAL_MONTHS} months trial activated!"
    }
    await callback.message.edit_text(welcome_text[lang], reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    await callback.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=get_main_keyboard(user['language']))
    await callback.answer()

@dp.callback_query(F.data == "models")
async def show_models(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    await callback.message.edit_text("🧠 <b>Выберите модель:</b>", reply_markup=get_models_keyboard(user['subscription'], user['language']))
    await callback.answer()

@dp.callback_query(F.data.startswith("model_"))
async def select_model(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    model_id = callback.data.replace("model_", "")
    db.update_user_model(user['user_id'], model_id)
    await callback.message.edit_text("✅ <b>Модель выбрана!</b>", reply_markup=get_main_keyboard(user['language']))
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def show_buy_options(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    await callback.message.edit_text("💳 <b>Выберите тип:</b>", reply_markup=get_buy_keyboard(user['language']))
    await callback.answer()

@dp.callback_query(F.data == "buy_subscription")
async def show_subscriptions(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    await callback.message.edit_text("📊 <b>Выберите подписку:</b>", reply_markup=get_subscription_keyboard(user['language']))
    await callback.answer()

@dp.callback_query(F.data == "buy_api")
async def show_api_prices(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    await callback.message.edit_text("🔑 <b>Выберите модель:</b>", reply_markup=get_api_key_keyboard(user['language']))
    await callback.answer()

@dp.callback_query(F.data.startswith("sub_"))
async def process_subscription(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    plan_id = callback.data.replace("sub_", "")
    plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == plan_id), None)
    if not plan: return await callback.answer("❌ План не найден")
    
    payment_id = str(uuid.uuid4())
    db.create_payment(payment_id, user['user_id'], 'subscription', plan_id, None, plan['price'])
    result = await yookassa_service.create_subscription_payment(user['user_id'], plan_id, plan['name'], plan['price'], user['language'])
    
    if result['success']:
        db.update_payment_status(payment_id, 'pending', result['yookassa_id'])
        payment_text = {
            'ru': f"💳 <b>Оплата {plan['name']}</b>\n\n💰 Сумма: {plan['price']} руб\n👉 <a href=\"{result['confirmation_url']}\">Оплатить</a>\n\n⚠️ После оплаты нажмите '✅ Я оплатил'",
            'en': f"💳 <b>Payment {plan['name_en']}</b>\n\n💰 Amount: {plan['price']} RUB\n👉 <a href=\"{result['confirmation_url']}\">Pay</a>\n\n⚠️ After payment click '✅ I paid'"
        }
        await callback.message.edit_text(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        await callback.message.edit_text("❌ <b>Ошибка оплаты</b>", reply_markup=get_back_keyboard('buy_subscription'))
    await callback.answer()

@dp.callback_query(F.data.startswith("api_"))
async def process_api(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Сначала /start")
    model_id = callback.data.replace("api_", "")
    price = Config.API_KEY_PRICES.get(model_id)
    if not price: return await callback.answer("❌ Модель не найдена")
    
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
            'ru': f"🔑 <b>API-ключ {model_name}</b>\n\n💰 Сумма: {price} руб\n👉 <a href=\"{result['confirmation_url']}\">Оплатить</a>\n\n📩 После оплаты обратитесь к {Config.SUPPORT_USERNAME}",
            'en': f"🔑 <b>API key {model_name}</b>\n\n💰 Amount: {price} RUB\n👉 <a href=\"{result['confirmation_url']}\">Pay</a>\n\n📩 After payment contact {Config.SUPPORT_USERNAME}"
        }
        await callback.message.edit_text(payment_text[user['language']], reply_markup=get_payment_check_keyboard(payment_id))
    else:
        await callback.message.edit_text("❌ <b>Ошибка оплаты</b>", reply_markup=get_back_keyboard('buy_api'))
    await callback.answer()

@dp.callback_query(F.data.startswith("paid_"))
async def check_payment(callback: types.CallbackQuery):
    payment_id = callback.data.replace("paid_", "")
    payment = db.get_payment(payment_id)
    if not payment: return await callback.answer("❌ Платеж не найден")
    
    user = db.get_user(callback.from_user.id)
    lang = user['language'] if user else 'ru'
    await callback.message.edit_text("⏳ <b>Проверяем платеж...</b>")
    
    result = await check_payment_status(payment_id, payment['yookassa_payment_id'], payment['user_id'])
    if not result:
        await callback.message.edit_text("❌ <b>Платеж не подтвержден</b>\n\nПопробуйте позже", reply_markup=get_payment_check_keyboard(payment_id))
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
        await callback.message.edit_text("⏹️ Остановлено", reply_markup=get_main_keyboard(lang))
    await callback.answer()

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: return await message.answer("❌ Сначала /start")
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: return await message.answer(f"❌ Лимит: {error_msg}")
    db.increment_daily_usage(user['user_id'])
    
    current_model_supports_images = False
    for category_models in Config.AI_MODELS.values():
        for model in category_models:
            if model['id'] == user['current_model']:
                current_model_supports_images = model['supports_images']
                break
    if not current_model_supports_images:
        return await message.answer("❌ Модель не поддерживает изображения")
    
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = await bot.download_file(file.file_path)
    image_data = base64.b64encode(file_path.read()).decode('utf-8')
    
    lang = user['language']
    msg = await message.answer("⏳ <b>Обработка...</b>", reply_markup=get_stop_keyboard())
    active_generations[message.from_user.id] = True
    
    try:
        result = await routerai_service.send_message(user['current_model'], message.caption or "Опиши изображение", extra_data={"image": image_data})
        if result['success'] and active_generations.get(message.from_user.id):
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{result['response']}", reply_markup=get_main_keyboard(lang))
        elif not result['success']:
            await msg.edit_text(f"❌ <b>Ошибка:</b>\n\n{result['error']}", reply_markup=get_main_keyboard(lang))
    except Exception as e:
        await msg.edit_text("❌ <b>Ошибка обработки</b>", reply_markup=get_main_keyboard(lang))
    finally:
        active_generations.pop(message.from_user.id, None)

@dp.message(F.text)
async def handle_message(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: return await message.answer("❌ Сначала /start")
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: return await message.answer(f"❌ Лимит: {error_msg}")
    db.increment_daily_usage(user['user_id'])
    
    user_id = message.from_user.id
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    user_conversations[user_id].append({"role": "user", "content": message.text})
    if len(user_conversations[user_id]) > 10:
        user_conversations[user_id] = user_conversations[user_id][-10:]
    
    lang = user['language']
    msg = await message.answer("⏳ <b>Генерация...</b>", reply_markup=get_stop_keyboard())
    active_generations[user_id] = True
    
    try:
        result = await routerai_service.send_message(user['current_model'], message.text, user_conversations[user_id][:-1])
        if result['success'] and active_generations.get(user_id):
            user_conversations[user_id].append({"role": "assistant", "content": result['response']})
            await msg.edit_text(f"🤖 <b>Ответ:</b>\n\n{result['response']}", reply_markup=get_main_keyboard(lang))
        elif not result['success']:
            await msg.edit_text(f"❌ <b>Ошибка:</b>\n\n{result['error']}", reply_markup=get_main_keyboard(lang))
    except Exception:
        await msg.edit_text("❌ <b>Ошибка соединения</b>", reply_markup=get_main_keyboard(lang))
    finally:
        active_generations.pop(user_id, None)

async def yookassa_webhook(request):
    try:
        body = await request.text()
        data = json.loads(body)
        logger.info(f"YooKassa webhook: {data}")
        
        if data.get('event') == 'payment.succeeded':
            yookassa_id = data['object']['id']
            metadata = data['object'].get('metadata', {})
            user_id = metadata.get('user_id')
            
            if user_id:
                payment = db.get_payment_by_yookassa_id(yookassa_id)
                if payment and payment['status'] != 'succeeded':
                    db.update_payment_status(payment['payment_id'], 'succeeded', yookassa_id)
                    
                    if payment['type'] == 'subscription':
                        db.update_user_subscription(user_id, payment['plan_id'])
                        success_text = "✅ <b>Платеж подтвержден!</b>\n\n🎉 Подписка активирована!"
                    else:
                        success_text = f"✅ <b>Платеж подтвержден!</b>\n\n📩 Обратитесь к {Config.SUPPORT_USERNAME}"
                    
                    await bot.send_message(user_id, success_text)
        
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
    await set_bot_commands()
    runner = await start_webhook_server()
    logger.info("Starting bot...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
