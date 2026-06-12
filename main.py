import os, hashlib, random, re
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, flash

# ========== НАСТРОЙКИ ==========
SECRET_KEY = "supersecretkey123_wishlist_pro_2026"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
PORT = int(os.getenv("PORT", 5000))
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(days=30)

# ========== УМНОЕ ПОДКЛЮЧЕНИЕ К БД ==========
def get_db():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        import psycopg
        from psycopg.rows import dict_row
        if 'sslmode=' not in db_url:
            db_url += '?sslmode=require'
        conn = psycopg.connect(db_url, row_factory=dict_row)
        return conn, 'postgres'
    else:
        import sqlite3
        conn = sqlite3.connect('wishlist.db')
        conn.row_factory = sqlite3.Row
        return conn, 'sqlite'
        
def ph(db_type):
    return '%s' if db_type == 'postgres' else '?'

def db_id_col(db_type):
    return 'SERIAL PRIMARY KEY' if db_type == 'postgres' else 'INTEGER PRIMARY KEY AUTOINCREMENT'

def db_bool_default(db_type):
    return 'BOOLEAN DEFAULT FALSE' if db_type == 'postgres' else 'INTEGER DEFAULT 0'

def db_bool_true(db_type):
    return 'BOOLEAN DEFAULT TRUE' if db_type == 'postgres' else 'INTEGER DEFAULT 1'

def db_date_default(db_type):
    return 'DATE DEFAULT CURRENT_DATE' if db_type == 'postgres' else 'DATE'

def as_bool(value):
    if value is None: return False
    if isinstance(value, bool): return value
    return bool(value)

def add_column_if_not_exists(cur, table, column, definition):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"✅ Добавлена колонка {column} в {table}")
    except Exception:
        pass

# ========== ИНИЦИАЛИЗАЦИЯ БД ==========
def init_db():
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    id_col = db_id_col(db_type)
    bool_def = db_bool_default(db_type)
    bool_true = db_bool_true(db_type)
    date_def = db_date_default(db_type)

    if db_type == 'postgres':
        cur.execute(f'''CREATE TABLE IF NOT EXISTS users (
            id {id_col}, username TEXT UNIQUE, password TEXT, email TEXT,
            theme TEXT DEFAULT 'light', currency TEXT DEFAULT 'BYN',
            created_at {date_def}, is_admin {bool_def}, is_banned {bool_def},
            last_login DATE, login_count INTEGER DEFAULT 0
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS wishlists (
            id {id_col}, user_id INTEGER, title TEXT, description TEXT,
            slug TEXT UNIQUE, is_default {bool_def}, is_public {bool_true},
            cover_emoji TEXT DEFAULT '🎁', created_at {date_def}
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS wishlist_items (
            id {id_col}, wishlist_id INTEGER, title TEXT, description TEXT, link TEXT,
            price NUMERIC(10,2), currency TEXT, image_url TEXT,
            status TEXT DEFAULT 'active', reserved_by INTEGER,
            priority INTEGER DEFAULT 0, created_at {date_def},
            is_secret {bool_def}, is_collective {bool_def},
            goal_amount NUMERIC(10,2), guest_name TEXT, guest_email TEXT
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS ideas (
            id {id_col}, title TEXT, description TEXT,
            price NUMERIC(10,2), currency TEXT, image_url TEXT, link TEXT,
            category TEXT, source TEXT DEFAULT 'manual',
            added_by INTEGER, created_at {date_def}
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS reservations (
            id {id_col}, item_id INTEGER, reserved_by INTEGER,
            reserved_at {date_def}
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS contributions (
            id {id_col}, item_id INTEGER, user_id INTEGER,
            guest_name TEXT, amount NUMERIC(10,2), created_at {date_def}
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS password_resets (
            id {id_col}, user_id INTEGER, token TEXT UNIQUE,
            expires_at TIMESTAMP, used {bool_def}
        )''')
        cur.execute(f'SELECT id FROM users WHERE username = {p}', (ADMIN_USERNAME,))
        if not cur.fetchone():
            hashed_pw = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
            cur.execute(f'''INSERT INTO users (username, password, is_admin, created_at, last_login, login_count)
                           VALUES ({p}, {p}, TRUE, CURRENT_DATE, CURRENT_DATE, 0)''',
                        (ADMIN_USERNAME, hashed_pw))
            print(f"👤 Админ создан: {ADMIN_USERNAME}/{ADMIN_PASSWORD}")
    else:
        cur.execute(f'''CREATE TABLE IF NOT EXISTS users (
            id {id_col}, username TEXT UNIQUE, password TEXT, email TEXT,
            theme TEXT DEFAULT 'light', currency TEXT DEFAULT 'BYN',
            created_at DATE, is_admin INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
            last_login DATE, login_count INTEGER DEFAULT 0
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS wishlists (
            id {id_col}, user_id INTEGER, title TEXT, description TEXT,
            slug TEXT UNIQUE, is_default INTEGER DEFAULT 0, is_public INTEGER DEFAULT 1,
            cover_emoji TEXT DEFAULT '🎁', created_at DATE
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS wishlist_items (
            id {id_col}, wishlist_id INTEGER, title TEXT, description TEXT, link TEXT,
            price REAL, currency TEXT, image_url TEXT,
            status TEXT DEFAULT 'active', reserved_by INTEGER,
            priority INTEGER DEFAULT 0, created_at DATE,
            is_secret INTEGER DEFAULT 0, is_collective INTEGER DEFAULT 0,
            goal_amount REAL, guest_name TEXT, guest_email TEXT
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS ideas (
            id {id_col}, title TEXT, description TEXT,
            price REAL, currency TEXT, image_url TEXT, link TEXT,
            category TEXT, source TEXT DEFAULT 'manual',
            added_by INTEGER, created_at DATE
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS reservations (
            id {id_col}, item_id INTEGER, reserved_by INTEGER, reserved_at DATE
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS contributions (
            id {id_col}, item_id INTEGER, user_id INTEGER,
            guest_name TEXT, amount REAL, created_at DATE
        )''')
        cur.execute(f'''CREATE TABLE IF NOT EXISTS password_resets (
            id {id_col}, user_id INTEGER, token TEXT UNIQUE,
            expires_at TEXT, used INTEGER DEFAULT 0
        )''')
        cur.execute(f'SELECT * FROM users WHERE username={p}', (ADMIN_USERNAME,))
        if not cur.fetchone():
            hashed_pw = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
            cur.execute(f'''INSERT INTO users (username, password, is_admin, created_at, last_login, login_count)
                           VALUES ({p}, {p}, 1, ?, ?, 0)''',
                        (ADMIN_USERNAME, hashed_pw, datetime.now().date(), datetime.now().date()))
            print(f"👤 Админ создан: {ADMIN_USERNAME}/{ADMIN_PASSWORD}")

    # Миграции на случай обновления
    if db_type == 'postgres':
        add_column_if_not_exists(cur, 'wishlist_items', 'is_secret', 'BOOLEAN DEFAULT FALSE')
        add_column_if_not_exists(cur, 'wishlist_items', 'is_collective', 'BOOLEAN DEFAULT FALSE')
        add_column_if_not_exists(cur, 'wishlist_items', 'goal_amount', 'NUMERIC(10,2)')
        add_column_if_not_exists(cur, 'wishlist_items', 'guest_name', 'TEXT')
        add_column_if_not_exists(cur, 'wishlist_items', 'guest_email', 'TEXT')
    else:
        add_column_if_not_exists(cur, 'wishlist_items', 'is_secret', 'INTEGER DEFAULT 0')
        add_column_if_not_exists(cur, 'wishlist_items', 'is_collective', 'INTEGER DEFAULT 0')
        add_column_if_not_exists(cur, 'wishlist_items', 'goal_amount', 'REAL')
        add_column_if_not_exists(cur, 'wishlist_items', 'guest_name', 'TEXT')
        add_column_if_not_exists(cur, 'wishlist_items', 'guest_email', 'TEXT')

    conn.commit()
    cur.close()
    conn.close()
    add_manual_ideas()

# ========== ИДЕИ ==========
def add_manual_ideas():
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT COUNT(*) as cnt FROM ideas WHERE source={p}', ('manual',))
    cnt_row = cur.fetchone()
    cnt = cnt_row['cnt'] if cnt_row else 0
    if cnt > 0:
        cur.close(); conn.close()
        return

    ideas_data = [
        ("Подарочная карта Starbucks", "Универсальный подарок для кофемана", 50, "BYN", "", "", "Подарочные карты"),
        ("Сертификат в SPA", "День релакса и красоты", 100, "BYN", "", "", "Впечатления"),
        ("Сертификат в магазин косметики", "Любимая косметика", 80, "BYN", "", "", "Подарочные карты"),
        ("Сертификат в магазин одежды", "Шопинг мечты", 150, "BYN", "", "", "Подарочные карты"),
        ("Сертификат Ozon", "Любой товар с доставкой", 100, "BYN", "", "", "Подарочные карты"),
        ("Сертификат Wildberries", "Миллионы товаров", 100, "BYN", "", "", "Подарочные карты"),
        ("Билет в кино на двоих", "Просмотр новинки в VIP зале", 30, "BYN", "", "", "Впечатления"),
        ("Ужин в ресторане", "Романтический вечер", 80, "BYN", "", "", "Впечатления"),
        ("Мастер-класс по кулинарии", "Учимся готовить вместе", 60, "BYN", "", "", "Впечатления"),
        ("Фотосессия", "Профессиональная съемка", 120, "BYN", "", "", "Впечатления"),
        ("Квест в реальности", "Командное приключение", 40, "BYN", "", "", "Впечатления"),
        ("Прыжок с парашютом", "Экстремальный подарок", 200, "BYN", "", "", "Впечатления"),
        ("Полет на воздушном шаре", "Романтическое приключение", 300, "BYN", "", "", "Впечатления"),
        ("Концерт любимой группы", "Незабываемые эмоции", 100, "BYN", "", "", "Впечатления"),
        ("Билет в театр", "Классическое искусство", 50, "BYN", "", "", "Впечатления"),
        ("Билет на стендап", "Вечер смеха", 40, "BYN", "", "", "Впечатления"),
        ("Картинг", "Скорость и адреналин", 50, "BYN", "", "", "Впечатления"),
        ("Пейнтбол", "Командная игра", 45, "BYN", "", "", "Впечатления"),
        ("Лазертаг", "Футуристическая битва", 40, "BYN", "", "", "Впечатления"),
        ("Верховая езда", "Прогулка на лошадях", 70, "BYN", "", "", "Впечатления"),
        ("Дайвинг", "Подводный мир", 150, "BYN", "", "", "Впечатления"),
        ("Мастер-класс по гончарному делу", "Создай свою вазу", 50, "BYN", "", "", "Впечатления"),
        ("Дегустация вин", "Изысканный вечер", 90, "BYN", "", "", "Впечатления"),
        ("Подписка Netflix", "Год безлимитного кино", 80, "BYN", "", "", "Подписки"),
        ("Подписка Spotify", "Год любимой музыки", 50, "BYN", "", "", "Подписки"),
        ("Подписка Яндекс.Плюс", "Музыка, кино, книги", 60, "BYN", "", "", "Подписки"),
        ("Подписка ChatGPT Plus", "ИИ помощник на год", 150, "BYN", "", "", "Подписки"),
        ("Подписка YouTube Premium", "Без рекламы + музыка", 70, "BYN", "", "", "Подписки"),
        ("Кастомные кроссовки", "Уникальная роспись", 150, "BYN", "", "", "Кастом"),
        ("Портрет на заказ", "Картина по фото", 100, "BYN", "", "", "Кастом"),
        ("Именная кружка", "Персонализированный подарок", 20, "BYN", "", "", "Кастом"),
        ("Фотокнига", "Альбом с лучшими моментами", 40, "BYN", "", "", "Кастом"),
        ("Звездная карта", "Небо в важный день", 45, "BYN", "", "", "Кастом"),
        ("Донат в любимый фонд", "Благотворительный подарок", 50, "BYN", "", "", "Благотворительность"),
        ("Посадить дерево", "Экологичный подарок", 30, "BYN", "", "", "Благотворительность"),
        ("Помощь приюту для животных", "Корм и лекарства", 40, "BYN", "", "", "Благотворительность"),
        ("Коробка элитного чая", "10 видов со всего мира", 60, "BYN", "", "", "Еда"),
        ("Набор шоколада ручной работы", "Бельгийский шоколад", 50, "BYN", "", "", "Еда"),
        ("Кофейный набор", "Зерна из Эфиопии + френч-пресс", 80, "BYN", "", "", "Еда"),
        ("Онлайн-курс программирования", "Python для начинающих", 200, "BYN", "", "", "Образование"),
        ("Курс английского языка", "3 месяца занятий", 300, "BYN", "", "", "Образование"),
        ("Массаж всего тела", "60 минут релакса", 70, "BYN", "", "", "Красота"),
        ("SPA-день", "Полный комплекс процедур", 200, "BYN", "", "", "Красота"),
        ("Курс йоги", "12 занятий", 150, "BYN", "", "", "Красота"),
    ]

    for idea in ideas_data:
        if db_type == 'postgres':
            cur.execute(f'''INSERT INTO ideas (title, description, price, currency, image_url, link, category, source, created_at)
                           VALUES ({p},{p},{p},{p},{p},{p},{p},{p},CURRENT_DATE)''',
                        (*idea, 'manual'))
        else:
            cur.execute(f'''INSERT INTO ideas (title, description, price, currency, image_url, link, category, source, created_at)
                           VALUES ({p},{p},{p},{p},{p},{p},{p},{p},?)''',
                        (*idea, 'manual', datetime.now().date()))

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Добавлено {len(ideas_data)} идей!")

# ========== УТИЛИТЫ ==========
def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = text.strip('-') or 'wish'
    suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=5))
    return f"{text}-{suffix}"

def generate_captcha():
    num1, num2 = random.randint(1, 10), random.randint(1, 10)
    ops = [('+', num1 + num2), ('-', num1 - num2), ('*', num1 * num2)]
    op, answer = random.choice(ops)
    return f"{num1} {op} {num2}", answer

# ========== ВАЛЮТЫ (с KZT и UAH) ==========
CURRENCIES = {
    'BYN': '🇧🇾 BYN', 'USD': '🇺🇸 USD', 'EUR': '🇪🇺 EUR',
    'RUB': '🇷🇺 RUB', 'KZT': '🇰🇿 KZT', 'UAH': '🇺🇦 UAH'
}

EXCHANGE_RATES = {
    'BYN': 1.0, 'USD': 0.31, 'EUR': 0.29,
    'RUB': 28.5, 'KZT': 148.5, 'UAH': 12.8
}

CURRENCY_SYMBOLS = {
    'BYN': 'Br', 'USD': '$', 'EUR': '€',
    'RUB': '₽', 'KZT': '₸', 'UAH': '₴'
}

def convert_price(price, from_currency, to_currency):
    if not price: return 0
    if from_currency == to_currency: return price
    try:
        in_byn = float(price) / EXCHANGE_RATES.get(from_currency, 1)
        return round(in_byn * EXCHANGE_RATES.get(to_currency, 1), 2)
    except:
        return price

def format_price(price, currency):
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    return f"{price} {symbol}"

THEMES = {
    'light': '☀️ Светлая', 'dark': '🌙 Тёмная', 'blue': '💙 Синяя',
    'green': '💚 Зелёная', 'purple': '💜 Фиолетовая', 'pink': '💗 Розовая'
}

# ========== ПРОВЕРКА EMAIL ==========
def validate_email_real(email):
    if not email:
        return True, "OK"
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return False, "Некорректный формат email"
    temp_domains = [
        'mailinator.com', 'tempmail.com', '10minutemail.com', 'guerrillamail.com',
        'throwawaymail.com', 'yopmail.com', 'maildrop.cc', 'trashmail.com',
        'fakeinbox.com', 'sharklasers.com', 'temp-mail.org', 'getnada.com',
        'mailnesia.com', 'dispostable.com', 'tempinbox.com', 'mailcatch.com'
    ]
    domain = email.split('@')[1].lower()
    if domain in temp_domains:
        return False, "Временные почты запрещены"
    try:
        import dns.resolver
        records = dns.resolver.resolve(domain, 'MX')
        if not records:
            return False, "Домен не принимает письма"
    except ImportError:
        return True, "OK"
    except Exception:
        return False, "Домен не существует"
    return True, "OK"

def send_email(to_email, subject, html_content):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER', '')
    smtp_pass = os.getenv('SMTP_PASS', '')
    if not smtp_user or not smtp_pass:
        print(f"⚠️ SMTP не настроен. Письмо для {to_email}: {subject}")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = to_email
        msg.attach(MIMEText(html_content, 'html'))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки email: {e}")
        return False

# ========== HTML ШАБЛОН (с адаптивом + подарочной коробкой) ==========
HTML_BASE = '''
<!DOCTYPE html>
<html lang="ru" data-theme="{{ theme }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} • WishList Pro</title>
    <style>
        :root {
            --bg: #f5f7fa; --card: white; --text: #1f2937; --text-secondary: #6b7280;
            --primary: #6366f1; --primary-hover: #4f46e5; --border: #e5e7eb;
            --success: #10b981; --warning: #f59e0b; --danger: #ef4444;
            --gift-red: #dc2626; --gift-gold: #fbbf24;
        }
        [data-theme="dark"] { --bg: #0f172a; --card: #1e293b; --text: #f1f5f9; --text-secondary: #94a3b8; --primary: #818cf8; --primary-hover: #6366f1; --border: #334155; }
        [data-theme="blue"] { --primary: #0ea5e9; }
        [data-theme="green"] { --primary: #22c55e; }
        [data-theme="purple"] { --primary: #a855f7; }
        [data-theme="pink"] { --primary: #ec4899; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh; }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideIn { from { opacity: 0; transform: translateX(-30px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
        @keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
        @keyframes gradientMove { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        @keyframes giftBounce { 0%, 100% { transform: translateY(0) rotate(-3deg); } 50% { transform: translateY(-10px) rotate(3deg); } }
        @keyframes giftShine { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
        @keyframes botPulse { 0%, 100% { box-shadow: 0 10px 30px rgba(99, 102, 241, 0.4); } 50% { box-shadow: 0 10px 30px rgba(99, 102, 241, 0.8), 0 0 0 15px rgba(99, 102, 241, 0.1); } }

        .animate-fade { animation: fadeIn 0.6s ease-out; }
        .animate-slide { animation: slideIn 0.5s ease-out; }
        .animate-scale { animation: scaleIn 0.4s ease-out; }
        .animate-bounce { animation: bounce 2s infinite; }
        .animate-float { animation: float 3s ease-in-out infinite; }

        .container { max-width: 1200px; margin: 0 auto; padding: 20px; animation: fadeIn 0.5s ease-out; }
        .header { background: var(--card); padding: 16px 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); margin-bottom: 30px; position: sticky; top: 0; z-index: 100; }
        .header-content { max-width: 1200px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 22px; font-weight: 800; color: var(--primary); text-decoration: none; display: flex; align-items: center; gap: 8px; }
        .nav { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .nav a { color: var(--text); text-decoration: none; padding: 8px 14px; border-radius: 10px; font-size: 14px; font-weight: 500; transition: all 0.3s; }
        .nav a:hover { background: var(--bg); color: var(--primary); transform: translateY(-2px); }

        .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 10px 20px; background: var(--primary); color: white; border: none; border-radius: 10px; cursor: pointer; text-decoration: none; font-size: 14px; font-weight: 600; transition: all 0.3s; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2); }
        .btn:hover { background: var(--primary-hover); transform: translateY(-2px); box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4); }
        .btn-secondary { background: var(--card); color: var(--text); border: 2px solid var(--border); box-shadow: none; }
        .btn-secondary:hover { background: var(--bg); border-color: var(--primary); color: var(--primary); }
        .btn-success { background: var(--success); }
        .btn-warning { background: var(--warning); }
        .btn-danger { background: var(--danger); }
        .btn-lg { padding: 14px 28px; font-size: 16px; }
        .btn-sm { padding: 6px 12px; font-size: 12px; }
        .btn-block { width: 100%; }

        .card { background: var(--card); padding: 24px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); margin-bottom: 20px; transition: all 0.4s; border: 1px solid var(--border); }
        .card:hover { transform: translateY(-4px); box-shadow: 0 12px 40px rgba(0,0,0,0.12); }

        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
        .grid-2 { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }

        .form-group { margin-bottom: 18px; }
        .form-group label { display: block; margin-bottom: 6px; font-weight: 600; font-size: 14px; }
        .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 12px 14px; border: 2px solid var(--border); border-radius: 10px; background: var(--card); color: var(--text); font-family: inherit; font-size: 14px; transition: all 0.3s; }
        .form-group input:focus, .form-group textarea:focus, .form-group select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1); }

        .alert { padding: 14px 20px; border-radius: 12px; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; animation: slideIn 0.4s ease-out; border-left: 4px solid; }
        .alert-success { background: #d1fae5; color: #065f46; border-color: var(--success); }
        .alert-error { background: #fee2e2; color: #991b1b; border-color: var(--danger); }
        .alert-info { background: #dbeafe; color: #1e40af; border-color: #3b82f6; }

        .badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }
        .badge-success { background: #d1fae5; color: #065f46; }
        .badge-warning { background: #fef3c7; color: #92400e; }
        .badge-primary { background: var(--primary); color: white; }
        .badge-danger { background: #fee2e2; color: #991b1b; }
        .badge-secret { background: linear-gradient(135deg, #7c3aed, #4f46e5); color: white; }
        .badge-collective { background: linear-gradient(135deg, #10b981, #059669); color: white; }

        .item-card { border: 2px solid var(--border); border-radius: 16px; overflow: hidden; transition: all 0.4s; background: var(--card); position: relative; }
        .item-card:hover { transform: translateY(-6px); box-shadow: 0 20px 40px rgba(0,0,0,0.15); border-color: var(--primary); }
        .item-image { width: 100%; height: 220px; background: var(--bg); display: flex; align-items: center; justify-content: center; font-size: 72px; overflow: hidden; position: relative; }
        .item-image img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.5s; }
        .item-card:hover .item-image img { transform: scale(1.1); }
        .item-content { padding: 20px; }
        .item-title { font-size: 17px; font-weight: 700; margin-bottom: 8px; }
        .item-price { font-size: 22px; font-weight: 800; color: var(--primary); margin-bottom: 10px; }
        .item-description { color: var(--text-secondary); margin-bottom: 15px; font-size: 14px; }

        .flex { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .flex-between { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
        .flex-center { display: flex; justify-content: center; align-items: center; gap: 10px; }
        .mb-4 { margin-bottom: 20px; }
        .text-center { text-align: center; }

        .captcha-box { background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(168, 85, 247, 0.1)); padding: 20px; border-radius: 12px; margin: 15px 0; text-align: center; border: 2px dashed var(--primary); }
        .captcha-question { font-size: 28px; font-weight: 800; color: var(--primary); margin-bottom: 10px; }

        .hero { text-align: center; padding: 60px 20px; background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(168, 85, 247, 0.05)); border-radius: 24px; margin-bottom: 40px; }
        .hero h1 { font-size: 52px; font-weight: 900; margin-bottom: 16px; background: linear-gradient(135deg, var(--primary), #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-size: 200% 200%; animation: gradientMove 5s ease infinite; }
        .hero p { font-size: 20px; color: var(--text-secondary); margin-bottom: 32px; }

        .stat-card { background: var(--card); padding: 24px; border-radius: 16px; text-align: center; transition: all 0.3s; border: 2px solid var(--border); }
        .stat-card:hover { transform: translateY(-4px); border-color: var(--primary); }
        .stat-number { font-size: 36px; font-weight: 900; color: var(--primary); background: linear-gradient(135deg, var(--primary), #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stat-label { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }

        .wish-card { background: var(--card); border-radius: 16px; padding: 20px; border: 2px solid var(--border); transition: all 0.4s; cursor: pointer; animation: fadeIn 0.5s ease-out; }
        .wish-card:hover { transform: translateY(-6px); border-color: var(--primary); box-shadow: 0 12px 30px rgba(0,0,0,0.1); }
        .wish-card-emoji { font-size: 48px; margin-bottom: 12px; display: block; animation: float 3s ease-in-out infinite; }
        .wish-card-title { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
        .wish-card-meta { color: var(--text-secondary); font-size: 13px; display: flex; gap: 10px; flex-wrap: wrap; }

        .empty-state { text-align: center; padding: 60px 20px; background: var(--card); border-radius: 16px; border: 2px dashed var(--border); }
        .empty-state-icon { font-size: 72px; margin-bottom: 16px; animation: bounce 2s infinite; display: inline-block; }

        .toast { position: fixed; bottom: 20px; right: 20px; background: var(--card); padding: 16px 24px; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); display: none; animation: slideIn 0.4s; z-index: 2000; border-left: 4px solid var(--primary); }
        .toast.show { display: flex; }

        .emoji-picker { display: grid; grid-template-columns: repeat(8, 1fr); gap: 6px; margin: 10px 0; }
        .emoji-option { font-size: 24px; padding: 8px; cursor: pointer; border-radius: 8px; transition: all 0.2s; border: 2px solid transparent; text-align: center; }
        .emoji-option:hover { background: var(--bg); transform: scale(1.2); }
        .emoji-option.selected { border-color: var(--primary); background: var(--bg); }

        .image-preview { width: 100%; height: 200px; border-radius: 12px; background: var(--bg); display: flex; align-items: center; justify-content: center; overflow: hidden; margin-top: 10px; border: 2px dashed var(--border); }
        .image-preview img { width: 100%; height: 100%; object-fit: cover; }

        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }
        th { background: var(--bg); font-weight: 700; font-size: 13px; }

        /* === ПОДАРОЧНАЯ КОРОБКА (красно-золотая) === */
        .gift-box {
            display: inline-block;
            font-size: 3em;
            filter: drop-shadow(0 4px 8px rgba(220, 38, 38, 0.3));
            animation: giftBounce 3s ease-in-out infinite;
            background: linear-gradient(135deg, #dc2626 0%, #fbbf24 50%, #dc2626 100%);
            background-size: 200% 200%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: giftBounce 3s ease-in-out infinite, giftShine 3s ease infinite;
        }

        /* === СКРЫТЫЕ ЖЕЛАНИЯ === */
        .secret-item .item-image img, .secret-item .item-image { filter: blur(12px); }
        .secret-overlay {
            position: absolute; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6);
            display: flex; align-items: center; justify-content: center;
            color: white; font-size: 48px;
            backdrop-filter: blur(2px);
            pointer-events: none;
        }

        /* === КОЛЛЕКТИВНЫЙ ПОДАРОК === */
        .collective-progress {
            background: var(--bg);
            border-radius: 12px;
            height: 24px;
            overflow: hidden;
            margin: 12px 0;
            border: 1px solid var(--border);
        }
        .collective-progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #10b981, #059669);
            transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 700; font-size: 13px;
            min-width: 40px;
        }
        .contributor-item {
            padding: 10px 14px;
            background: var(--bg);
            border-radius: 8px;
            margin-top: 6px;
            border-left: 3px solid var(--success);
            font-size: 14px;
        }

        /* === БОТ ПОДДЕРЖКИ === */
        .support-bot {
            position: fixed; bottom: 30px; right: 30px;
            width: 64px; height: 64px;
            background: linear-gradient(135deg, var(--primary), #a855f7);
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 32px;
            text-decoration: none;
            box-shadow: 0 10px 30px rgba(99, 102, 241, 0.4);
            z-index: 999;
            transition: all 0.3s;
            animation: botPulse 3s ease-in-out infinite;
        }
        .support-bot:hover { transform: scale(1.15) rotate(10deg); }

        /* === ДЕСКТОП: дизайнерская асимметричная сетка === */
        @media (min-width: 1024px) {
            .container { max-width: 1400px; padding: 40px; }
            .hero { padding: 100px 40px; border-radius: 40px; }
            .hero h1 { font-size: 72px; letter-spacing: -2px; }
            .grid-masonry {
                display: grid;
                grid-template-columns: 2fr 1fr 1fr;
                grid-template-rows: auto auto;
                gap: 30px;
                margin-bottom: 60px;
            }
            .grid-masonry > :nth-child(1) { grid-row: span 2; }
            .grid-masonry .card { border-radius: 24px; transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1); }
            .grid-masonry .card:hover { transform: translateY(-12px) rotate(-1deg); box-shadow: 0 30px 60px rgba(99, 102, 241, 0.2); }

            .stats-float { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }
            .stats-float .stat-card:nth-child(odd) { transform: translateY(-20px); }
            .stats-float .stat-card:nth-child(even) { transform: translateY(20px); }
            .stats-float .stat-card:hover { transform: translateY(0) scale(1.05); }

            .grid-2 { grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 30px; }
            .header { padding: 20px 40px; border-radius: 0 0 24px 24px; }
            .mb-4 { margin-bottom: 40px; }
            .card { padding: 40px; }
        }

        /* === ПЛАНШЕТЫ === */
        @media (min-width: 768px) and (max-width: 1023px) {
            .container { max-width: 900px; padding: 24px; }
            .grid-masonry { grid-template-columns: repeat(2, 1fr); }
            .grid-masonry > :nth-child(1) { grid-row: auto; }
            .stats-float { grid-template-columns: repeat(2, 1fr); }
            .stats-float .stat-card { transform: none; }
        }

        /* === МОБИЛЬНАЯ ВЕРСИЯ === */
        @media (max-width: 767px) {
            .container { padding: 16px; }
            .hero { padding: 40px 20px; border-radius: 20px; }
            .hero h1 { font-size: 32px; line-height: 1.2; }
            .hero p { font-size: 16px; }
            .grid, .grid-2, .grid-masonry { grid-template-columns: 1fr !important; gap: 16px; }
            .stats-float { grid-template-columns: repeat(2, 1fr) !important; gap: 12px; }
            .stats-float .stat-card { transform: none !important; padding: 16px; }
            .stat-number { font-size: 28px; }
            .btn { padding: 16px 24px; font-size: 16px; min-height: 56px; border-radius: 14px; }
            .btn-lg { padding: 20px 32px; font-size: 18px; }
            .btn-block { min-height: 60px; }
            .form-group input, .form-group textarea, .form-group select { padding: 16px; font-size: 16px; min-height: 56px; }
            .header { padding: 12px 16px; }
            .header-content { flex-direction: column; gap: 12px; }
            .nav { width: 100%; justify-content: center; }
            .nav a { padding: 10px 12px; font-size: 13px; }
            .card { padding: 20px; border-radius: 16px; }
            .item-card { border-radius: 16px; }
            .item-image { height: 180px; }
            .emoji-picker { grid-template-columns: repeat(6, 1fr); }
            .support-bot { width: 56px; height: 56px; bottom: 20px; right: 20px; font-size: 28px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <a href="/" class="logo"><span class="gift-box" style="font-size: 1.2em;">🎁</span><span>WishList Pro</span></a>
            <div class="nav">
                <a href="/">🏠 Главная</a>
                <a href="/ideas">💡 Идеи</a>
                {% if session.get("user_id") %}
                <a href="/dashboard">✨ Мои виши</a>
                <a href="/settings">⚙️</a>
                {% if session.get("is_admin") %}
                <a href="/admin" style="background: linear-gradient(135deg, #ec4899, #8b5cf6); color: white;">🔧 Админ</a>
                {% endif %}
                <a href="/logout">🚪 Выйти</a>
                {% else %}
                <a href="/login">🔑 Войти</a>
                <a href="/register" class="btn btn-sm">Регистрация</a>
                {% endif %}
            </div>
        </div>
    </div>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="alert alert-{{ "success" if category == "success" else "info" if category == "info" else "error" }}">
                    <span>{{ "✅" if category == "success" else "ℹ️" if category == "info" else "❌" }}</span>
                    <span>{{ message }}</span>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {{ content | safe }}
    </div>
    <a href="https://t.me/your_bot_username" target="_blank" class="support-bot" title="💬 Поддержка 24/7">💬</a>
    <div class="toast" id="toast"></div>
    <script>
        document.documentElement.setAttribute("data-theme", localStorage.getItem("theme") || "{{ theme }}");
        function showToast(message, type = "success") {
            const toast = document.getElementById("toast");
            toast.textContent = message;
            toast.className = "toast show";
            setTimeout(() => toast.classList.remove("show"), 3000);
        }
        function previewImage(input, previewId) {
            const preview = document.getElementById(previewId);
            if (input.value) preview.innerHTML = '<img src="' + input.value + '" onerror="this.parentElement.innerHTML=\'❌\'">';
        }
    </script>
</body>
</html>
'''

# ========== МАРШРУТЫ ==========
@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(days=30)

@app.route('/')
def index():
    theme = session.get('theme', 'light')
    conn, db_type = get_db()
    cur = conn.cursor()

    def get_count(q, params=()):
        cur.execute(q, params)
        r = cur.fetchone()
        return r['c'] if db_type == 'postgres' else r[0]

    users_count = get_count('SELECT COUNT(*) as c FROM users WHERE is_banned=0')
    wishes_count = get_count('SELECT COUNT(*) as c FROM wishlists')
    items_count = get_count('SELECT COUNT(*) as c FROM wishlist_items')
    ideas_count = get_count('SELECT COUNT(*) as c FROM ideas')
    cur.close(); conn.close()

    user_logged = session.get("user_id")
    hero_buttons = '<a href="/dashboard" class="btn btn-lg">✨ Мои виши</a><a href="/wishlist/new" class="btn btn-secondary btn-lg">➕ Создать виш</a>' if user_logged else '<a href="/register" class="btn btn-lg">🚀 Начать бесплатно</a><a href="/ideas" class="btn btn-secondary btn-lg">💡 Идеи подарков</a>'

    content = f'''
    <div class="hero">
        <div class="gift-box" style="font-size: 4em;">🎁</div>
        <h1 class="animate-fade">Создавай свои виши</h1>
        <p class="animate-fade" style="animation-delay: 0.2s;">Делись мечталками с друзьями и получай идеальные подарки</p>
        <div class="flex-center animate-fade" style="animation-delay: 0.4s;">{hero_buttons}</div>
    </div>
    <div class="grid-masonry">
        <div class="card text-center animate-slide"><div style="font-size: 72px; margin-bottom: 16px;" class="animate-float">📝</div><h3 style="font-size: 24px;">Создавай виши</h3><p style="color: var(--text-secondary); margin-top: 10px;">Собирай желания в красивые вишлисты с обложками и описаниями</p></div>
        <div class="card text-center animate-slide"><div style="font-size: 56px; margin-bottom: 12px;" class="animate-float">🔗</div><h3>Делись ссылкой</h3><p style="color: var(--text-secondary);">Красивые короткие ссылки</p></div>
        <div class="card text-center animate-slide"><div style="font-size: 56px; margin-bottom: 12px;" class="animate-float">🎉</div><h3>Получай подарки</h3><p style="color: var(--text-secondary);">Друзья бронируют и дарят</p></div>
        <div class="card text-center animate-slide"><div style="font-size: 56px; margin-bottom: 12px;" class="animate-float">🤫</div><h3>Секретные желания</h3><p style="color: var(--text-secondary);">Скрывай самое важное</p></div>
    </div>
    <div class="stats-float">
        <div class="stat-card animate-scale"><div class="stat-number">{users_count}</div><div class="stat-label">👥 Вишелюбов</div></div>
        <div class="stat-card animate-scale"><div class="stat-number">{wishes_count}</div><div class="stat-label">🎁 Вишей</div></div>
        <div class="stat-card animate-scale"><div class="stat-number">{items_count}</div><div class="stat-label">⭐ Желаний</div></div>
        <div class="stat-card animate-scale"><div class="stat-number">{ideas_count}</div><div class="stat-label">💡 Идей</div></div>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Главная', content=content)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        captcha_answer = request.form.get('captcha_answer', '').strip()
        correct_answer = session.get('captcha_answer')
        try:
            if not captcha_answer or int(captcha_answer) != correct_answer:
                flash('❌ Неверный ответ', 'error')
                return redirect(url_for('register'))
        except:
            flash('❌ Введите число', 'error')
            return redirect(url_for('register'))

        username = request.form['username'].strip()
        password = request.form['password']
        email = request.form.get('email', '').strip().lower()

        if len(username) < 3 or len(password) < 4:
            flash('Минимум 3 символа имени и 4 пароля', 'error')
            return redirect(url_for('register'))

        if email:
            is_valid, msg = validate_email_real(email)
            if not is_valid:
                flash(f'❌ {msg}', 'error')
                return redirect(url_for('register'))

        conn, db_type = get_db()
        cur = conn.cursor()
        p = ph(db_type)
        cur.execute(f'SELECT id FROM users WHERE username={p}', (username,))
        if cur.fetchone():
            cur.close(); conn.close()
            flash('Такой вишелюб уже существует', 'error')
            return redirect(url_for('register'))

        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        if db_type == 'postgres':
            cur.execute(f'INSERT INTO users (username, password, email, created_at, last_login, login_count) VALUES ({p},{p},{p},CURRENT_DATE,CURRENT_DATE,1) RETURNING id',
                        (username, hashed_pw, email))
            user_id = cur.fetchone()['id']
        else:
            cur.execute(f'INSERT INTO users (username, password, email, created_at, last_login, login_count) VALUES ({p},{p},{p},?,?,1)',
                        (username, hashed_pw, email, datetime.now().date(), datetime.now().date()))
            user_id = cur.lastrowid

        slug = slugify(f"{username}-main")
        if db_type == 'postgres':
            cur.execute(f'INSERT INTO wishlists (user_id, title, description, slug, is_default, created_at) VALUES ({p},{p},{p},{p},TRUE,CURRENT_DATE)',
                        (user_id, 'Мой первый виш', 'Главный вишлист', slug))
        else:
            cur.execute(f'INSERT INTO wishlists (user_id, title, description, slug, is_default, created_at) VALUES ({p},{p},{p},{p},1,?)',
                        (user_id, 'Мой первый виш', 'Главный вишлист', slug, datetime.now().date()))
        conn.commit()
        cur.close(); conn.close()
        flash('🎉 Добро пожаловать!', 'success')
        return redirect(url_for('login'))

    question, answer = generate_captcha()
    session['captcha_answer'] = answer
    theme = session.get('theme', 'light')
    content = f'''
    <div class="card animate-scale" style="max-width: 500px; margin: 40px auto;">
        <h2>🚀 Стать вишелюбом</h2>
        <form method="POST">
            <div class="form-group"><label>Имя *</label><input type="text" name="username" required minlength="3"></div>
            <div class="form-group"><label>Email</label><input type="email" name="email" placeholder="you@example.com"></div>
            <div class="form-group"><label>Пароль *</label><input type="password" name="password" required minlength="4"></div>
            <div class="captcha-box">
                <div class="captcha-question">{question} = ?</div>
                <input type="number" name="captcha_answer" required style="width: 150px; text-align: center;">
            </div>
            <button type="submit" class="btn btn-block btn-lg">Создать аккаунт</button>
        </form>
        <p style="margin-top: 20px; text-align: center;">Уже с нами? <a href="/login" style="color: var(--primary);">Войти</a></p>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Регистрация', content=content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        is_admin_login = request.form.get('admin_login') == '1'
        username = request.form['username']
        password = request.form['password']
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        conn, db_type = get_db()
        cur = conn.cursor()
        p = ph(db_type)
        if is_admin_login:
            cur.execute(f'SELECT * FROM users WHERE username={p} AND password={p} AND is_admin=1 AND is_banned=0', (username, hashed_pw))
            user = cur.fetchone()
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = as_bool(user['is_admin'])
                session['theme'] = user['theme']
                session['currency'] = user['currency']
                if db_type == 'postgres':
                    cur.execute(f'UPDATE users SET last_login=CURRENT_DATE, login_count=login_count+1 WHERE id={p}', (user['id'],))
                else:
                    cur.execute(f'UPDATE users SET last_login=?, login_count=login_count+1 WHERE id={p}', (datetime.now().date(), user['id']))
                conn.commit()
                cur.close(); conn.close()
                flash(f'👑 Добро пожаловать, админ {user["username"]}!', 'success')
                return redirect(url_for('admin'))
            else:
                cur.close(); conn.close()
                flash('🚫 Неверные данные администратора', 'error')
                return redirect(url_for('login'))
        else:
            cur.execute(f'SELECT * FROM users WHERE username={p} AND password={p}', (username, hashed_pw))
            user = cur.fetchone()
            if user and as_bool(user['is_banned']):
                cur.close(); conn.close()
                flash('🚫 Аккаунт заблокирован', 'error')
                return redirect(url_for('login'))
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = as_bool(user['is_admin'])
                session['theme'] = user['theme']
                session['currency'] = user['currency']
                if db_type == 'postgres':
                    cur.execute(f'UPDATE users SET last_login=CURRENT_DATE, login_count=login_count+1 WHERE id={p}', (user['id'],))
                else:
                    cur.execute(f'UPDATE users SET last_login=?, login_count=login_count+1 WHERE id={p}', (datetime.now().date(), user['id']))
                conn.commit()
                cur.close(); conn.close()
                flash(f'👋 С возвращением, {user["username"]}!', 'success')
                if as_bool(user['is_admin']):
                    return redirect(url_for('admin'))
                return redirect(url_for('dashboard'))
            else:
                cur.close(); conn.close()
                flash('Неверное имя или пароль', 'error')
    theme = session.get('theme', 'light')
    content = '''
    <div class="card animate-scale" style="max-width: 500px; margin: 40px auto;">
        <h2>🔑 Вход</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">С возвращением, вишелюб!</p>
        <form method="POST" id="loginForm">
            <input type="hidden" name="admin_login" id="adminLoginFlag" value="0">
            <div class="form-group"><label>Имя</label><input type="text" name="username" required></div>
            <div class="form-group"><label>Пароль</label><input type="password" name="password" required></div>
            <div id="adminPanel" style="display: none; margin-top: 20px; padding: 20px; background: linear-gradient(135deg, rgba(236, 72, 153, 0.1), rgba(139, 92, 246, 0.1)); border: 2px dashed #ec4899; border-radius: 12px;">
                <div style="text-align: center;"><div style="font-size: 36px;" class="animate-bounce">👑</div><h3 style="color: #ec4899;">Режим администратора</h3></div>
            </div>
            <button type="submit" class="btn btn-block btn-lg">Войти</button>
        </form>
        <div style="margin-top: 20px; text-align: center;">
            <span id="keyIcon" style="cursor: pointer; font-size: 20px; transition: transform 0.2s;">🔑</span>
            <span id="clickCounter" style="margin-left: 8px; opacity: 0.5;"></span>
        </div>
        <p style="margin-top: 12px; text-align: center;"><a href="/forgot-password" style="color: var(--primary); font-size: 14px;">🔐 Забыли пароль?</a></p>
        <p style="margin-top: 20px; text-align: center;">Ещё не с нами? <a href="/register" style="color: var(--primary);">Регистрация</a></p>
    </div>
    <script>
        (function() {
            let clickCount = 0;
            const keyIcon = document.getElementById('keyIcon');
            const adminPanel = document.getElementById('adminPanel');
            const counter = document.getElementById('clickCounter');
            const adminFlag = document.getElementById('adminLoginFlag');
            let resetTimer = null;
            keyIcon.addEventListener('click', function() {
                clickCount++;
                keyIcon.style.transform = 'rotate(' + (clickCount * 72) + 'deg) scale(1.3)';
                setTimeout(() => keyIcon.style.transform = 'rotate(' + (clickCount * 72) + 'deg) scale(1)', 150);
                if (clickCount >= 3) { counter.textContent = clickCount + '/5'; counter.style.opacity = '1'; counter.style.color = '#ec4899'; counter.style.fontWeight = 'bold'; }
                if (clickCount >= 5) {
                    adminPanel.style.display = 'block';
                    adminFlag.value = '1';
                    counter.textContent = '✨ Режим админа активирован!';
                    counter.style.color = '#10b981';
                    keyIcon.style.transform = 'rotate(360deg) scale(1.2)';
                    document.querySelector('h2').innerHTML = '👑 Вход администратора';
                    keyIcon.style.pointerEvents = 'none';
                }
                clearTimeout(resetTimer);
                resetTimer = setTimeout(() => { if (clickCount < 5) { clickCount = 0; counter.textContent = ''; counter.style.opacity = '0.5'; keyIcon.style.transform = 'rotate(0deg) scale(1)'; } }, 3000);
            });
            keyIcon.addEventListener('mousedown', (e) => e.preventDefault());
        })();
    </script>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Вход', content=content)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        is_valid, msg = validate_email_real(email)
        if not is_valid:
            flash(f'❌ {msg}', 'error')
            return redirect(url_for('forgot_password'))

        conn, db_type = get_db()
        cur = conn.cursor()
        p = ph(db_type)
        cur.execute(f'SELECT * FROM users WHERE LOWER(email) = {p}', (email,))
        user = cur.fetchone()

        if not user:
            flash('✅ Если email зарегистрирован — письмо отправлено', 'success')
            cur.close(); conn.close()
            return redirect(url_for('login'))

        import secrets
        token = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(hours=1)

        if db_type == 'postgres':
            cur.execute(f'INSERT INTO password_resets (user_id, token, expires_at, used) VALUES ({p},{p},{p},FALSE)',
                        (user['id'], token, expires))
        else:
            cur.execute(f'INSERT INTO password_resets (user_id, token, expires_at, used) VALUES ({p},{p},{p},0)',
                        (user['id'], token, expires.isoformat()))
        conn.commit()
        cur.close(); conn.close()

        reset_url = f"{BASE_URL}/reset-password/{token}"
        html = f'''
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #6366f1;">🔐 Восстановление пароля WishList Pro</h2>
            <p>Привет, <b>{user['username']}</b>!</p>
            <p>Ты запросил сброс пароля. Нажми на кнопку ниже:</p>
            <a href="{reset_url}" style="display: inline-block; padding: 14px 28px; background: #6366f1; color: white; text-decoration: none; border-radius: 10px; margin: 20px 0;">Сбросить пароль</a>
            <p style="color: #6b7280; font-size: 14px;">Ссылка действует 1 час.</p>
        </div>
        '''
        if send_email(email, '🔐 Сброс пароля WishList Pro', html):
            flash('✅ Письмо со ссылкой отправлено на email', 'success')
        else:
            flash('⚠️ Не удалось отправить письмо (SMTP не настроен). Обратись к админу.', 'error')
        return redirect(url_for('login'))

    content = '''
    <div class="card animate-scale" style="max-width: 500px; margin: 40px auto;">
        <h2>🔐 Восстановление пароля</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">Введи email, привязанный к аккаунту</p>
        <form method="POST">
            <div class="form-group"><label>Email</label><input type="email" name="email" required></div>
            <button type="submit" class="btn btn-block btn-lg">Отправить ссылку</button>
        </form>
        <p style="margin-top: 20px; text-align: center;"><a href="/login" style="color: var(--primary);">← Вернуться ко входу</a></p>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=session.get('theme', 'light'), title='Восстановление', content=content)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM password_resets WHERE token = {p}', (token,))
    reset = cur.fetchone()

    if not reset or as_bool(reset['used']):
        cur.close(); conn.close()
        flash('❌ Ссылка недействительна или уже использована', 'error')
        return redirect(url_for('forgot_password'))

    expires = reset['expires_at']
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if datetime.now() > expires:
        cur.close(); conn.close()
        flash('⏰ Ссылка истекла', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        if len(new_password) < 4:
            flash('Минимум 4 символа', 'error')
            return redirect(url_for('reset_password', token=token))
        hashed = hashlib.sha256(new_password.encode()).hexdigest()
        cur.execute(f'UPDATE users SET password = {p} WHERE id = {p}', (hashed, reset['user_id']))
        if db_type == 'postgres':
            cur.execute(f'UPDATE password_resets SET used = TRUE WHERE token = {p}', (token,))
        else:
            cur.execute(f'UPDATE password_resets SET used = 1 WHERE token = {p}', (token,))
        conn.commit()
        cur.close(); conn.close()
        flash('✅ Пароль изменён!', 'success')
        return redirect(url_for('login'))

    cur.close(); conn.close()
    content = '''
    <div class="card animate-scale" style="max-width: 500px; margin: 40px auto;">
        <h2>🔑 Новый пароль</h2>
        <form method="POST">
            <div class="form-group"><label>Новый пароль *</label><input type="password" name="password" required minlength="4"></div>
            <button type="submit" class="btn btn-block btn-lg">Сохранить пароль</button>
        </form>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=session.get('theme', 'light'), title='Новый пароль', content=content)

@app.route('/logout')
def logout():
    session.clear()
    flash('👋 Ты вышел!', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    user_id = session['user_id']
    theme = session.get('theme', 'light')
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'''SELECT w.*,
                    (SELECT COUNT(*) FROM wishlist_items WHERE wishlist_id=w.id) as items_count,
                    (SELECT COUNT(*) FROM wishlist_items WHERE wishlist_id=w.id AND (reserved_by IS NOT NULL OR guest_name IS NOT NULL)) as reserved_count
                    FROM wishlists w WHERE w.user_id = {p} ORDER BY w.is_default DESC, w.created_at DESC''', (user_id,))
    wishlists = cur.fetchall()
    cur.close(); conn.close()

    if not wishlists:
        content = '<div class="empty-state animate-scale"><div class="empty-state-icon">🎁</div><h2>У тебя пока нет вишей</h2><p style="color: var(--text-secondary); margin-bottom: 24px;">Создай первый!</p><a href="/wishlist/new" class="btn btn-lg">✨ Создать первый виш</a></div>'
    else:
        wishes_html = ''
        for w in wishlists:
            items_count = int(w['items_count'] or 0)
            reserved_count = int(w['reserved_count'] or 0)
            progress = int((reserved_count / items_count * 100)) if items_count > 0 else 0
            default_badge = '<span class="badge badge-primary">⭐ Главный</span>' if as_bool(w['is_default']) else ''
            wishes_html += f'''
            <a href="/w/{w['slug']}" class="wish-card" style="text-decoration: none; color: inherit;">
                <span class="wish-card-emoji">{w['cover_emoji'] or '🎁'}</span>
                <div class="wish-card-title">{w['title']}</div>
                <div class="wish-card-meta"><span>🎯 {items_count}</span><span>✅ {reserved_count}</span>{default_badge}</div>
                <div class="collective-progress"><div class="collective-progress-bar" style="width: {progress}%;">{progress}%</div></div>
            </a>
            '''
        content = f'''
        <div class="flex-between mb-4">
            <div><h1>✨ Мои виши</h1><p style="color: var(--text-secondary);">Всего: {len(wishlists)}</p></div>
            <a href="/wishlist/new" class="btn">➕ Новый виш</a>
        </div>
        <div class="grid-2">{wishes_html}</div>
        '''
    return render_template_string(HTML_BASE, theme=theme, title='Мои виши', content=content)

@app.route('/wishlist/new', methods=['GET', 'POST'])
def new_wishlist():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title'].strip()
        if not title:
            flash('Введите название', 'error')
            return redirect(url_for('new_wishlist'))
        slug = slugify(title)
        conn, db_type = get_db()
        cur = conn.cursor()
        p = ph(db_type)
        is_public = 1 if request.form.get('is_public') else 0
        if db_type == 'postgres':
            cur.execute(f'INSERT INTO wishlists (user_id, title, description, slug, is_public, cover_emoji, created_at) VALUES ({p},{p},{p},{p},{p},{p},CURRENT_DATE)',
                        (session['user_id'], title, request.form.get('description', ''), slug, is_public, request.form.get('cover_emoji', '🎁')))
        else:
            cur.execute(f'INSERT INTO wishlists (user_id, title, description, slug, is_public, cover_emoji, created_at) VALUES ({p},{p},{p},{p},{p},{p},?)',
                        (session['user_id'], title, request.form.get('description', ''), slug, is_public, request.form.get('cover_emoji', '🎁'), datetime.now().date()))
        conn.commit()
        cur.close(); conn.close()
        flash(f'🎉 Виш "{title}" создан!', 'success')
        return redirect(url_for('view_wishlist', slug=slug))

    theme = session.get('theme', 'light')
    emojis = ['🎁', '🎂', '🎄', '💝', '🎓', '👰', '🏠', '🚗', '✈️', '💻', '📱', '🎮', '📚', '🎨', '⚽', '🎵', '💎', '🌹', '🍰', '🎈']
    emoji_html = ''.join([f'<div class="emoji-option" onclick="selectEmoji(this, \'{e}\')">{e}</div>' for e in emojis])
    content = f'''
    <div class="card animate-scale" style="max-width: 600px; margin: 0 auto;">
        <h2>✨ Новый виш</h2>
        <form method="POST">
            <div class="form-group"><label>Название *</label><input type="text" name="title" required maxlength="50"></div>
            <div class="form-group"><label>Описание</label><textarea name="description" rows="3"></textarea></div>
            <div class="form-group"><label>Обложка</label><div class="emoji-picker">{emoji_html}</div><input type="hidden" name="cover_emoji" id="coverEmoji" value="🎁"></div>
            <div class="form-group"><label style="display: flex; align-items: center; gap: 8px;"><input type="checkbox" name="is_public" value="1" checked style="width: auto;"><span>Публичный</span></label></div>
            <div class="flex"><button type="submit" class="btn" style="flex: 1;">✨ Создать</button><a href="/dashboard" class="btn btn-secondary" style="flex: 1;">Отмена</a></div>
        </form>
    </div>
    <script>function selectEmoji(el, emoji) {{ document.querySelectorAll(".emoji-option").forEach(e => e.classList.remove("selected")); el.classList.add("selected"); document.getElementById("coverEmoji").value = emoji; }} document.querySelector(".emoji-option").classList.add("selected");</script>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Новый виш', content=content)

@app.route('/w/<slug>')
def view_wishlist(slug):
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM wishlists WHERE slug={p}', (slug,))
    wishlist = cur.fetchone()
    if not wishlist:
        cur.close(); conn.close()
        flash('Виш не найден', 'error')
        return redirect(url_for('index'))
    cur.execute(f'SELECT * FROM users WHERE id={p}', (wishlist['user_id'],))
    user = cur.fetchone()
    current_user_id = session.get('user_id')
    if not as_bool(wishlist['is_public']) and current_user_id != wishlist['user_id'] and not session.get('is_admin'):
        cur.close(); conn.close()
        flash('Виш приватный', 'error')
        return redirect(url_for('index'))
    cur.execute(f'SELECT i.*, u.username as reserved_by_name FROM wishlist_items i LEFT JOIN users u ON i.reserved_by = u.id WHERE i.wishlist_id = {p} ORDER BY i.priority DESC, i.created_at DESC', (wishlist['id'],))
    items = cur.fetchall()
    cur.close(); conn.close()
    is_owner = current_user_id == wishlist['user_id']
    user_currency = session.get('currency', user['currency'] or 'BYN')

    items_html = ''
    if items:
        for item in items:
            is_secret = as_bool(item.get('is_secret'))
            is_collective = as_bool(item.get('is_collective'))
            is_reserved = item['reserved_by'] is not None or item['guest_name']
            secret_class = 'secret-item' if (is_secret and not is_owner) else ''

            # Для секретных желаний не показываем детали другим
            if is_secret and not is_owner and not is_reserved:
                items_html += f'''
                <div class="item-card {secret_class}">
                    <div class="item-image">🎁<div class="secret-overlay">🤫</div></div>
                    <div class="item-content">
                        <h3 class="item-title">Секретное желание <span class="badge badge-secret">🤫 Скрыто</span></h3>
                        <p class="item-description">Забронируй — и узнаешь что это!</p>
                        <a href="/reserve/{item['id']}" class="btn btn-success btn-block">🎯 Забронировать вслепую</a>
                    </div>
                </div>
                '''
                continue

            # Конвертация цены
            raw_price = item['price']
            item_currency = item['currency'] or 'BYN'
            if raw_price:
                converted = convert_price(raw_price, item_currency, user_currency)
                price_html = f'<div class="item-price">💰 {format_price(converted, user_currency)}</div>'
            else:
                price_html = ''

            link_html = f'<a href="{item["link"]}" target="_blank" class="btn btn-secondary btn-sm">🔗 Купить</a>' if item['link'] else ''
            img_html = f'<img src="{item["image_url"]}" alt="{item["title"]}" onerror="this.parentElement.innerHTML=\'🎁\'">' if item['image_url'] else '🎁'

            badges = ''
            if is_secret: badges += '<span class="badge badge-secret">🤫 Секрет</span> '
            if is_collective: badges += '<span class="badge badge-collective">💰 Коллективный</span> '

            # Статус брони
            reserve_html = ''
            if item['reserved_by']:
                if item['reserved_by'] == current_user_id:
                    reserve_html = f'<span class="badge badge-success">✓ Вы забрали</span><a href="/unreserve/{item["id"]}" class="btn btn-secondary btn-sm" style="margin-top: 8px; display: block;">↩️ Отменить</a>'
                else:
                    name = item['reserved_by_name'] or 'Кто-то'
                    reserve_html = f'<span class="badge badge-warning">🔒 Забрал {name}</span>'
            elif item['guest_name']:
                reserve_html = f'<span class="badge badge-warning">🔒 Забронировал: {item["guest_name"]}</span>'
            elif current_user_id and current_user_id != wishlist['user_id']:
                reserve_html = f'<a href="/reserve/{item["id"]}" class="btn btn-success btn-block">🎯 Забрать</a>'
            elif not current_user_id:
                reserve_html = f'<a href="/reserve/{item["id"]}" class="btn btn-success btn-block">🎯 Забронировать</a>'

            # Коллективный подарок — прогресс
            collective_html = ''
            if is_collective and item.get('goal_amount'):
                conn2, dt2 = get_db()
                cur2 = conn2.cursor()
                cur2.execute(f'SELECT COALESCE(SUM(amount), 0) as total FROM contributions WHERE item_id = {p}', (item['id'],))
                r = cur2.fetchone()
                collected = float(r['total'] if dt2 == 'postgres' else r[0])
                cur2.execute(f'SELECT guest_name, amount, created_at FROM contributions WHERE item_id = {p} ORDER BY created_at DESC', (item['id'],))
                contribs = cur2.fetchall()
                cur2.close(); conn2.close()
                goal = float(item['goal_amount'])
                progress = int((collected / goal * 100)) if goal > 0 else 0
                contribs_html = ''
                if contribs:
                    contribs_html = '<div style="margin-top: 10px; font-size: 13px;"><b>Участники:</b>'
                    for c in contribs:
                        nm = c['guest_name'] if dt2 == 'postgres' else c[0]
                        am = c['amount'] if dt2 == 'postgres' else c[1]
                        contribs_html += f'<div class="contributor-item"><b>{nm}</b> — {format_price(am, item_currency)}</div>'
                    contribs_html += '</div>'
               # Выносим кнопку в отдельную переменную (избегаем ! в f-string)
                contribute_btn = ""
                if not reserve_html and not is_owner:
                    item_id = item['id']
                    contribute_btn = f'<a href="/reserve/{item_id}" class="btn btn-success btn-block" style="margin-top: 10px;">💰 Внести свой вклад</a>'
                
                collective_html = f'''
                <div style="margin: 12px 0;">
                    <div class="flex-between" style="font-size: 13px; margin-bottom: 4px;">
                        <span>Собрано: <b>{format_price(collected, item_currency)}</b></span>
                        <span>Цель: <b>{format_price(goal, item_currency)}</b></span>
                    </div>
                    <div class="collective-progress"><div class="collective-progress-bar" style="width: {min(progress, 100)}%;">{progress}%</div></div>
                    {contribs_html}
                    {contribute_btn}
                </div>
                '''

            owner_actions = ''
            if is_owner:
                owner_actions = f'<div style="margin-top: 10px; display: flex; gap: 6px;"><a href="/item/{item["id"]}/edit" class="btn btn-secondary btn-sm" style="flex: 1;">✏️</a><a href="/item/{item["id"]}/delete" class="btn btn-danger btn-sm" style="flex: 1;" onclick="return confirm(\'Удалить?\')">🗑️</a></div>'

            items_html += f'''
            <div class="item-card {secret_class}">
                <div class="item-image">{img_html}</div>
                <div class="item-content">
                    <h3 class="item-title">{item["title"]} {badges}</h3>
                    {price_html}
                    {f'<p class="item-description">{item["description"]}</p>' if item["description"] else ""}
                    {link_html}
                    {collective_html}
                    <div style="margin-top: 12px;">{reserve_html}</div>
                    {owner_actions}
                </div>
            </div>
            '''
    else:
        if is_owner:
            items_html = f'<div class="empty-state" style="grid-column: 1/-1;"><div class="empty-state-icon">🎁</div><h3>Виш пустой</h3><p style="color: var(--text-secondary); margin: 12px 0 20px;">Добавь желание!</p><a href="/w/{slug}/add" class="btn">➕ Добавить</a><a href="/ideas" class="btn btn-secondary" style="margin-left: 10px;">💡 Из идей</a></div>'
        else:
            items_html = '<div class="empty-state" style="grid-column: 1/-1;"><div class="empty-state-icon">🤷</div><h3>Пока пусто</h3></div>'

    owner_actions_html = ''
    if is_owner:
        owner_actions_html = f'''
        <div class="flex" style="margin-top: 16px; justify-content: center; flex-wrap: wrap;">
            <a href="/w/{slug}/add" class="btn">➕ Добавить</a>
            <a href="/w/{slug}/edit" class="btn btn-secondary">✏️ Редактировать</a>
            <button onclick="navigator.clipboard.writeText('{BASE_URL}/w/{slug}').then(() => showToast('📋 Скопировано!'))" class="btn btn-secondary">📋 Копировать</button>
            <a href="/w/{slug}/delete" class="btn btn-danger" onclick="return confirm('Удалить виш?')">🗑️</a>
        </div>
        '''

    content = f'''
    <div class="card text-center animate-scale" style="margin-bottom: 30px;">
        <div style="font-size: 72px; margin-bottom: 12px;" class="animate-float">{wishlist['cover_emoji'] or '🎁'}</div>
        <h1 style="font-size: 36px; margin-bottom: 8px;">{wishlist['title']}</h1>
        {f'<p style="color: var(--text-secondary); margin-bottom: 12px;">{wishlist["description"]}</p>' if wishlist['description'] else ''}
        <p style="color: var(--text-secondary);">👤 {user['username']} • 🎯 {len(items)} желаний</p>
        <div style="margin-top: 12px; font-size: 13px;">🔗 <code style="background: var(--bg); padding: 4px 10px; border-radius: 6px;">{BASE_URL}/w/{slug}</code></div>
        {owner_actions_html}
    </div>
    <div class="grid">{items_html}</div>
    '''
    return render_template_string(HTML_BASE, theme=user['theme'] or 'light', title=f'{wishlist["title"]} • Виш', content=content)

@app.route('/w/<slug>/add', methods=['GET', 'POST'])
def add_to_wishlist(slug):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM wishlists WHERE slug={p} AND user_id={p}', (slug, session['user_id']))
    wishlist = cur.fetchone()
    if not wishlist:
        cur.close(); conn.close()
        flash('Виш не найден', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title = request.form['title'].strip()
        if not title:
            cur.close(); conn.close()
            flash('Введите название', 'error')
            return redirect(url_for('add_to_wishlist', slug=slug))

        price = float(request.form['price']) if request.form.get('price') else None
        is_secret = 1 if request.form.get('is_secret') else 0
        is_collective = 1 if request.form.get('is_collective') else 0
        goal_amount = float(request.form['goal_amount']) if request.form.get('goal_amount') else None

        if db_type == 'postgres':
            cur.execute(f'''INSERT INTO wishlist_items
                (wishlist_id, title, description, link, price, currency, image_url, priority, is_secret, is_collective, goal_amount, created_at)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},CURRENT_DATE)''',
                (wishlist['id'], title, request.form.get('description', ''), request.form.get('link', ''),
                 price, request.form.get('currency', session.get('currency', 'BYN')),
                 request.form.get('image_url', ''), int(request.form.get('priority', 0)),
                 is_secret, is_collective, goal_amount))
        else:
            cur.execute(f'''INSERT INTO wishlist_items
                (wishlist_id, title, description, link, price, currency, image_url, priority, is_secret, is_collective, goal_amount, created_at)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},?)''',
                (wishlist['id'], title, request.form.get('description', ''), request.form.get('link', ''),
                 price, request.form.get('currency', session.get('currency', 'BYN')),
                 request.form.get('image_url', ''), int(request.form.get('priority', 0)),
                 is_secret, is_collective, goal_amount, datetime.now().date()))
        conn.commit()
        cur.close(); conn.close()
        flash('✨ Добавлено в виш!', 'success')
        return redirect(url_for('view_wishlist', slug=slug))

    cur.close(); conn.close()
    theme = session.get('theme', 'light')
    currency_options = ''.join([f'<option value="{code}" {"selected" if code == session.get("currency", "BYN") else ""}>{name}</option>' for code, name in CURRENCIES.items()])
    content = f'''
    <div class="card animate-scale" style="max-width: 650px; margin: 0 auto;">
        <h2>➕ Новое желание</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">В виш: <b>{wishlist['title']}</b></p>
        <form method="POST">
            <div class="form-group"><label>Название *</label><input type="text" name="title" required></div>
            <div class="form-group"><label>Описание</label><textarea name="description" rows="2"></textarea></div>
            <div class="flex" style="gap: 12px;">
                <div class="form-group" style="flex: 1;"><label>Цена</label><input type="number" name="price" step="0.01"></div>
                <div class="form-group" style="flex: 1;"><label>Валюта</label><select name="currency">{currency_options}</select></div>
            </div>
            <div class="form-group"><label>🔗 Ссылка</label><input type="url" name="link"></div>
            <div class="form-group"><label>🖼️ URL картинки</label><input type="url" name="image_url" oninput="previewImage(this, 'imgPreview')"><div class="image-preview" id="imgPreview">🖼️ Превью</div></div>
            <div class="form-group"><label>⭐ Приоритет (0-10)</label><input type="number" name="priority" min="0" max="10" value="0"></div>
            <div class="form-group"><label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="checkbox" name="is_secret" value="1" style="width: auto;">
                <span>🤫 Секретное желание (скрыто от других)</span>
            </label></div>
            <div class="form-group"><label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="checkbox" name="is_collective" value="1" style="width: auto;" id="collectiveCheck" onchange="document.getElementById('goalField').style.display=this.checked?'block':'none'">
                <span>💰 Коллективный подарок (можно скинуться)</span>
            </label></div>
            <div class="form-group" id="goalField" style="display: none;">
                <label>Цель сбора (сумма)</label>
                <input type="number" name="goal_amount" step="0.01" placeholder="Например: 500">
            </div>
            <div class="flex"><button type="submit" class="btn" style="flex: 1;">✨ Добавить</button><a href="/w/{slug}" class="btn btn-secondary" style="flex: 1;">Отмена</a></div>
        </form>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Добавить желание', content=content)

@app.route('/w/<slug>/edit', methods=['GET', 'POST'])
def edit_wishlist(slug):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM wishlists WHERE slug={p} AND user_id={p}', (slug, session['user_id']))
    wishlist = cur.fetchone()
    if not wishlist:
        cur.close(); conn.close()
        flash('Виш не найден', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        is_public = 1 if request.form.get('is_public') else 0
        cur.execute(f'UPDATE wishlists SET title={p}, description={p}, cover_emoji={p}, is_public={p} WHERE id={p}',
                    (request.form['title'], request.form.get('description', ''), request.form.get('cover_emoji', '🎁'), is_public, wishlist['id']))
        conn.commit()
        cur.close(); conn.close()
        flash('✅ Виш обновлён!', 'success')
        return redirect(url_for('view_wishlist', slug=slug))

    cur.close(); conn.close()
    theme = session.get('theme', 'light')
    emojis = ['🎁', '🎂', '🎄', '💝', '🎓', '👰', '🏠', '🚗', '✈️', '💻', '📱', '🎮', '📚', '🎨', '⚽', '🎵', '💎', '🌹', '🍰', '🎈']
    emoji_html = ''.join([f'<div class="emoji-option {"selected" if e == wishlist["cover_emoji"] else ""}" onclick="selectEmoji(this, \'{e}\')">{e}</div>' for e in emojis])
    content = f'''
    <div class="card animate-scale" style="max-width: 600px; margin: 0 auto;">
        <h2>✏️ Редактировать виш</h2>
        <form method="POST">
            <div class="form-group"><label>Название</label><input type="text" name="title" required value="{wishlist['title']}"></div>
            <div class="form-group"><label>Описание</label><textarea name="description" rows="3">{wishlist['description'] or ''}</textarea></div>
            <div class="form-group"><label>Обложка</label><div class="emoji-picker">{emoji_html}</div><input type="hidden" name="cover_emoji" id="coverEmoji" value="{wishlist['cover_emoji'] or '🎁'}"></div>
            <div class="form-group"><label style="display: flex; align-items: center; gap: 8px;"><input type="checkbox" name="is_public" value="1" {"checked" if as_bool(wishlist['is_public']) else ""} style="width: auto;"><span>Публичный</span></label></div>
            <div class="flex"><button type="submit" class="btn" style="flex: 1;">💾 Сохранить</button><a href="/w/{slug}" class="btn btn-secondary" style="flex: 1;">Отмена</a></div>
        </form>
    </div>
    <script>function selectEmoji(el, emoji) {{ document.querySelectorAll(".emoji-option").forEach(e => e.classList.remove("selected")); el.classList.add("selected"); document.getElementById("coverEmoji").value = emoji; }}</script>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Редактировать виш', content=content)

@app.route('/w/<slug>/delete')
def delete_wishlist(slug):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM wishlists WHERE slug={p} AND user_id={p}', (slug, session['user_id']))
    wishlist = cur.fetchone()
    if wishlist:
        cur.execute(f'DELETE FROM contributions WHERE item_id IN (SELECT id FROM wishlist_items WHERE wishlist_id={p})', (wishlist['id'],))
        cur.execute(f'DELETE FROM reservations WHERE item_id IN (SELECT id FROM wishlist_items WHERE wishlist_id={p})', (wishlist['id'],))
        cur.execute(f'DELETE FROM wishlist_items WHERE wishlist_id={p}', (wishlist['id'],))
        cur.execute(f'DELETE FROM wishlists WHERE id={p}', (wishlist['id'],))
        conn.commit()
        flash('🗑️ Виш удалён', 'success')
    cur.close(); conn.close()
    return redirect(url_for('dashboard'))

@app.route('/item/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_item(item_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT i.*, w.user_id, w.slug FROM wishlist_items i JOIN wishlists w ON i.wishlist_id=w.id WHERE i.id={p}', (item_id,))
    item = cur.fetchone()
    if not item or item['user_id'] != session['user_id']:
        cur.close(); conn.close()
        flash('Нет доступа', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        price = float(request.form['price']) if request.form.get('price') else None
        is_secret = 1 if request.form.get('is_secret') else 0
        is_collective = 1 if request.form.get('is_collective') else 0
        goal_amount = float(request.form['goal_amount']) if request.form.get('goal_amount') else None
        cur.execute(f'''UPDATE wishlist_items SET title={p}, description={p}, link={p}, price={p}, currency={p}, image_url={p}, priority={p}, is_secret={p}, is_collective={p}, goal_amount={p} WHERE id={p}''',
                    (request.form['title'], request.form.get('description', ''), request.form.get('link', ''),
                     price, request.form.get('currency', 'BYN'), request.form.get('image_url', ''),
                     int(request.form.get('priority', 0)), is_secret, is_collective, goal_amount, item_id))
        conn.commit()
        cur.close(); conn.close()
        flash('✅ Обновлено!', 'success')
        return redirect(url_for('view_wishlist', slug=item['slug']))

    cur.close(); conn.close()
    theme = session.get('theme', 'light')
    currency_options = ''.join([f'<option value="{code}" {"selected" if code == (item["currency"] or session.get("currency", "BYN")) else ""}>{name}</option>' for code, name in CURRENCIES.items()])
    content = f'''
    <div class="card animate-scale" style="max-width: 650px; margin: 0 auto;">
        <h2>✏️ Редактировать</h2>
        <form method="POST">
            <div class="form-group"><label>Название</label><input type="text" name="title" required value="{item['title']}"></div>
            <div class="form-group"><label>Описание</label><textarea name="description" rows="2">{item['description'] or ''}</textarea></div>
            <div class="flex" style="gap: 12px;">
                <div class="form-group" style="flex: 1;"><label>Цена</label><input type="number" name="price" step="0.01" value="{item['price'] or ''}"></div>
                <div class="form-group" style="flex: 1;"><label>Валюта</label><select name="currency">{currency_options}</select></div>
            </div>
            <div class="form-group"><label>Ссылка</label><input type="url" name="link" value="{item['link'] or ''}"></div>
            <div class="form-group"><label>URL картинки</label><input type="url" name="image_url" value="{item['image_url'] or ''}" oninput="previewImage(this, 'imgPreview')"><div class="image-preview" id="imgPreview">{f'<img src="{item["image_url"]}">' if item['image_url'] else '🖼️ Превью'}</div></div>
            <div class="form-group"><label>Приоритет</label><input type="number" name="priority" min="0" max="10" value="{item['priority'] or 0}"></div>
            <div class="form-group"><label style="display: flex; align-items: center; gap: 8px;">
                <input type="checkbox" name="is_secret" value="1" {"checked" if as_bool(item.get("is_secret")) else ""} style="width: auto;">
                <span>🤫 Секретное</span>
            </label></div>
            <div class="form-group"><label style="display: flex; align-items: center; gap: 8px;">
                <input type="checkbox" name="is_collective" value="1" {"checked" if as_bool(item.get("is_collective")) else ""} style="width: auto;" id="collectiveCheck" onchange="document.getElementById('goalField').style.display=this.checked?'block':'none'">
                <span>💰 Коллективный</span>
            </label></div>
            <div class="form-group" id="goalField" style="display: {"block" if as_bool(item.get("is_collective")) else "none"};">
                <label>Цель сбора</label>
                <input type="number" name="goal_amount" step="0.01" value="{item['goal_amount'] or ''}">
            </div>
            <div class="flex"><button type="submit" class="btn" style="flex: 1;">💾 Сохранить</button><a href="/w/{item['slug']}" class="btn btn-secondary" style="flex: 1;">Отмена</a></div>
        </form>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Редактировать', content=content)

@app.route('/item/<int:item_id>/delete')
def delete_item(item_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT i.wishlist_id, w.slug, w.user_id FROM wishlist_items i JOIN wishlists w ON i.wishlist_id=w.id WHERE i.id={p}', (item_id,))
    item = cur.fetchone()
    if item and item['user_id'] == session['user_id']:
        cur.execute(f'DELETE FROM contributions WHERE item_id={p}', (item_id,))
        cur.execute(f'DELETE FROM reservations WHERE item_id={p}', (item_id,))
        cur.execute(f'DELETE FROM wishlist_items WHERE id={p}', (item_id,))
        conn.commit()
        flash('🗑️ Удалено', 'success')
        slug = item['slug']
    else:
        slug = None
    cur.close(); conn.close()
    return redirect(url_for('view_wishlist', slug=slug) if slug else url_for('dashboard'))

@app.route('/reserve/<int:item_id>', methods=['GET', 'POST'])
def reserve(item_id):
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM wishlist_items WHERE id = {p}', (item_id,))
    item = cur.fetchone()
    if not item:
        cur.close(); conn.close()
        flash('Подарок не найден', 'error')
        return redirect(url_for('index'))

    cur.execute(f'SELECT slug FROM wishlists WHERE id = {p}', (item['wishlist_id'],))
    wishlist = cur.fetchone()
    slug = wishlist['slug'] if wishlist else None

    # Залогиненный пользователь — обычная бронь
    if session.get('user_id'):
        if item['reserved_by'] or item['guest_name']:
            cur.close(); conn.close()
            flash('Уже забронировано', 'error')
            return redirect(url_for('view_wishlist', slug=slug))
        cur.execute(f'UPDATE wishlist_items SET reserved_by = {p} WHERE id = {p}', (session['user_id'], item_id))
        if db_type == 'postgres':
            cur.execute(f'INSERT INTO reservations (item_id, reserved_by, reserved_at) VALUES ({p},{p},CURRENT_DATE)', (item_id, session['user_id']))
        else:
            cur.execute(f'INSERT INTO reservations (item_id, reserved_by, reserved_at) VALUES ({p},{p},?)', (item_id, session['user_id'], datetime.now().date()))
        conn.commit()
        cur.close(); conn.close()
        flash('🎯 Забронировано!', 'success')
        return redirect(url_for('view_wishlist', slug=slug))

    # ГОСТЕВАЯ БРОНЬ
    if request.method == 'POST':
        guest_name = request.form.get('guest_name', '').strip()
        guest_email = request.form.get('guest_email', '').strip()

        if not guest_name or len(guest_name) < 2:
            flash('❌ Введите имя (минимум 2 символа)', 'error')
            return redirect(url_for('reserve', item_id=item_id))

        if guest_email:
            is_valid, msg = validate_email_real(guest_email)
            if not is_valid:
                flash(f'❌ {msg}', 'error')
                return redirect(url_for('reserve', item_id=item_id))

        # Коллективный подарок
        if as_bool(item.get('is_collective')) and item.get('goal_amount'):
            amount = float(request.form.get('amount', 0))
            if amount <= 0:
                flash('❌ Укажи сумму взноса', 'error')
                return redirect(url_for('reserve', item_id=item_id))
            if db_type == 'postgres':
                cur.execute(f'INSERT INTO contributions (item_id, guest_name, amount, created_at) VALUES ({p},{p},{p},CURRENT_DATE)', (item_id, guest_name, amount))
            else:
                cur.execute(f'INSERT INTO contributions (item_id, guest_name, amount, created_at) VALUES ({p},{p},{p},?)', (item_id, guest_name, amount, datetime.now().date()))
            conn.commit()
            cur.close(); conn.close()
            flash(f'💰 Спасибо, {guest_name}! Взнос записан', 'success')
            return redirect(url_for('view_wishlist', slug=slug))

        # Обычная гостевая бронь
        if item['reserved_by'] or item['guest_name']:
            cur.close(); conn.close()
            flash('Уже забронировано', 'error')
            return redirect(url_for('view_wishlist', slug=slug))

        cur.execute(f'UPDATE wishlist_items SET guest_name = {p}, guest_email = {p} WHERE id = {p}', (guest_name, guest_email, item_id))
        conn.commit()
        cur.close(); conn.close()
        flash(f'🎉 Спасибо, {guest_name}! Бронь принята', 'success')
        return redirect(url_for('view_wishlist', slug=slug))

    cur.close(); conn.close()

    is_collective = as_bool(item.get('is_collective')) and item.get('goal_amount')
    collected = 0
    contributors = []
    if is_collective:
        conn2, dt2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute(f'SELECT SUM(amount) as total FROM contributions WHERE item_id = {p}', (item_id,))
        r = cur2.fetchone()
        collected = float(r['total'] or 0) if dt2 == 'postgres' else (r[0] or 0)
        cur2.execute(f'SELECT guest_name, amount, created_at FROM contributions WHERE item_id = {p} ORDER BY created_at DESC', (item_id,))
        contributors = cur2.fetchall()
        cur2.close(); conn2.close()

    goal = float(item['goal_amount'] or 0)
    progress = int((collected / goal * 100)) if goal > 0 else 0

    contributors_html = ''
    if contributors:
        contributors_html = '<div style="margin-top: 20px;"><h4>👥 Уже внесли:</h4>'
        for c in contributors:
            nm = c['guest_name'] if db_type == 'postgres' else c[0]
            am = c['amount'] if db_type == 'postgres' else c[1]
            contributors_html += f'<div class="contributor-item"><b>{nm}</b> — {format_price(am, item["currency"] or "BYN")}</div>'
        contributors_html += '</div>'

    content = f'''
    <div class="card animate-scale" style="max-width: 500px; margin: 40px auto;">
        <h2>{"💰 Коллективный подарок" if is_collective else "🎁 Забронировать подарок"}</h2>
        <p style="color: var(--text-secondary); margin-bottom: 20px;"><b>{item['title']}</b><br>{"Без регистрации — укажи имя" if not is_collective else "Скинься вместе с друзьями!"}</p>
        {f'''
        <div class="collective-progress"><div class="collective-progress-bar" style="width: {min(progress, 100)}%;">{progress}%</div></div>
        <p style="text-align: center; margin: 10px 0;">Собрано: <b>{format_price(collected, item["currency"] or "BYN")}</b> / {format_price(goal, item["currency"] or "BYN")}</p>
        {contributors_html}
        ''' if is_collective else ''}
        <form method="POST" style="margin-top: 20px;">
            <div class="form-group"><label>Твоё имя *</label><input type="text" name="guest_name" required minlength="2" placeholder="Как тебя зовут?"></div>
            <div class="form-group"><label>Email (необязательно)</label><input type="email" name="guest_email" placeholder="Для уведомлений"></div>
            {"<div class='form-group'><label>Сумма взноса *</label><input type='number' name='amount' step='0.01' min='1' required placeholder='Сколько внести?'></div>" if is_collective else ""}
            <button type="submit" class="btn btn-block btn-lg">{"💰 Внести" if is_collective else "🎯 Забронировать"}</button>
        </form>
        <p style="margin-top: 20px; text-align: center;"><a href="/login" style="color: var(--primary);">Войти как зарегистрированный</a></p>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=session.get('theme', 'light'), title='Бронирование', content=content)

@app.route('/unreserve/<int:item_id>')
def unreserve(item_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM wishlist_items WHERE id = {p}', (item_id,))
    item = cur.fetchone()
    if not item:
        cur.close(); conn.close()
        return redirect(url_for('index'))
    cur.execute(f'SELECT slug FROM wishlists WHERE id = {p}', (item['wishlist_id'],))
    wishlist = cur.fetchone()
    slug = wishlist['slug'] if wishlist else None
    cur.execute(f'UPDATE wishlist_items SET reserved_by=NULL WHERE id={p} AND reserved_by={p}', (item_id, session['user_id']))
    cur.execute(f'DELETE FROM reservations WHERE item_id={p} AND reserved_by={p}', (item_id, session['user_id']))
    conn.commit()
    cur.close(); conn.close()
    flash('↩️ Бронь снята', 'success')
    return redirect(url_for('view_wishlist', slug=slug) if slug else url_for('index'))

@app.route('/ideas')
def ideas():
    theme = session.get('theme', 'light')
    user_currency = session.get('currency', 'BYN')
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    category = request.args.get('category', '')
    search = request.args.get('search', '').strip()
    if category:
        cur.execute(f'SELECT * FROM ideas WHERE category={p} ORDER BY created_at DESC', (category,))
    elif search:
        cur.execute(f"SELECT * FROM ideas WHERE title LIKE {p} ORDER BY created_at DESC", (f'%{search}%',))
    else:
        cur.execute('SELECT * FROM ideas ORDER BY created_at DESC')
    ideas = cur.fetchall()
    cur.execute('SELECT DISTINCT category FROM ideas WHERE category IS NOT NULL')
    categories = cur.fetchall()
    cur.close(); conn.close()

    category_buttons = ''.join([f'<a href="/ideas?category={cat["category"]}" class="btn btn-sm {"btn-success" if category == cat["category"] else "btn-secondary"}">{cat["category"]}</a>' for cat in categories])
    ideas_html = ''
    for idea in ideas:
        raw_price = idea['price']
        item_currency = idea['currency'] or 'BYN'
        if raw_price:
            converted = convert_price(raw_price, item_currency, user_currency)
            price_html = f'<div class="item-price">💰 {format_price(converted, user_currency)}</div>'
        else:
            price_html = ''
        link_html = f'<a href="{idea["link"]}" target="_blank" class="btn btn-secondary btn-sm">🔗</a>' if idea['link'] else ''
        img_html = f'<img src="{idea["image_url"]}" alt="{idea["title"]}" onerror="this.parentElement.innerHTML=\'🎁\'">' if idea['image_url'] else '🎁'
        add_btn = f'<a href="/add_item_from_idea/{idea["id"]}" class="btn btn-block">➕ В мой виш</a>' if session.get('user_id') else '<a href="/login" class="btn btn-secondary btn-block">Войти</a>'
        ideas_html += f'''
        <div class="item-card">
            <div class="item-image">{img_html}</div>
            <div class="item-content">
                <h3 class="item-title">{idea["title"]}</h3>
                {price_html}
                <p class="item-description">{idea["description"]}</p>
                {link_html}
                <div style="margin-top: 10px;">{add_btn}</div>
            </div>
        </div>
        '''
    content = f'''
    <div class="flex-between mb-4"><div><h1>💡 Идеи подарков</h1><p style="color: var(--text-secondary);">Готовые идеи для вишей</p></div></div>
    <div class="card" style="margin-bottom: 20px;">
        <form method="GET" class="flex">
            <input type="search" name="search" placeholder="🔍 Поиск..." value="{search}" style="flex: 1;">
            <button type="submit" class="btn">Найти</button>
            <a href="/ideas" class="btn btn-secondary">✖️</a>
        </form>
    </div>
    <div class="flex mb-4" style="flex-wrap: wrap; gap: 8px;">
        <a href="/ideas" class="btn btn-sm {"btn-success" if not category else "btn-secondary"}">🌟 Все</a>
        {category_buttons}
    </div>
    <div class="grid">{ideas_html}</div>
    '''
    return render_template_string(HTML_BASE, theme=theme, title='Идеи', content=content)

@app.route('/add_item_from_idea/<int:idea_id>')
def add_from_idea(idea_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM ideas WHERE id={p}', (idea_id,))
    idea = cur.fetchone()
    if idea:
        cur.execute(f'SELECT id FROM wishlists WHERE user_id={p} ORDER BY is_default DESC, id ASC LIMIT 1', (session['user_id'],))
        wishlist = cur.fetchone()
        if not wishlist:
            slug = slugify(f"{session['username']}-main")
            if db_type == 'postgres':
                cur.execute(f'INSERT INTO wishlists (user_id, title, slug, is_default, created_at) VALUES ({p},{p},{p},TRUE,CURRENT_DATE)', (session['user_id'], 'Мой виш', slug))
            else:
                cur.execute(f'INSERT INTO wishlists (user_id, title, slug, is_default, created_at) VALUES ({p},{p},{p},1,?)', (session['user_id'], 'Мой виш', slug, datetime.now().date()))
            conn.commit()
            cur.execute(f'SELECT id FROM wishlists WHERE user_id={p} ORDER BY is_default DESC LIMIT 1', (session['user_id'],))
            wishlist = cur.fetchone()
        if db_type == 'postgres':
            cur.execute(f'INSERT INTO wishlist_items (wishlist_id, title, description, link, price, currency, image_url, created_at) VALUES ({p},{p},{p},{p},{p},{p},{p},CURRENT_DATE)',
                        (wishlist['id'], idea['title'], idea['description'], idea['link'], idea['price'], idea['currency'], idea['image_url']))
        else:
            cur.execute(f'INSERT INTO wishlist_items (wishlist_id, title, description, link, price, currency, image_url, created_at) VALUES ({p},{p},{p},{p},{p},{p},{p},?)',
                        (wishlist['id'], idea['title'], idea['description'], idea['link'], idea['price'], idea['currency'], idea['image_url'], datetime.now().date()))
        conn.commit()
        flash('✨ Добавлено в виш!', 'success')
    cur.close(); conn.close()
    return redirect(url_for('ideas'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        conn, db_type = get_db()
        cur = conn.cursor()
        p = ph(db_type)
        if action == 'save':
            theme = request.form['theme']
            currency = request.form['currency']
            cur.execute(f'UPDATE users SET theme={p}, currency={p} WHERE id={p}', (theme, currency, session['user_id']))
            conn.commit()
            session['theme'] = theme
            session['currency'] = currency
            flash('💾 Сохранено!', 'success')
        elif action == 'save_email':
            email = request.form.get('email', '').strip().lower()
            if email:
                is_valid, msg = validate_email_real(email)
                if not is_valid:
                    flash(f'❌ {msg}', 'error')
                    cur.close(); conn.close()
                    return redirect(url_for('settings'))
            cur.execute(f'UPDATE users SET email={p} WHERE id={p}', (email, session['user_id']))
            conn.commit()
            flash('💾 Email сохранён!', 'success')
        elif action == 'change_password':
            old_password = request.form.get('old_password', '')
            new_password = request.form.get('new_password', '')
            if len(new_password) < 4:
                flash('Минимум 4 символа', 'error')
                cur.close(); conn.close()
                return redirect(url_for('settings'))
            cur.execute(f'SELECT password FROM users WHERE id={p}', (session['user_id'],))
            user = cur.fetchone()
            if user['password'] != hashlib.sha256(old_password.encode()).hexdigest():
                flash('❌ Неверный пароль', 'error')
                cur.close(); conn.close()
                return redirect(url_for('settings'))
            cur.execute(f'UPDATE users SET password={p} WHERE id={p}', (hashlib.sha256(new_password.encode()).hexdigest(), session['user_id']))
            conn.commit()
            flash('🔐 Пароль изменён!', 'success')
        cur.close(); conn.close()
        return redirect(url_for('settings'))

    user_theme = session.get('theme', 'light')
    user_currency = session.get('currency', 'BYN')
    theme_options = ''.join([f'<option value="{code}" {"selected" if code == user_theme else ""}>{name}</option>' for code, name in THEMES.items()])
    currency_options = ''.join([f'<option value="{code}" {"selected" if code == user_currency else ""}>{name}</option>' for code, name in CURRENCIES.items()])
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM users WHERE id={p}', (session['user_id'],))
    user = cur.fetchone()
    wishlists_count = cur.execute(f'SELECT COUNT(*) as c FROM wishlists WHERE user_id={p}', (session['user_id'],)).fetchone()
    wc = wishlists_count['c'] if db_type == 'postgres' else wishlists_count[0]
    items_count = cur.execute(f'SELECT COUNT(*) as c FROM wishlist_items i JOIN wishlists w ON i.wishlist_id=w.id WHERE w.user_id={p}', (session['user_id'],)).fetchone()
    ic = items_count['c'] if db_type == 'postgres' else items_count[0]
    cur.close(); conn.close()

    content = f'''
    <h1>⚙️ Настройки</h1>
    <div class="grid-2">
        <div class="card animate-slide">
            <h2>🎨 Оформление</h2>
            <form method="POST"><input type="hidden" name="action" value="save">
                <div class="form-group"><label>Тема</label><select name="theme">{theme_options}</select></div>
                <div class="form-group"><label>Валюта</label><select name="currency">{currency_options}</select></div>
                <button type="submit" class="btn btn-block">💾 Сохранить</button>
            </form>
        </div>
        <div class="card animate-slide">
            <h2>👤 Профиль</h2>
            <p><b>Имя:</b> {session['username']}</p>
            <p><b>Вишей:</b> {wc} | <b>Желаний:</b> {ic}</p>
        </div>
        <div class="card animate-slide">
            <h2>📧 Email</h2>
            <form method="POST"><input type="hidden" name="action" value="save_email">
                <div class="form-group"><label>Email</label><input type="email" name="email" value="{user['email'] or ''}" placeholder="you@example.com"></div>
                <button type="submit" class="btn btn-block">💾 Сохранить</button>
            </form>
            <p style="margin-top: 10px; font-size: 12px; color: var(--text-secondary);">Нужен для восстановления пароля</p>
        </div>
        <div class="card animate-slide">
            <h2>🔐 Сменить пароль</h2>
            <form method="POST"><input type="hidden" name="action" value="change_password">
                <div class="form-group"><label>Текущий пароль</label><input type="password" name="old_password" required></div>
                <div class="form-group"><label>Новый пароль</label><input type="password" name="new_password" required minlength="4"></div>
                <button type="submit" class="btn btn-block">Сменить</button>
            </form>
        </div>
    </div>
    '''
    return render_template_string(HTML_BASE, theme=user_theme, title='Настройки', content=content)

@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    def get_count(query, params=()):
        cur.execute(query, params)
        r = cur.fetchone()
        return r['c'] if db_type == 'postgres' else r[0]
    users_count = get_count('SELECT COUNT(*) as c FROM users')
    wishlists_count = get_count('SELECT COUNT(*) as c FROM wishlists')
    items_count = get_count('SELECT COUNT(*) as c FROM wishlist_items')
    ideas_count = get_count('SELECT COUNT(*) as c FROM ideas')
    reservations_count = get_count('SELECT COUNT(*) as c FROM reservations')
    cur.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 5')
    recent_users = cur.fetchall()
    cur.close(); conn.close()
    recent_html = ''.join([f'<tr><td>{u["id"]}</td><td><b>{u["username"]}</b></td><td>{u["email"] or "-"}</td><td>{u["created_at"]}</td><td>{"🚫" if as_bool(u["is_banned"]) else "✅"}</td></tr>' for u in recent_users])
    content = f'''
    <div class="flex-between mb-4"><h1>🔧 Админ-панель</h1><p style="color: var(--text-secondary);">Привет, {session['username']}!</p></div>
    <div class="grid" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));">
        <div class="stat-card"><div style="font-size: 32px;">👥</div><div class="stat-number">{users_count}</div><div class="stat-label">Пользователей</div></div>
        <div class="stat-card"><div style="font-size: 32px;">🎁</div><div class="stat-number">{wishlists_count}</div><div class="stat-label">Вишей</div></div>
        <div class="stat-card"><div style="font-size: 32px;">⭐</div><div class="stat-number">{items_count}</div><div class="stat-label">Желаний</div></div>
        <div class="stat-card"><div style="font-size: 32px;">💡</div><div class="stat-number">{ideas_count}</div><div class="stat-label">Идей</div></div>
        <div class="stat-card"><div style="font-size: 32px;">🎯</div><div class="stat-number">{reservations_count}</div><div class="stat-label">Броней</div></div>
    </div>
    <div class="flex" style="margin: 20px 0; gap: 10px;"><a href="/admin/users" class="btn">👥 Пользователи</a></div>
    <div class="card"><h2>👥 Последние пользователи</h2><table><thead><tr><th>ID</th><th>Имя</th><th>Email</th><th>Дата</th><th>Статус</th></tr></thead><tbody>{recent_html}</tbody></table></div>
    '''
    return render_template_string(HTML_BASE, theme=session.get('theme', 'dark'), title='Админка', content=content)

@app.route('/admin/users')
def admin_users():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    conn, db_type = get_db()
    cur = conn.cursor()
    cur.execute('''SELECT u.*, (SELECT COUNT(*) FROM wishlists WHERE user_id=u.id) as wishlists_count,
                   (SELECT COUNT(*) FROM wishlist_items i JOIN wishlists w ON i.wishlist_id=w.id WHERE w.user_id=u.id) as items_count
                   FROM users u ORDER BY u.created_at DESC''')
    users = cur.fetchall()
    cur.close(); conn.close()
    users_html = ''.join([f'''
    <tr>
        <td>{u["id"]}</td><td><b>{u["username"]}</b></td><td>{u["email"] or '-'}</td><td>{u["created_at"]}</td>
        <td>{u["login_count"]}</td><td>{u["wishlists_count"]}</td><td>{u["items_count"]}</td>
        <td>{"<span class='badge badge-danger'>🚫 Бан</span>" if as_bool(u["is_banned"]) else "<span class='badge badge-success'>✅ OK</span>"}{"<span class='badge badge-primary'>⚡</span>" if as_bool(u["is_admin"]) else ""}</td>
        <td><a href="/admin/user/{u["id"]}/toggle_ban" class="btn btn-sm {"btn-success" if as_bool(u["is_banned"]) else "btn-warning"}">{"✅ Разбан" if as_bool(u["is_banned"]) else "🚫 Бан"}</a></td>
    </tr>
    ''' for u in users])
    content = f'''
    <div class="flex-between mb-4"><h1>👥 Пользователи ({len(users)})</h1><a href="/admin" class="btn btn-secondary">← Назад</a></div>
    <div class="card"><table><thead><tr><th>ID</th><th>Имя</th><th>Email</th><th>Рег.</th><th>Входов</th><th>Вишей</th><th>Желаний</th><th>Статус</th><th>Действия</th></tr></thead><tbody>{users_html}</tbody></table></div>
    '''
    return render_template_string(HTML_BASE, theme=session.get('theme', 'dark'), title='Пользователи', content=content)

@app.route('/admin/user/<int:user_id>/toggle_ban')
def admin_toggle_ban(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    if user_id == session['user_id']:
        flash('Нельзя забанить себя!', 'error')
        return redirect(url_for('admin_users'))
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM users WHERE id={p}', (user_id,))
    user = cur.fetchone()
    if user:
        new_status = 0 if as_bool(user['is_banned']) else 1
        cur.execute(f'UPDATE users SET is_banned={p} WHERE id={p}', (new_status, user_id))
        conn.commit()
        flash(f'{"✅ Разбанен" if new_status == 0 else "🚫 Забанен"}: {user["username"]}', 'success')
    cur.close(); conn.close()
    return redirect(url_for('admin_users'))

@app.route('/u/<username>')
def public_wishlist(username):
    conn, db_type = get_db()
    cur = conn.cursor()
    p = ph(db_type)
    cur.execute(f'SELECT * FROM users WHERE username={p}', (username,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        flash('Пользователь не найден', 'error')
        return redirect(url_for('index'))
    cur.execute(f'SELECT slug FROM wishlists WHERE user_id={p} AND is_public=1 ORDER BY is_default DESC LIMIT 1', (user['id'],))
    wishlist = cur.fetchone()
    cur.close(); conn.close()
    if wishlist:
        return redirect(url_for('view_wishlist', slug=wishlist['slug']))
    flash('Нет публичных вишей', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    print(f'✅ WishList Pro запущен!')
    print(f'🌐 URL: {BASE_URL}')
    print(f'👤 Админ: {ADMIN_USERNAME} / {ADMIN_PASSWORD}')
    print(f'🗄️ БД: {"PostgreSQL" if os.getenv("DATABASE_URL") else "SQLite"}')
    app.run(host='0.0.0.0', port=PORT, debug=False)
