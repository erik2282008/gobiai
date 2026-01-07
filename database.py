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
                referral_bonus_days INTEGER DEFAULT 0,
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
                'referral_bonus_days': user[15]
            }
        return None
    
    def create_user(self, user_id, username, language='ru', referral_code=None):
        cursor = self.conn.cursor()
        trial_end = (datetime.now() + timedelta(days=30 * Config.TRIAL_MONTHS)).strftime('%Y-%m-%d')
        
        # Генерируем реферальный код
        ref_code = f"ref_{user_id}"
        
        referred_by = None
        referral_bonus = 0
        
        if referral_code and referral_code.startswith('ref_'):
            try:
                referred_by = int(referral_code.replace('ref_', ''))
                # Добавляем бонусные дни пригласившему
                cursor.execute('''
                    UPDATE users 
                    SET referral_count = referral_count + 1,
                        referral_bonus_days = referral_bonus_days + ?
                    WHERE user_id = ?
                ''', (Config.REFERRAL_REWARD_DAYS, referred_by))
                
                # Даем бонус новому пользователю
                referral_bonus = Config.REFERRAL_REWARD_DAYS
                trial_end = (datetime.now() + timedelta(days=30 * Config.TRIAL_MONTHS + Config.REFERRAL_REWARD_DAYS)).strftime('%Y-%m-%d')
            except:
                referred_by = None
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, language, trial_end, referral_code, referred_by, referral_bonus_days) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, language, trial_end, ref_code, referred_by, referral_bonus))
        
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
