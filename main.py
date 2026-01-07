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

# ========== ЮРИДИЧЕСКИЕ ДОКУМЕНТЫ ==========
LEGAL_DOCUMENTS = {
    'privacy_policy': """
🔒 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>

<b>1. АДМИНИСТРАТОР И ВЛАДЕЛЕЦ</b>
• Владелец бота: Симикян Эрик Самвелович
• Контакты: Telegram @smknnnn
• Юридический адрес: Российская Федерация

<b>2. ОБРАБАТЫВАЕМЫЕ ДАННЫЕ</b>
• Идентификатор пользователя Telegram (User ID)
• Имя пользователя (username)
• Статистика использования сервиса
• История сообщений (в целях предоставления услуг)
• Данные платежей (через ЮKassa)

<b>3. ЦЕЛИ ОБРАБОТКИ ДАННЫХ</b>
• Предоставление услуг AI-ассистента
• Обработка платежей и подписок
• Улучшение качества сервиса
• Соблюдение законодательства РФ

<b>4. ХРАНЕНИЕ И ЗАЩИТА ДАННЫХ</b>
• Данные хранятся в зашифрованном виде
• Срок хранения: 3 года с момента последней активности
• Доступ ограничен администрацией сервиса

<b>5. ПЕРЕДАЧА ДАННЫХ ТРЕТЬИМ ЛИЦАМ</b>
• Данные не передаются третьим лицам, за исключением:
  - Провайдеров платежных услуг (ЮKassa)
  - По требованию уполномоченных органов РФ

<b>6. ПРАВА ПОЛЬЗОВАТЕЛЯ</b>
Пользователь имеет право на:
• Доступ к своим персональным данным
• Исправление неточных данных
• Удаление данных (право на забвение)
• Отзыв согласия на обработку данных

<b>7. ПРАВОВОЕ ОСНОВАНИЕ</b>
• Федеральный закон №152-ФЗ «О персональных данных»
• Правила обработки персональных данных
• Пользовательское соглашение сервиса

<b>8. КОНТАКТЫ ДЛЯ ВОПРОСОВ</b>
По всем вопросам защиты персональных данных обращаться к @smknnnn
""",

    'user_agreement': """
📋 <b>ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Настоящее Соглашение регулирует отношения между Администрацией сервиса GobiAI Bot (далее — «Сервис») и Пользователем.
1.2. Используя Сервис, Пользователь соглашается с условиями настоящего Соглашения.
1.3. Владелец: Симикян Эрик Самвелович.

<b>2. ПРЕДМЕТ СОГЛАШЕНИЯ</b>
2.1. Сервис предоставляет доступ к AI-моделям через Telegram бота.
2.2. Услуги предоставляются «как есть» (as is).
2.3. Администрация оставляет за собой право изменять функционал Сервиса.

<b>3. РЕГИСТРАЦИЯ И АККАУНТ</b>
3.1. Для использования Сервиса требуется регистрация через Telegram.
3.2. Пользователь обязан предоставить достоверную информацию.
3.3. Аккаунт не подлежит передаче третьим лицам.

<b>4. ОГРАНИЧЕНИЯ ИСПОЛЬЗОВАНИЯ</b>
4.1. Запрещается использование Сервиса для:
   - Распространения незаконного контента
   - Нарушения авторских прав
   - Мошеннических действий
   - Спама и массовых рассылок
4.2. Администрация вправе заблокировать аккаунт при нарушении правил.

<b>5. ОТВЕТСТВЕННОСТЬ</b>
5.1. Администрация не несет ответственности за:
   - Точность и достоверность генерируемого контента
   - Убытки, вызванные использованием Сервиса
   - Технические сбои и перерывы в работе
5.2. Максимальная ответственность ограничена стоимостью подписки.

<b>6. АВТОРСКИЕ ПРАВА</b>
6.1. Пользователь сохраняет права на генерируемый контент.
6.2. Использование Сервиса не передает права на интеллектуальную собственность.

<b>7. ЗАКОНОДАТЕЛЬСТВО РФ</b>
7.1. Соглашение регулируется законодательством Российской Федерации.
7.2. Споры решаются в судебном порядке по месту нахождения Администрации.
""",

    'payment_terms': """
💳 <b>УСЛОВИЯ ОПЛАТЫ И ВОЗВРАТОВ</b>

<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>
1.1. Оплата услуг осуществляется через платежную систему ЮKassa (ООО «ЮMoney»).
1.2. Платежи обрабатываются в соответствии с законодательством РФ.

<b>2. СТОИМОСТЬ И ОПЛАТА</b>
2.1. Цены указаны в российских рублях (RUB).
2.2. Оплата производится единовременно за выбранный период.
2.3. НДС не облагается в соответствии с законодательством РФ.

<b>3. ПОДПИСКИ И АВТОПРОДЛЕНИЕ</b>
3.1. Подписки действуют в течение оплаченного периода.
3.2. Автопродление не предусмотрено.
3.3. Для продолжения использования требуется новая оплата.

<b>4. ВОЗВРАТЫ</b>
4.1. Возвраты осуществляются в соответствии с Законом «О защите прав потребителей».
4.2. Возврат возможен в течение 14 дней с момента оплаты.
4.3. Для возврата обратитесь к @smknnnn с указанием номера платежа.

<b>5. ТЕХНИЧЕСКИЕ ВОПРОСЫ</b>
5.1. При неудачной оплате проверьте:
   - Достаточность средств на счете
   - Корректность реквизитов карты
   - Ограничения банка-эмитента
5.2. Техподдержка: @smknnnn

<b>6. БЕЗОПАСНОСТЬ ПЛАТЕЖЕЙ</b>
6.1. Все платежи защищены стандартом PCI DSS.
6.2. Данные карт не хранятся на наших серверах.
6.3. Обработкой платежей занимается ЮKassa.
""",

    'subscription_terms': """
📄 <b>ДОГОВОР ПОДПИСКИ И УСЛОВИЯ ПРЕДОСТАВЛЕНИЯ УСЛУГ</b>

<b>1. ПРЕДМЕТ ДОГОВОРА</b>
1.1. Настоящий Договор регулирует предоставление услуг доступа к AI-моделям.
1.2. Услуги предоставляются на условиях выбранного тарифного плана.

<b>2. ТАРИФНЫЕ ПЛАНЫ</b>
2.1. Доступны следующие тарифы: Бесплатный, Lite, Lite+, VIP, VIP+, Quantum, Quantum Pro, Quantum Infinite.
2.2. Описание тарифов доступно в интерфейсе бота.
2.3. Администрация вправе изменять тарифы с уведомлением пользователей.

<b>3. ПОРЯДОК АКТИВАЦИИ</b>
3.1. Подписка активируется после успешной оплаты.
3.2. Срок действия: 30 календарных дней с момента активации.
3.3. Доступ к услугам предоставляется моментально после оплаты.

<b>4. ЛИМИТЫ И ОГРАНИЧЕНИЯ</b>
4.1. Использование Сервиса может быть ограничено в соответствии с выбранным тарифом.
4.2. Подробные условия использования указаны в описании каждого тарифа.
4.3. Администрация оставляет за собой право вводить разумные ограничения.

<b>5. ПРЕКРАЩЕНИЕ ДЕЙСТВИЯ</b>
5.1. Подписка автоматически прекращается по истечении оплаченного периода.
5.2. Досрочное прекращение возможно в случае нарушения Правил использования.

<b>6. КОНФИДЕНЦИАЛЬНОСТЬ</b>
6.1. Условия конфиденциальности регулируются отдельным документом.
6.2. Администрация обязуется не разглашать данные Пользователя.

<b>7. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ</b>
7.1. Договор действует с момента активации подписки.
7.2. Администрация вправе вносить изменения в Договор с уведомлением.
7.3. Споры решаются в соответствии с законодательством РФ.
"""
}

# ========== МЕНЮ-ПАНЕЛЬ (ПОД ЧАТОМ) ==========
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

# Убираем меню (если нужно скрыть)
def remove_keyboard():
    return ReplyKeyboardRemove()

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
        # Разбиваем длинный документ на части
        doc_text = LEGAL_DOCUMENTS[doc_type]
        if len(doc_text) > 4000:
            parts = [doc_text[i:i+4000] for i in range(0, len(doc_text), 4000)]
            for i, part in enumerate(parts):
                await callback.message.answer(part)
        else:
            await callback.message.answer(doc_text)
    
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
    wait_text = {
        'ru': "🎨 <b>Генерация изображения...</b>",
        'en': "🎨 <b>Generating image...</b>"
    }
    
    msg = await message.answer(wait_text[lang], reply_markup=get_stop_keyboard())
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
            welcome_text += f"\n\n🎁 +{Config.REFERRAL_REWARD_DAYS} дней VIP за регистрацию по реферальной ссылке!"
        
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
    await message.answer(profile_text[lang], reply_markup=get_profile_keyboard(lang))

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
👤 Мой профиль - информация о подписке и лимитах + юр.документы
💳 Купить подписку - выбор и покупка подписок
🔑 Купить API - приобретение API-ключей
🎨 Сгенерировать фото - генерация изображений по описанию
📤 Рефералка - реферальная система
🆘 Помощь - эта справка
⏹️ Остановить - прекращение текущей генерации

<b>Команды:</b>
/start - начать работу с ботом
/generate [описание] - сгенерировать изображение

<b>Поддержка:</b> {Config.SUPPORT_USERNAME}
<b>Юридические вопросы:</b> @smknnnn""",
        'en': f"""🆘 <b>GobiAI Help</b>

<b>Menu Panel:</b>
🧠 Choose model - view and select AI models
👤 My profile - subscription info, limits + legal docs
💳 Buy subscription - choose and buy subscriptions
🔑 Buy API - purchase API keys
🎨 Generate image - generate images from text
📤 Referral - referral system
🆘 Help - this help information
⏹️ Stop - stop current generation

<b>Commands:</b>
/start - start working with bot
/generate [description] - generate image

<b>Support:</b> {Config.SUPPORT_USERNAME}
<b>Legal questions:</b> @smknnnn"""
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
        await message.answer(stop_text['ru'])

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@dp.callback_query(F.data == "lang_ru")
@dp.callback_query(F.data == "lang_en")
async def set_language(callback: types.CallbackQuery):
    lang = "ru" if callback.data == "lang_ru" else "en"
    
    # Обновляем язык пользователя в базе
    cursor = db.conn.cursor()
    cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (lang, callback.from_user.id))
    db.conn.commit()
    
    welcome_text = {
        'ru': f"""🎉 <b>Язык изменен на Русский!</b>

✨ <b>Бесплатный триал на {Config.TRIAL_MONTHS} месяца активирован!</b>

Используйте панель меню внизу для навигации по боту.""",
        'en': f"""🎉 <b>Language changed to English!</b>

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
🖼 Генерация изображений: {plan['image_generate']}/день
📤 Отправка изображений: {plan['image_send']}/день
🎥 Отправка видео: {plan['video_send']}/день

👉 <a href="{result['confirmation_url']}">Перейти к оплате</a>

⚠️ После оплаты нажмите "✅ Я оплатил" для проверки статуса.""",
            'en': f"""💳 <b>Payment for {plan['name_en']}</b>

💰 Amount: {plan['price']} RUB
📅 Duration: 30 days
📊 Limit: {plan['daily_limit']} messages/day
🖼 Image generation: {plan['image_generate']}/day
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
    lang = user['language'] if user else 'ru'
    
    await callback.message.edit_text("⏳ <b>Проверяем статус платежа...</b>")
    
    result = await check_payment_status(payment_id, payment['yookassa_payment_id'], payment['user_id'])
    if not result:
        not_paid_text = {
            'ru': "❌ <b>Платеж еще не подтвержден</b>\n\nПожалуйста, подождите несколько минут и попробуйте снова.",
            'en': "❌ <b>Payment not confirmed yet</b>\n\nPlease wait a few minutes and try again."
        }
        await callback.message.answer(not_paid_text[lang], reply_markup=get_payment_check_keyboard(payment_id))
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

💎 Приглашайте друзей и получайте бонусы!""",
        'en': f"""📤 <b>Share referral link</b>

🔗 Your link:
https://t.me/{(await bot.get_me()).username}?start={user['referral_code']}

💎 Invite friends and get bonuses!"""
    }
    await callback.message.answer(ref_text[user['language']])
    await callback.answer()

@dp.callback_query(F.data == "generate_image")
async def generate_image_menu(callback: types.CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user: 
        await callback.answer("Сначала используйте /start")
        return
        
    text = {
        'ru': "🎨 <b>Генерация изображений</b>\n\nИспользуйте команду /generate с описанием:\n\n<code>/generate красная спортивная машина в горах</code>",
        'en': "🎨 <b>Image Generation</b>\n\nUse /generate command with description:\n\n<code>/generate red sports car in mountains</code>"
    }
    await callback.message.answer(text[user['language']])
    await callback.answer()

@dp.callback_query(F.data == "stop_generation")
async def stop_generation(callback: types.CallbackQuery):
    if callback.from_user.id in active_generations:
        active_generations[callback.from_user.id] = False
        user = db.get_user(callback.from_user.id)
        lang = user['language'] if user else 'ru'
        stop_text = {
            'ru': "⏹️ <b>Генерация остановлена</b>",
            'en': "⏹️ <b>Generation stopped</b>"
        }
        await callback.message.answer(stop_text[lang])
    await callback.answer()

# ========== ОБРАБОТКА СООБЩЕНИЙ ДЛЯ AI ==========
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user = db.get_user(message.from_user.id)
    if not user: 
        await message.answer("❌ Сначала используйте /start")
        return
        
    # Проверяем лимиты отправки изображений
    can_send, error_msg = db.can_send_image(user['user_id'])
    if not can_send: 
        lang = user['language']
        await message.answer(f"❌ {error_msg}")
        return
        
    # Проверяем общие лимиты
    can_use, error_msg = db.can_use_model(user['user_id'])
    if not can_use: 
        lang = user['language']
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
        lang = user['language']
        error_text = {
            'ru': "❌ Текущая модель не поддерживает изображения",
            'en': "❌ Current model doesn't support images"
        }
        await message.answer(error_text[lang])
        return
    
    # Скачиваем изображение
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = await bot.download_file(file.file_path)
    image_data = base64.b64encode(file_path.read()).decode('utf-8')
    
    lang = user['language']
    wait_text = {
        'ru': "⏳ <b>Обработка изображения...</b>",
        'en': "⏳ <b>Processing image...</b>"
    }
    
    msg = await message.answer(wait_text[lang], reply_markup=get_stop_keyboard())
    active_generations[message.from_user.id] = True
    
    try:
        result = await routerai_service.send_message(
            user['current_model'], 
            message.caption or "Опиши это изображение",
            extra_data={"image": image_data}
        )
        
        if result['success'] and active_generations.get(message.from_user.id):
            response_text = f"🤖 <b>Ответ:</b>\n\n{result['response']}"
            await msg.edit_text(response_text)
        elif not result['success']:
            error_text = f"❌ <b>Ошибка:</b>\n\n{result['error']}"
            await msg.edit_text(error_text)
            
    except Exception as e:
        error_text = {
            'ru': "❌ <b>Ошибка обработки изображения</b>",
            'en': "❌ <b>Image processing error</b>"
        }
        await msg.edit_text(error_text[lang])
    finally:
        active_generations.pop(message.from_user.id, None)

@dp.message(F.text)
async def handle_message(message: types.Message):
    # Пропускаем команды меню
    menu_commands = ["🧠 Выбрать модель", "👤 Мой профиль", "💳 Купить подписку", "🔑 Купить API", 
                    "🎨 Сгенерировать фото", "📤 Рефералка", "🆘 Помощь", "⏹️ Остановить",
                    "🧠 Choose model", "👤 My profile", "💳 Buy subscription", "🔑 Buy API",
                    "🎨 Generate image", "📤 Referral", "🆘 Help", "⏹️ Stop"]
    
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
    wait_text = {
        'ru': "⏳ <b>Генерация началась...</b>",
        'en': "⏳ <b>Generation started...</b>"
    }
    
    msg = await message.answer(wait_text[lang], reply_markup=get_stop_keyboard())
    active_generations[user_id] = True
    
    try:
        result = await routerai_service.send_message(
            user['current_model'], 
            message.text,
            user_conversations[user_id][:-1]
        )
        
        if result['success'] and active_generations.get(user_id):
            user_conversations[user_id].append({"role": "assistant", "content": result['response']})
            response_text = f"🤖 <b>Ответ:</b>\n\n{result['response']}"
            await msg.edit_text(response_text)
        elif not result['success']:
            error_text = f"❌ <b>Ошибка:</b>\n\n{result['error']}"
            await msg.edit_text(error_text)
            
    except Exception as e:
        error_text = {
            'ru': "❌ <b>Ошибка соединения</b>\n\nПопробуйте позже.",
            'en': "❌ <b>Connection error</b>\n\nPlease try again later."
        }
        await msg.edit_text(error_text[lang])
    finally:
        active_generations.pop(user_id, None)

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
    logger.info("Starting GobiAI bot with full functionality...")
    
    # Запускаем сервер для вебхуков
    runner = await start_webhook_server()
    
    logger.info("Starting bot in polling mode...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
