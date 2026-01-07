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
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                language TEXT DEFAULT 'ru',
                subscription TEXT DEFAULT 'free',
                subscription_end DATE,
                trial_end DATE,
                daily_used INTEGER DEFAULT 0,
                last_reset DATE DEFAULT CURRENT_DATE,
                current_model TEXT DEFAULT 'google/gemma-3-4b-it',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица платежей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER,
                type TEXT, -- 'subscription' или 'api_key'
                plan_id TEXT,
                model_id TEXT,
                amount REAL,
                status TEXT DEFAULT 'pending',
                yookassa_payment_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица API ключей (покупки)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_key_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                model_id TEXT,
                payment_id TEXT,
                status TEXT DEFAULT 'pending', -- pending, completed
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (payment_id) REFERENCES payments (payment_id)
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
                'last_reset': user[7],
                'current_model': user[8]
            }
        return None
    
    def create_user(self, user_id, username, language='ru'):
        cursor = self.conn.cursor()
        trial_end = (datetime.now() + timedelta(days=30 * Config.TRIAL_MONTHS)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, language, trial_end) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, language, trial_end))
        
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
        
        # Сбрасываем счетчик если новый день
        cursor.execute('SELECT last_reset FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        last_reset = result[0] if result else None
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        if last_reset != today:
            cursor.execute('''
                UPDATE users 
                SET daily_used = 0, last_reset = ? 
                WHERE user_id = ?
            ''', (today, user_id))
        
        cursor.execute('UPDATE users SET daily_used = daily_used + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def can_use_model(self, user_id):
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        # Проверяем дневной лимит
        today = datetime.now().strftime('%Y-%m-%d')
        if user['last_reset'] != today:
            return True, ""
        
        plan = next((p for p in Config.SUBSCRIPTION_PLANS if p['id'] == user['subscription']), None)
        if not plan:
            return False, "Subscription plan not found"
        
        if user['daily_used'] >= plan['daily_limit']:
            return False, f"Дневной лимит ({plan['daily_limit']} сообщений) исчерпан"
        
        return True, ""
    
    # Платежи
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
        
        # Если платеж успешный, обновляем подписку
        if status == 'succeeded':
            payment = self.get_payment(payment_id)
            if payment and payment['type'] == 'subscription':
                self.update_user_subscription(payment['user_id'], payment['plan_id'])
            elif payment and payment['type'] == 'api_key':
                self.create_api_key_purchase(payment['user_id'], payment['model_id'], payment_id)
    
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
    
    def create_api_key_purchase(self, user_id, model_id, payment_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO api_key_purchases 
            (user_id, model_id, payment_id, status)
            VALUES (?, ?, ?, 'completed')
        ''', (user_id, model_id, payment_id))
        self.conn.commit()
    
    def get_user_api_purchases(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT ap.*, p.amount 
            FROM api_key_purchases ap
            JOIN payments p ON ap.payment_id = p.payment_id
            WHERE ap.user_id = ? AND ap.status = 'completed'
        ''', (user_id,))
        return cursor.fetchall()

# Глобальный экземпляр базы данных
db = Database()
