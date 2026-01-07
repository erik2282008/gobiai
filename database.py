import sqlite3
import logging
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db', check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                language TEXT DEFAULT 'ru',
                subscription TEXT DEFAULT 'free',
                subscription_end DATE,
                trial_end DATE,
                daily_used INTEGER DEFAULT 0,
                images_generated_today INTEGER DEFAULT 0,
                images_sent_today INTEGER DEFAULT 0,
                videos_sent_today INTEGER DEFAULT 0,
                last_reset DATE DEFAULT CURRENT_DATE,
                current_model TEXT DEFAULT 'google/gemma-3-4b-it',
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0,
                monthly_tokens_used INTEGER DEFAULT 0,
                monthly_input_tokens INTEGER DEFAULT 0,
                monthly_output_tokens INTEGER DEFAULT 0,
                last_cost_reset DATE DEFAULT CURRENT_DATE,
                is_blocked BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER,
                type TEXT,
                plan_id TEXT,
                model_id TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                yookassa_payment_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_subscription ON users(subscription)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)')
        
        self.conn.commit()
    
    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user:
            return {
                'user_id': user[0],
                'username': user[1],
                'language': user[2],
                'subscription': user[3],
                'subscription_end': user[4],
                'trial_end': user[5],
                'daily_used': user[6],
                'images_generated_today': user[7],
                'images_sent_today': user[8],
                'videos_sent_today': user[9],
                'last_reset': user[10],
                'current_model': user[11],
                'referral_code': user[12],
                'referred_by': user[13],
                'referral_count': user[14],
                'monthly_tokens_used': user[15],
                'monthly_input_tokens': user[16],
                'monthly_output_tokens': user[17],
                'last_cost_reset': user[18],
                'is_blocked': user[19]
            }
        return None
    
    def create_user(self, user_id, username, language='ru', referral_code=None):
        cursor = self.conn.cursor()
        
        # Если это реферал - даем LITE подписку на 10 дней
        subscription = 'free'
        subscription_end = None
        trial_end = (datetime.now() + timedelta(days=30 * Config.TRIAL_MONTHS)).strftime('%Y-%m-%d')
        
        referred_by = None
        
        if referral_code and referral_code.startswith('ref_'):
            try:
                referred_by = int(referral_code.replace('ref_', ''))
                # Даем LITE подписку на 10 дней рефералу
                subscription = 'lite'
                subscription_end = (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d')
                trial_end = None
                
                # Обновляем статистику пригласившего и даем ему тоже LITE на 10 дней
                cursor.execute('''
                    UPDATE users 
                    SET referral_count = referral_count + 1,
                        subscription = 'lite',
                        subscription_end = ?
                    WHERE user_id = ?
                ''', (subscription_end, referred_by))
                
            except Exception as e:
                referred_by = None
        
        # Генерируем реферальный код
        ref_code = f"ref_{user_id}"
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, language, subscription, subscription_end, trial_end, referral_code, referred_by) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, language, subscription, subscription_end, trial_end, ref_code, referred_by))
        
        self.conn.commit()
        return self.get_user(user_id)
    
    def update_user_subscription(self, user_id, subscription, duration_days=30):
        cursor = self.conn.cursor()
        subscription_end = (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            UPDATE users 
            SET subscription = ?, subscription_end = ?
            WHERE user_id = ?
        ''', (subscription, subscription_end, user_id))
        
        self.conn.commit()
    
    def update_user_model(self, user_id, model_id):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET current_model = ? WHERE user_id = ?', (model_id, user_id))
        self.conn.commit()
    
    def increment_daily_usage(self, user_id):
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT last_reset FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        last_reset = result[0] if result else None
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        if last_reset != today:
            cursor.execute('''
                UPDATE users 
                SET daily_used = 0, 
                    images_generated_today = 0,
                    images_sent_today = 0,
                    videos_sent_today = 0,
                    last_reset = ? 
                WHERE user_id = ?
            ''', (today, user_id))
        
        cursor.execute('UPDATE users SET daily_used = daily_used + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def update_media_usage(self, user_id, media_type):
        """Обновляет счетчики медиафайлов"""
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT last_reset FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        last_reset = result[0] if result else None
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        if last_reset != today:
            cursor.execute('''
                UPDATE users 
                SET daily_used = 0, 
                    images_generated_today = 0,
                    images_sent_today = 0,
                    videos_sent_today = 0,
                    last_reset = ? 
                WHERE user_id = ?
            ''', (today, user_id))
        
        if media_type == 'image_generate':
            cursor.execute('UPDATE users SET images_generated_today = images_generated_today + 1 WHERE user_id = ?', (user_id,))
        elif media_type == 'image_send':
            cursor.execute('UPDATE users SET images_sent_today = images_sent_today + 1 WHERE user_id = ?', (user_id,))
        elif media_type == 'video_send':
            cursor.execute('UPDATE users SET videos_sent_today = videos_sent_today + 1 WHERE user_id = ?', (user_id,))
        
        self.conn.commit()
    
    def can_use_model(self, user_id):
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        if user.get('is_blocked'):
            return False, "Account blocked"
        
        today = datetime.now().strftime('%Y-%m-%d')
        if user['last_reset'] != today:
            return True, ""
        
        plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
        if not plan:
            return False, "Subscription plan not found"
        
        if user['daily_used'] >= plan['daily_limit']:
            return False, f"Daily limit ({plan['daily_limit']} messages) exceeded"
        
        return True, ""
    
    def can_generate_image(self, user_id):
        """Проверяет можно ли генерировать изображения"""
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
        if not plan:
            return False, "Plan not found"
        
        if user['images_generated_today'] >= plan['image_generate']:
            return False, f"Image generation limit reached ({plan['image_generate']}/day)"
        
        return True, ""
    
    def can_send_image(self, user_id):
        """Проверяет можно ли отправлять изображения"""
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
        if not plan:
            return False, "Plan not found"
        
        if user['images_sent_today'] >= plan['image_send']:
            return False, f"Image send limit reached ({plan['image_send']}/day)"
        
        return True, ""
    
    def can_send_video(self, user_id):
        """Проверяет можно ли отправлять видео"""
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
        if not plan:
            return False, "Plan not found"
        
        if user['videos_sent_today'] >= plan['video_send']:
            return False, f"Video send limit reached ({plan['video_send']}/day)"
        
        return True, ""
    
    def check_monthly_token_limits(self, user_id, input_tokens=0, output_tokens=0):
        """Проверяет месячные лимиты токенов"""
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        # Сброс счетчика в начале месяца
        today = datetime.now()
        first_day_of_month = today.replace(day=1)
        if user['last_cost_reset'] != first_day_of_month.strftime('%Y-%m-%d'):
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET monthly_tokens_used = 0, 
                    monthly_input_tokens = 0,
                    monthly_output_tokens = 0,
                    last_cost_reset = ?,
                    is_blocked = FALSE
                WHERE user_id = ?
            ''', (first_day_of_month.strftime('%Y-%m-%d'), user_id))
            self.conn.commit()
            user = self.get_user(user_id)
        
        # Лимиты для разных подписок (60% на ответы, 40% на вопросы)
        if user['subscription'] == 'free':
            max_total = 15000
            max_input = int(max_total * 0.4)  # 6K
            max_output = int(max_total * 0.6)  # 9K
        else:
            max_total = 850000
            max_input = int(max_total * 0.4)  # 340K
            max_output = int(max_total * 0.6)  # 510K
        
        # Проверка лимитов
        if user['monthly_tokens_used'] + input_tokens + output_tokens > max_total:
            cursor = self.conn.cursor()
            cursor.execute('UPDATE users SET is_blocked = TRUE WHERE user_id = ?', (user_id,))
            self.conn.commit()
            return False, f"Monthly token limit reached ({max_total} tokens)"
        
        if user['monthly_input_tokens'] + input_tokens > max_input:
            return False, f"Monthly input token limit reached ({max_input} tokens)"
        
        if user['monthly_output_tokens'] + output_tokens > max_output:
            return False, f"Monthly output token limit reached ({max_output} tokens)"
        
        return True, ""
    
    def update_token_usage(self, user_id, input_tokens, output_tokens):
        """Обновляет счетчики использованных токенов"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET monthly_tokens_used = monthly_tokens_used + ?,
                monthly_input_tokens = monthly_input_tokens + ?,
                monthly_output_tokens = monthly_output_tokens + ?
            WHERE user_id = ?
        ''', (input_tokens + output_tokens, input_tokens, output_tokens, user_id))
        self.conn.commit()
    
    def create_payment(self, payment_id, user_id, payment_type, plan_id=None, model_id=None, amount=0):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT INTO payments 
            (payment_id, user_id, type, plan_id, model_id, amount, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ''', (payment_id, user_id, payment_type, plan_id, model_id, amount))
        
        self.conn.commit()
    
    def update_payment_status(self, payment_id, status, yookassa_id=None):
        cursor = self.conn.cursor()
        
        if yookassa_id:
            cursor.execute('''
                UPDATE payments 
                SET status = ?, yookassa_payment_id = ?
                WHERE payment_id = ?
            ''', (status, yookassa_id, payment_id))
        else:
            cursor.execute('''
                UPDATE payments 
                SET status = ?
                WHERE payment_id = ?
            ''', (status, payment_id))
        
        self.conn.commit()
    
    def get_payment(self, payment_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,))
        payment = cursor.fetchone()
        
        if payment:
            return {
                'payment_id': payment[0],
                'user_id': payment[1],
                'type': payment[2],
                'plan_id': payment[3],
                'model_id': payment[4],
                'amount': payment[5],
                'status': payment[6],
                'yookassa_payment_id': payment[7]
            }
        return None
    
    def get_payment_by_yookassa_id(self, yookassa_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM payments WHERE yookassa_payment_id = ?', (yookassa_id,))
        payment = cursor.fetchone()
        
        if payment:
            return {
                'payment_id': payment[0],
                'user_id': payment[1],
                'type': payment[2],
                'plan_id': payment[3],
                'model_id': payment[4],
                'amount': payment[5],
                'status': payment[6],
                'yookassa_payment_id': payment[7]
            }
        return None

db = Database()
