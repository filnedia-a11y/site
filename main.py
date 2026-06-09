import os, sqlite3, hashlib, random, re
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
# ========== ГЛОБАЛЬНАЯ НАСТРОЙКА БД ==========
# Делает все соединения sqlite3 "умными":
# row[0] и row['column_name'] работают одновременно!
_original_sqlite_connect = sqlite3.connect

def _smart_connect(*args, **kwargs):
    conn = _original_sqlite_connect(*args, **kwargs)
    conn.row_factory = sqlite3.Row  # ← ВОТ ОНА, МАГИЯ!
    return conn

sqlite3.connect = _smart_connect
# ==============================================
# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('wishlist.db')
    c = conn.cursor()
    
    # Создаём таблицы (если их ещё нет)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT,
        theme TEXT DEFAULT 'light',
        currency TEXT DEFAULT 'BYN',
        created_at DATE,
        is_admin INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        last_login DATE,
        login_count INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS wishlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        description TEXT,
        slug TEXT UNIQUE,
        is_default INTEGER DEFAULT 0,
        is_public INTEGER DEFAULT 1,
        cover_emoji TEXT DEFAULT '🎁',
        created_at DATE,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS wishlist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wishlist_id INTEGER,
        title TEXT,
        description TEXT,
        link TEXT,
        price REAL,
        currency TEXT,
        image_url TEXT,
        status TEXT DEFAULT 'active',
        reserved_by INTEGER,
        priority INTEGER DEFAULT 0,
        created_at DATE,
        FOREIGN KEY (wishlist_id) REFERENCES wishlists(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        price REAL,
        currency TEXT,
        image_url TEXT,
        link TEXT,
        category TEXT,
        source TEXT DEFAULT 'manual',
        added_by INTEGER,
        created_at DATE
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS wb_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        price REAL,
        currency TEXT,
        image_url TEXT,
        link TEXT,
        category TEXT,
        wb_id TEXT,
        created_at DATE
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        reserved_by INTEGER,
        reserved_at DATE,
        FOREIGN KEY (item_id) REFERENCES wishlist_items(id)
    )''')
    
    # 🔄 АВТОМАТИЧЕСКИЕ МИГРАЦИИ — добавляем недостающие колонки
    def add_column_if_not_exists(table, column, definition):
        c.execute(f"PRAGMA table_info({table})")
        existing_columns = [row[1] for row in c.fetchall()]
        if column not in existing_columns:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                print(f"✅ Добавлена колонка {column} в таблицу {table}")
            except Exception as e:
                print(f"⚠️ Не удалось добавить {column}: {e}")
    
    # Применяем миграции к таблице users
    add_column_if_not_exists('users', 'is_admin', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('users', 'is_banned', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('users', 'last_login', 'DATE')
    add_column_if_not_exists('users', 'login_count', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('users', 'theme', 'TEXT DEFAULT "light"')
    add_column_if_not_exists('users', 'currency', 'TEXT DEFAULT "BYN"')
    add_column_if_not_exists('users', 'email', 'TEXT')
    
    # Миграции для wishlists
    add_column_if_not_exists('wishlists', 'slug', 'TEXT')
    add_column_if_not_exists('wishlists', 'is_default', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('wishlists', 'is_public', 'INTEGER DEFAULT 1')
    add_column_if_not_exists('wishlists', 'cover_emoji', 'TEXT DEFAULT "🎁"')
    
    # Миграции для wishlist_items
    add_column_if_not_exists('wishlist_items', 'image_url', 'TEXT')
    add_column_if_not_exists('wishlist_items', 'priority', 'INTEGER DEFAULT 0')
    add_column_if_not_exists('wishlist_items', 'reserved_by', 'INTEGER')
    
    # Миграции для ideas
    add_column_if_not_exists('ideas', 'image_url', 'TEXT')
    add_column_if_not_exists('ideas', 'category', 'TEXT')
    add_column_if_not_exists('ideas', 'source', 'TEXT DEFAULT "manual"')
    
    # Создаём админа если его нет
    c.execute('SELECT * FROM users WHERE username=?', (ADMIN_USERNAME,))
    if not c.fetchone():
        hashed_pw = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
        c.execute('''INSERT INTO users (username, password, is_admin, created_at, last_login, login_count) 
                     VALUES (?, ?, 1, ?, ?, 0)''',
                 (ADMIN_USERNAME, hashed_pw, datetime.now().date(), datetime.now().date()))
        print(f"👤 Админ создан: {ADMIN_USERNAME}")
    
    conn.commit()
    conn.close()
    
# ========== РУЧНЫЕ ИДЕИ ==========
def add_manual_ideas():
    conn = sqlite3.connect('wishlist.db')
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM ideas WHERE source="manual"')
    if c.fetchone()[0] > 0:
        conn.close()
        return
    
    ideas_data = [
        # 🎁 ПОДАРОЧНЫЕ КАРТЫ И СЕРТИФИКАТЫ
        ("Подарочная карта Starbucks", "Универсальный подарок для кофемана", 50, "BYN", "", "", "Подарочные карты"),
        ("Сертификат в SPA", "День релакса и красоты", 100, "BYN", "", "", "Впечатления"),
        ("Сертификат в магазин косметики", "Любимая косметика", 80, "BYN", "", "", "Подарочные карты"),
        ("Сертификат в книжный магазин", "Выбор любимой книги", 40, "BYN", "", "", "Подарочные карты"),
        ("Сертификат в магазин одежды", "Шопинг мечты", 150, "BYN", "", "", "Подарочные карты"),
        ("Подарочная карта iTunes", "Музыка, фильмы, приложения", 60, "BYN", "", "", "Подарочные карты"),
        ("Сертификат Ozon", "Любой товар с доставкой", 100, "BYN", "", "", "Подарочные карты"),
        ("Сертификат Wildberries", "Миллионы товаров", 100, "BYN", "", "", "Подарочные карты"),
        
        # 🎭 ВПЕЧАТЛЕНИЯ
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
        ("Поход в аквапарк", "День водных развлечений", 60, "BYN", "", "", "Впечатления"),
        ("Картинг", "Скорость и адреналин", 50, "BYN", "", "", "Впечатления"),
        ("Боулинг с друзьями", "Веселая компания", 30, "BYN", "", "", "Впечатления"),
        ("Пейнтбол", "Командная игра", 45, "BYN", "", "", "Впечатления"),
        ("Лазертаг", "Футуристическая битва", 40, "BYN", "", "", "Впечатления"),
        ("Верховая езда", "Прогулка на лошадях", 70, "BYN", "", "", "Впечатления"),
        ("Дайвинг", "Подводный мир", 150, "BYN", "", "", "Впечатления"),
        ("Полет в аэротрубе", "Ощущение свободного падения", 120, "BYN", "", "", "Впечатления"),
        ("Мастер-класс по гончарному делу", "Создай свою вазу", 50, "BYN", "", "", "Впечатления"),
        ("Урок рисования", "Раскрой творческий потенциал", 40, "BYN", "", "", "Впечатления"),
        ("Дегустация вин", "Изысканный вечер", 90, "BYN", "", "", "Впечатления"),
        ("Экскурсия по городу", "Узнай историю", 30, "BYN", "", "", "Впечатления"),
        
        # 💻 ПОДПИСКИ
        ("Подписка Netflix", "Год безлимитного кино", 80, "BYN", "", "", "Подписки"),
        ("Подписка Spotify", "Год любимой музыки", 50, "BYN", "", "", "Подписки"),
        ("Подписка Яндекс.Плюс", "Музыка, кино, книги", 60, "BYN", "", "", "Подписки"),
        ("Подписка ChatGPT Plus", "ИИ помощник на год", 150, "BYN", "", "", "Подписки"),
        ("Подписка YouTube Premium", "Без рекламы + музыка", 70, "BYN", "", "", "Подписки"),
        ("Подписка Apple Music", "Миллионы треков", 60, "BYN", "", "", "Подписки"),
        ("Подписка Adobe Creative Cloud", "Все программы Adobe", 400, "BYN", "", "", "Подписки"),
        ("Подписка Microsoft 365", "Office на год", 120, "BYN", "", "", "Подписки"),
        ("Подписка Disney+", "Фильмы Disney и Marvel", 70, "BYN", "", "", "Подписки"),
        ("Подписка HBO Max", "Сериалы и фильмы", 80, "BYN", "", "", "Подписки"),
        ("Подписка Twitch", "Стримы и эмодзи", 50, "BYN", "", "", "Подписки"),
        ("Подписка Xbox Game Pass", "Сотни игр", 100, "BYN", "", "", "Подписки"),
        
        # 🎨 КАСТОМ
        ("Кастомные кроссовки", "Уникальная роспись", 150, "BYN", "", "", "Кастом"),
        ("Портрет на заказ", "Картина по фото", 100, "BYN", "", "", "Кастом"),
        ("Именная кружка", "Персонализированный подарок", 20, "BYN", "", "", "Кастом"),
        ("Гравировка на кольце", "Памятная надпись", 50, "BYN", "", "", "Кастом"),
        ("Фотокнига", "Альбом с лучшими моментами", 40, "BYN", "", "", "Кастом"),
        ("Видео-поздравление", "Монтаж от друзей", 30, "BYN", "", "", "Кастом"),
        ("Песня на заказ", "Персональная композиция", 80, "BYN", "", "", "Кастом"),
        ("Стихотворение на заказ", "Персональные строки", 50, "BYN", "", "", "Кастом"),
        ("Именной халат", "С вышивкой имени", 60, "BYN", "", "", "Кастом"),
        ("Персонализированный планер", "С именем на обложке", 25, "BYN", "", "", "Кастом"),
        ("Чехол для телефона на заказ", "С твоим дизайном", 30, "BYN", "", "", "Кастом"),
        ("Звездная карта", "Небо в важный день", 45, "BYN", "", "", "Кастом"),
        ("Постер с цитатой", "Любимая фраза", 25, "BYN", "", "", "Кастом"),
        ("Магниты с фото", "Набор 10 штук", 20, "BYN", "", "", "Кастом"),
        ("Пазл с фото", "1000 деталей", 40, "BYN", "", "", "Кастом"),
        
        # 🌱 БЛАГОТВОРИТЕЛЬНОСТЬ
        ("Донат в любимый фонд", "Благотворительный подарок", 50, "BYN", "", "", "Благотворительность"),
        ("Посадить дерево", "Экологичный подарок", 30, "BYN", "", "", "Благотворительность"),
        ("Помощь приюту для животных", "Корм и лекарства", 40, "BYN", "", "", "Благотворительность"),
        ("Поддержка детского дома", "Игрушки и книги", 60, "BYN", "", "", "Благотворительность"),
        ("Пожертвование в больницу", "На лечение", 100, "BYN", "", "", "Благотворительность"),
        ("Стипендия студенту", "Поддержка образования", 200, "BYN", "", "", "Благотворительность"),
        
        # 🍽 ЕДА И НАПИТКИ
        ("Коробка элитного чая", "10 видов со всего мира", 60, "BYN", "", "", "Еда"),
        ("Набор шоколада ручной работы", "Бельгийский шоколад", 50, "BYN", "", "", "Еда"),
        ("Кофейный набор", "Зерна из Эфиопии + френч-пресс", 80, "BYN", "", "", "Еда"),
        ("Сырная тарелка", "5 видов сыра + мед", 70, "BYN", "", "", "Еда"),
        ("Набор специй", "30 специй со всего мира", 45, "BYN", "", "", "Еда"),
        ("Корзина экзотических фруктов", "Манго, маракуйя, драконфрукт", 60, "BYN", "", "", "Еда"),
        ("Винный набор", "3 бутылки + бокалы", 150, "BYN", "", "", "Еда"),
        ("Коробка макарун", "12 штук, разные вкусы", 35, "BYN", "", "", "Еда"),
        ("Медовый набор", "5 видов меда", 40, "BYN", "", "", "Еда"),
        ("Корзина итальянских продуктов", "Паста, оливки, соусы", 90, "BYN", "", "", "Еда"),
        
        # 🎓 ОБРАЗОВАНИЕ
        ("Онлайн-курс программирования", "Python для начинающих", 200, "BYN", "", "", "Образование"),
        ("Курс английского языка", "3 месяца занятий", 300, "BYN", "", "", "Образование"),
        ("Мастер-класс по фотографии", "От новичка до профи", 100, "BYN", "", "", "Образование"),
        ("Курс дизайна интерьеров", "Создай дом мечты", 150, "BYN", "", "", "Образование"),
        ("Уроки игры на гитаре", "10 занятий", 200, "BYN", "", "", "Образование"),
        ("Курс по кулинарии", "50 рецептов от шефа", 80, "BYN", "", "", "Образование"),
        ("Книга по саморазвитию", "Бестселлер года", 30, "BYN", "", "", "Образование"),
        ("Подписка на Skillbox", "Год обучения", 400, "BYN", "", "", "Образование"),
        
        # 💆 ЗДОРОВЬЕ И КРАСОТА
        ("Массаж всего тела", "60 минут релакса", 70, "BYN", "", "", "Красота"),
        ("Маникюр + педикюр", "Полный уход", 50, "BYN", "", "", "Красота"),
        ("Стрижка + укладка", "В топовом салоне", 60, "BYN", "", "", "Красота"),
        ("Набор корейской косметики", "10-ступенчатый уход", 120, "BYN", "", "", "Красота"),
        ("Парфюм нишевый", "Уникальный аромат", 250, "BYN", "", "", "Красота"),
        ("Набор для бровей", "Полный уход", 40, "BYN", "", "", "Красота"),
        ("SPA-день", "Полный комплекс процедур", 200, "BYN", "", "", "Красота"),
        ("Курс йоги", "12 занятий", 150, "BYN", "", "", "Красота"),
        ("Абонемент в бассейн", "Месяц безлимита", 80, "BYN", "", "", "Красота"),
        ("Персональный тренер", "10 тренировок", 300, "BYN", "", "", "Красота"),
    ]
    
    for idea in ideas_data:
        c.execute('''INSERT INTO ideas (title, description, price, currency, image_url, link, category, source, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', ?)''', (*idea, datetime.now().date()))
    
    conn.commit()
    conn.close()
    print(f"✅ Добавлено {len(ideas_data)} идей!")

# ========== УТИЛИТЫ ==========
def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = text.strip('-')
    if not text:
        text = 'wish'
    suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=5))
    return f"{text}-{suffix}"

def generate_captcha():
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    ops = [('+', num1 + num2), ('-', num1 - num2), ('*', num1 * num2)]
    op, answer = random.choice(ops)
    question = f"{num1} {op} {num2}"
    return question, answer

CURRENCIES = {
    'BYN': '🇧🇾 BYN', 'USD': '🇺🇸 USD', 'EUR': '🇪🇺 EUR',
    'RUB': '🇷🇺 RUB', 'KZT': '🇰🇿 KZT', 'PLN': '🇵🇱 PLN'
}

THEMES = {
    'light': '☀️ Светлая', 'dark': '🌙 Тёмная', 'blue': '💙 Синяя',
    'green': '💚 Зелёная', 'purple': '💜 Фиолетовая', 'orange': '🧡 Оранжевая',
    'pink': '💗 Розовая', 'gradient': '🌈 Градиент'
}

# ========== HTML ШАБЛОН ==========
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
        }
        [data-theme="dark"] {
            --bg: #0f172a; --card: #1e293b; --text: #f1f5f9; --text-secondary: #94a3b8;
            --primary: #818cf8; --primary-hover: #6366f1; --border: #334155;
        }
        [data-theme="blue"] { --primary: #0ea5e9; --primary-hover: #0284c7; }
        [data-theme="green"] { --primary: #22c55e; --primary-hover: #16a34a; }
        [data-theme="purple"] { --primary: #a855f7; --primary-hover: #9333ea; }
        [data-theme="orange"] { --primary: #f97316; --primary-hover: #ea580c; }
        [data-theme="pink"] { --primary: #ec4899; --primary-hover: #db2777; }
        [data-theme="gradient"] { --primary: #8b5cf6; --primary-hover: #7c3aed; }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg); color: var(--text); line-height: 1.6;
            min-height: 100vh; transition: background 0.4s ease, color 0.4s ease;
        }
        
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideIn { from { opacity: 0; transform: translateX(-30px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
        @keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
        @keyframes float { 0%, 100% { transform: translateY(0) rotate(0deg); } 50% { transform: translateY(-10px) rotate(2deg); } }
        @keyframes gradientMove { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        
        .animate-fade { animation: fadeIn 0.6s ease-out; }
        .animate-slide { animation: slideIn 0.5s ease-out; }
        .animate-scale { animation: scaleIn 0.4s ease-out; }
        .animate-bounce { animation: bounce 2s infinite; }
        .animate-float { animation: float 3s ease-in-out infinite; }
        
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; animation: fadeIn 0.5s ease-out; }
        
        .header { 
            background: var(--card); padding: 16px 20px; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            margin-bottom: 30px; position: sticky; top: 0; z-index: 100;
            backdrop-filter: blur(10px); transition: all 0.3s ease;
        }
        .header-content { 
            max-width: 1200px; margin: 0 auto; display: flex; 
            justify-content: space-between; align-items: center;
        }
        .logo { 
            font-size: 22px; font-weight: 800; color: var(--primary); 
            text-decoration: none; display: flex; align-items: center; gap: 8px;
            transition: transform 0.3s ease;
        }
        .logo:hover { transform: scale(1.05); }
        .logo-icon { font-size: 28px; animation: float 3s ease-in-out infinite; display: inline-block; }
        
        .nav { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .nav a { 
            color: var(--text); text-decoration: none; padding: 8px 14px; 
            border-radius: 10px; font-size: 14px; font-weight: 500;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }
        .nav a::before {
            content: ""; position: absolute; bottom: 0; left: 50%;
            width: 0; height: 2px; background: var(--primary);
            transition: all 0.3s ease; transform: translateX(-50%);
        }
        .nav a:hover::before { width: 80%; }
        .nav a:hover { background: var(--bg); color: var(--primary); transform: translateY(-2px); }
        
        .btn { 
            display: inline-flex; align-items: center; justify-content: center; gap: 6px;
            padding: 10px 20px; background: var(--primary); 
            color: white; border: none; border-radius: 10px; cursor: pointer;
            text-decoration: none; font-size: 14px; font-weight: 600;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2);
            position: relative; overflow: hidden;
        }
        .btn::before {
            content: ""; position: absolute; top: 50%; left: 50%;
            width: 0; height: 0; border-radius: 50%;
            background: rgba(255,255,255,0.3);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }
        .btn:hover::before { width: 300px; height: 300px; }
        .btn:hover { background: var(--primary-hover); transform: translateY(-2px); box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4); }
        .btn:active { transform: translateY(0); }
        
        .btn-secondary { background: var(--card); color: var(--text); border: 2px solid var(--border); box-shadow: none; }
        .btn-secondary:hover { background: var(--bg); border-color: var(--primary); color: var(--primary); }
        .btn-success { background: var(--success); box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3); }
        .btn-success:hover { background: #059669; }
        .btn-warning { background: var(--warning); box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3); }
        .btn-danger { background: var(--danger); box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3); }
        .btn-lg { padding: 14px 28px; font-size: 16px; }
        .btn-sm { padding: 6px 12px; font-size: 12px; }
        .btn-block { width: 100%; }
        
        .card { 
            background: var(--card); padding: 24px; border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06); margin-bottom: 20px;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid var(--border); animation: fadeIn 0.5s ease-out;
        }
        .card:hover { transform: translateY(-4px); box-shadow: 0 12px 40px rgba(0,0,0,0.12); }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
        .grid-2 { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
        
        .form-group { margin-bottom: 18px; }
        .form-group label { display: block; margin-bottom: 6px; font-weight: 600; font-size: 14px; }
        .form-group input, .form-group textarea, .form-group select { 
            width: 100%; padding: 12px 14px; border: 2px solid var(--border); 
            border-radius: 10px; background: var(--card); color: var(--text); 
            font-family: inherit; font-size: 14px; transition: all 0.3s ease;
        }
        .form-group input:focus, .form-group textarea:focus, .form-group select:focus { 
            outline: none; border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1); transform: translateY(-1px);
        }
        
        .alert { 
            padding: 14px 20px; border-radius: 12px; margin-bottom: 20px;
            display: flex; align-items: center; gap: 10px;
            animation: slideIn 0.4s ease-out; border-left: 4px solid;
        }
        .alert-success { background: #d1fae5; color: #065f46; border-color: var(--success); }
        .alert-error { background: #fee2e2; color: #991b1b; border-color: var(--danger); }
        
        .badge { 
            display: inline-flex; align-items: center; gap: 4px;
            padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;
            transition: all 0.3s ease;
        }
        .badge:hover { transform: scale(1.05); }
        .badge-success { background: #d1fae5; color: #065f46; }
        .badge-warning { background: #fef3c7; color: #92400e; }
        .badge-secondary { background: var(--bg); color: var(--text-secondary); }
        .badge-wb { background: linear-gradient(135deg, #cb11ab 0%, #8b0aaf 100%); color: white; }
        .badge-primary { background: var(--primary); color: white; }
        .badge-danger { background: #fee2e2; color: #991b1b; }
        
        .item-card { 
            border: 2px solid var(--border); border-radius: 16px; 
            overflow: hidden; transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            background: var(--card); animation: scaleIn 0.5s ease-out;
        }
        .item-card:hover { 
            transform: translateY(-6px) scale(1.01); 
            box-shadow: 0 20px 40px rgba(0,0,0,0.15); border-color: var(--primary);
        }
        .item-image { 
            width: 100%; height: 220px; background: var(--bg); 
            display: flex; align-items: center; justify-content: center; 
            font-size: 72px; overflow: hidden; position: relative;
        }
        .item-image img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.5s ease; }
        .item-card:hover .item-image img { transform: scale(1.1); }
        .item-content { padding: 20px; }
        .item-title { font-size: 17px; font-weight: 700; margin-bottom: 8px; line-height: 1.3; }
        .item-price { font-size: 22px; font-weight: 800; color: var(--primary); margin-bottom: 10px; }
        .item-description { color: var(--text-secondary); margin-bottom: 15px; font-size: 14px; }
        
        .flex { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .flex-between { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
        .flex-center { display: flex; justify-content: center; align-items: center; gap: 10px; }
        .mt-4 { margin-top: 20px; }
        .mb-4 { margin-bottom: 20px; }
        .text-center { text-align: center; }
        
        .captcha-box { 
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(168, 85, 247, 0.1) 100%);
            padding: 20px; border-radius: 12px; margin: 15px 0; text-align: center;
            border: 2px dashed var(--primary);
        }
        .captcha-question { 
            font-size: 28px; font-weight: 800; color: var(--primary); 
            margin-bottom: 10px; letter-spacing: 3px; animation: pulse 2s infinite;
        }
        
        .hero {
            text-align: center; padding: 60px 20px;
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(168, 85, 247, 0.05) 100%);
            border-radius: 24px; margin-bottom: 40px; position: relative; overflow: hidden;
        }
        .hero h1 {
            font-size: 52px; font-weight: 900; margin-bottom: 16px;
            background: linear-gradient(135deg, var(--primary) 0%, #a855f7 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text; background-size: 200% 200%;
            animation: gradientMove 5s ease infinite;
        }
        .hero p { font-size: 20px; color: var(--text-secondary); margin-bottom: 32px; }
        
        .stat-card {
            background: var(--card); padding: 24px; border-radius: 16px;
            text-align: center; transition: all 0.3s ease; border: 2px solid var(--border);
        }
        .stat-card:hover { transform: translateY(-4px); border-color: var(--primary); }
        .stat-number { 
            font-size: 36px; font-weight: 900; color: var(--primary);
            background: linear-gradient(135deg, var(--primary) 0%, #a855f7 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
        }
        .stat-label { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
        
        .wish-card {
            background: var(--card); border-radius: 16px; padding: 20px;
            border: 2px solid var(--border); transition: all 0.4s ease;
            cursor: pointer; position: relative; overflow: hidden; animation: fadeIn 0.5s ease-out;
        }
        .wish-card:hover { transform: translateY(-6px); border-color: var(--primary); box-shadow: 0 12px 30px rgba(0,0,0,0.1); }
        .wish-card-emoji { font-size: 48px; margin-bottom: 12px; display: block; animation: float 3s ease-in-out infinite; }
        .wish-card-title { font-size: 18px; font-weight: 700; margin-bottom: 6px; }
        .wish-card-meta { color: var(--text-secondary); font-size: 13px; display: flex; gap: 10px; flex-wrap: wrap; }
        
        .empty-state {
            text-align: center; padding: 60px 20px;
            background: var(--card); border-radius: 16px; border: 2px dashed var(--border);
        }
        .empty-state-icon { font-size: 72px; margin-bottom: 16px; animation: bounce 2s infinite; display: inline-block; }
        
        .toast {
            position: fixed; bottom: 20px; right: 20px;
            background: var(--card); padding: 16px 24px; border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            display: none; align-items: center; gap: 10px;
            animation: slideIn 0.4s ease-out; z-index: 2000; border-left: 4px solid var(--primary);
        }
        .toast.show { display: flex; }
        
        .emoji-picker { display: grid; grid-template-columns: repeat(8, 1fr); gap: 6px; margin: 10px 0; }
        .emoji-option { 
            font-size: 24px; padding: 8px; cursor: pointer; 
            border-radius: 8px; transition: all 0.2s ease;
            border: 2px solid transparent; text-align: center;
        }
        .emoji-option:hover { background: var(--bg); transform: scale(1.2); }
        .emoji-option.selected { border-color: var(--primary); background: var(--bg); }
        
        .image-preview {
            width: 100%; height: 200px; border-radius: 12px;
            background: var(--bg); display: flex; align-items: center; justify-content: center;
            overflow: hidden; margin-top: 10px; border: 2px dashed var(--border);
        }
        .image-preview img { width: 100%; height: 100%; object-fit: cover; }
        
        .wb-random-section {
            background: linear-gradient(135deg, rgba(203, 17, 171, 0.1) 0%, rgba(139, 10, 175, 0.1) 100%);
            padding: 30px; border-radius: 20px; margin-bottom: 30px;
            border: 2px solid rgba(203, 17, 171, 0.3);
        }
        .wb-random-title {
            font-size: 28px; font-weight: 800; margin-bottom: 20px;
            display: flex; align-items: center; gap: 12px;
        }
        .wb-random-grid {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px;
        }
        
        .table-responsive { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }
        th { background: var(--bg); font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }
        tr { transition: background 0.2s ease; }
        tr:hover { background: var(--bg); }
        
        @media (max-width: 768px) {
            .hero h1 { font-size: 36px; }
            .hero p { font-size: 16px; }
            .header-content { flex-direction: column; gap: 12px; }
            .nav { justify-content: center; }
            .grid { grid-template-columns: 1fr; }
            .emoji-picker { grid-template-columns: repeat(6, 1fr); }
        }
        
        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-track { background: var(--bg); }
        ::-webkit-scrollbar-thumb { background: var(--primary); border-radius: 5px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--primary-hover); }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <a href="/" class="logo">
                <span class="logo-icon">🎁</span>
                <span>WishList Pro</span>
            </a>
            <div class="nav">
                <a href="/">🏠 Главная</a>
                <a href="/ideas">💡 Идеи</a>
                {% if session.get("user_id") %}
                <a href="/dashboard">✨ Мои виши</a>
                <a href="/settings">⚙️</a>
                {% if session.get("is_admin") %}
                <a href="/admin" style="background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); color: white;">🔧 Админ</a>
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
                <div class="alert alert-{{ "success" if category == "success" else "error" }}">
                    <span>{{ "✅" if category == "success" else "❌" }}</span>
                    <span>{{ message }}</span>
                </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {{ content | safe }}
    </div>
    
    <div class="toast" id="toast"></div>
    
    <script>
        document.documentElement.setAttribute("data-theme", localStorage.getItem("theme") || "{{ theme }}");
        
        function showToast(message, type = "success") {
            const toast = document.getElementById("toast");
            toast.textContent = message;
            toast.className = "toast show";
            toast.style.borderLeftColor = type === "error" ? "var(--danger)" : "var(--success)";
            setTimeout(() => toast.classList.remove("show"), 3000);
        }
        
        function previewImage(input, previewId) {
            const preview = document.getElementById(previewId);
            if (input.value) {
                preview.innerHTML = "<img src=\"" + input.value + "\" onerror=\"this.parentElement.innerHTML='❌ Ошибка'\">";
            }
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
    conn = sqlite3.connect('wishlist.db')
    users_count = conn.execute('SELECT COUNT(*) FROM users WHERE is_banned=0').fetchone()[0]
    wishes_count = conn.execute('SELECT COUNT(*) FROM wishlists').fetchone()[0]
    items_count = conn.execute('SELECT COUNT(*) FROM wishlist_items').fetchone()[0]
    wb_count = conn.execute('SELECT COUNT(*) FROM wb_items').fetchone()[0]
    conn.close()

    user_logged = session.get("user_id")
    if user_logged:
        hero_buttons = '''
        <a href="/dashboard" class="btn btn-lg">✨ Мои виши</a>
        <a href="/wishlist/new" class="btn btn-secondary btn-lg">➕ Создать виш</a>
        '''
    else:
        hero_buttons = '''
        <a href="/register" class="btn btn-lg">🚀 Начать бесплатно</a>
        <a href="/ideas" class="btn btn-secondary btn-lg">💡 Идеи подарков</a>
        '''
    
    content = f'''
    <div class="hero">
        <h1 class="animate-fade">🎁 Создавай свои виши</h1>
        <p class="animate-fade" style="animation-delay: 0.2s;">
            Делись мечталками с друзьями и получай идеальные подарки
        </p>
        <div class="flex-center animate-fade" style="animation-delay: 0.4s;">
            {hero_buttons}
        </div>
    </div>
    
    
    <div class="grid" style="margin-bottom: 40px;">
        <div class="card text-center animate-slide" style="animation-delay: 0.1s;">
            <div style="font-size: 56px; margin-bottom: 12px;" class="animate-float">📝</div>
            <h3>Создавай виши</h3>
            <p style="color: var(--text-secondary); margin-top: 8px;">Собирай желания в красивые вишлисты</p>
        </div>
        <div class="card text-center animate-slide" style="animation-delay: 0.2s;">
            <div style="font-size: 56px; margin-bottom: 12px;" class="animate-float">🔗</div>
            <h3>Делись ссылкой</h3>
            <p style="color: var(--text-secondary); margin-top: 8px;">Красивые короткие ссылки на каждый виш</p>
        </div>
        <div class="card text-center animate-slide" style="animation-delay: 0.3s;">
            <div style="font-size: 56px; margin-bottom: 12px;" class="animate-float">🎉</div>
            <h3>Получай подарки</h3>
            <p style="color: var(--text-secondary); margin-top: 8px;">Друзья бронируют и дарят</p>
        </div>
    </div>
    
    <div class="grid" style="grid-template-columns: repeat(4, 1fr);">
        <div class="stat-card animate-scale" style="animation-delay: 0.4s;">
            <div class="stat-number">{users_count}</div>
            <div class="stat-label">Вишелюбов</div>
        </div>
        <div class="stat-card animate-scale" style="animation-delay: 0.5s;">
            <div class="stat-number">{wishes_count}</div>
            <div class="stat-label">Вишей создано</div>
        </div>
        <div class="stat-card animate-scale" style="animation-delay: 0.6s;">
            <div class="stat-number">{items_count}</div>
            <div class="stat-label">Желаний</div>
        </div>
        <div class="stat-card animate-scale" style="animation-delay: 0.7s;">
        </div>
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
                flash('❌ Неверный ответ на капчу', 'error')
                return redirect(url_for('register'))
        except:
            flash('❌ Введите число', 'error')
            return redirect(url_for('register'))
        
        username = request.form['username'].strip()
        password = request.form['password']
        email = request.form.get('email', '')
        
        if len(username) < 3:
            flash('Имя пользователя должно быть минимум 3 символа', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 4:
            flash('Пароль должен быть минимум 4 символа', 'error')
            return redirect(url_for('register'))
        
        conn = sqlite3.connect('wishlist.db')
        existing = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
        if existing:
            flash('Такой вишелюб уже существует 😕', 'error')
            conn.close()
            return redirect(url_for('register'))
        
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        c = conn.cursor()
        c.execute('''INSERT INTO users (username, password, email, created_at, last_login, login_count) 
                     VALUES (?, ?, ?, ?, ?, 1)''',
                 (username, hashed_pw, email, datetime.now().date(), datetime.now().date()))
        user_id = c.lastrowid
        
        slug = slugify(f"{username}-main")
        c.execute('''INSERT INTO wishlists (user_id, title, description, slug, is_default, created_at) 
                     VALUES (?, ?, ?, ?, 1, ?)''',
                 (user_id, 'Мой первый виш', 'Главный вишлист', slug, datetime.now().date()))
        
        conn.commit()
        conn.close()
        
        flash('🎉 Добро пожаловать, вишелюб! Твой первый виш уже создан!', 'success')
        return redirect(url_for('login'))
    
    question, answer = generate_captcha()
    session['captcha_answer'] = answer
    theme = session.get('theme', 'light')
    
    content = f'''
    <div class="card animate-scale" style="max-width: 500px; margin: 40px auto;">
        <h2 style="margin-bottom: 8px;">🚀 Стать вишелюбом</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">Создай аккаунт и начни собирать виши</p>
        <form method="POST">
            <div class="form-group">
                <label>Имя вишелюба *</label>
                <input type="text" name="username" required placeholder="твой_ник" minlength="3">
            </div>
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" placeholder="you@example.com">
            </div>
            <div class="form-group">
                <label>Пароль *</label>
                <input type="password" name="password" required minlength="4">
            </div>
            
            <div class="captcha-box">
                <div style="margin-bottom: 10px; color: var(--text-secondary); font-size: 14px;">🧮 Докажи что ты не робот:</div>
                <div class="captcha-question">{question} = ?</div>
                <input type="number" name="captcha_answer" required placeholder="Ответ" 
                       style="width: 150px; text-align: center; font-size: 18px; font-weight: bold;">
            </div>
            
            <button type="submit" class="btn btn-block btn-lg">Создать аккаунт</button>
        </form>
        <p style="margin-top: 20px; text-align: center; color: var(--text-secondary);">
            Уже с нами? <a href="/login" style="color: var(--primary); font-weight: 600;">Войти</a>
        </p>
    </div>
    '''
    
    return render_template_string(HTML_BASE, theme=theme, title='Регистрация', content=content)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # 🕵️ Проверяем — это вход админа?
        is_admin_login = request.form.get('admin_login') == '1'
        
        username = request.form['username']
        password = request.form['password']
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        
        if is_admin_login:
            # 🔐 ВХОД КАК АДМИН
            conn = sqlite3.connect('wishlist.db')
            conn.row_factory = sqlite3.Row
            user = conn.execute('''SELECT * FROM users 
                                   WHERE username=? AND password=? AND is_admin=1 AND is_banned=0''', 
                               (username, hashed_pw)).fetchone()
            conn.close()
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = user['is_admin']
                session['theme'] = user['theme']
                session['currency'] = user['currency']
                
                conn = sqlite3.connect('wishlist.db')
                conn.execute('UPDATE users SET last_login=?, login_count=login_count+1 WHERE id=?',
                            (datetime.now().date(), user['id']))
                conn.commit()
                conn.close()
                
                flash(f'👑 Добро пожаловать, админ {user["username"]}!', 'success')
                return redirect(url_for('admin'))  # ← Сразу в админку
            else:
                flash('🚫 Неверные данные администратора', 'error')
                return redirect(url_for('login'))
        else:
            # 👤 ОБЫЧНЫЙ ВХОД
            conn = sqlite3.connect('wishlist.db')
            conn.row_factory = sqlite3.Row
            user = conn.execute('SELECT * FROM users WHERE username=? AND password=?', 
                               (username, hashed_pw)).fetchone()
            
            if user and user['is_banned']:
                flash('🚫 Этот аккаунт заблокирован', 'error')
                conn.close()
                return redirect(url_for('login'))
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = user['is_admin']
                session['theme'] = user['theme']
                session['currency'] = user['currency']
                
                conn.execute('UPDATE users SET last_login=?, login_count=login_count+1 WHERE id=?',
                            (datetime.now().date(), user['id']))
                conn.commit()
                conn.close()
                
                flash(f'👋 С возвращением, {user["username"]}!', 'success')
                
                # Если это админ — редиректим в админку
                if user['is_admin']:
                    return redirect(url_for('admin'))
                return redirect(url_for('dashboard'))
            else:
                flash('Неверное имя или пароль', 'error')
                conn.close()
    
    # 🎨 GET запрос — показываем форму
    theme = session.get('theme', 'light')
    content = '''
    <div class="card animate-scale" style="max-width: 500px; margin: 40px auto;">
        <h2 style="margin-bottom: 8px;">🔑 Вход</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">С возвращением, вишелюб!</p>
        <form method="POST" id="loginForm">
            <input type="hidden" name="admin_login" id="adminLoginFlag" value="0">
            
            <div class="form-group">
                <label>Имя вишелюба</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>Пароль</label>
                <input type="password" name="password" required>
            </div>
            
            <!-- 🔐 СЕКРЕТНАЯ АДМИН-ПАНЕЛЬ (появляется после 5 кликов) -->
            <div id="adminPanel" style="display: none; margin-top: 20px; padding: 20px; 
                                        background: linear-gradient(135deg, rgba(236, 72, 153, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%); 
                                        border: 2px dashed #ec4899; border-radius: 12px;
                                        animation: scaleIn 0.4s ease-out;">
                <div style="text-align: center; margin-bottom: 15px;">
                    <div style="font-size: 36px; animation: bounce 1s infinite;">👑</div>
                    <h3 style="color: #ec4899; margin-top: 8px;">Режим администратора</h3>
                </div>
            </div>
            
            <button type="submit" class="btn btn-block btn-lg">Войти</button>
        </form>
        
        <div style="margin-top: 20px; text-align: center; color: var(--text-secondary); font-size: 13px;">
            <span id="keyIcon" style="cursor: pointer; font-size: 20px; display: inline-block; 
                                      transition: transform 0.2s; user-select: none;" 
                  title="🔑">🔑</span>
            <span id="clickCounter" style="margin-left: 8px; opacity: 0.5;"></span>
        </div>
        
        <p style="margin-top: 20px; text-align: center; color: var(--text-secondary);">
            Ещё не с нами? <a href="/register" style="color: var(--primary); font-weight: 600;">Стать вишелюбом</a>
        </p>
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
                
                // Анимация клика
                keyIcon.style.transform = 'rotate(' + (clickCount * 72) + 'deg) scale(1.3)';
                setTimeout(() => {
                    keyIcon.style.transform = 'rotate(' + (clickCount * 72) + 'deg) scale(1)';
                }, 150);
                
                // Показываем счётчик начиная с 3-го клика
                if (clickCount >= 3) {
                    counter.textContent = clickCount + '/5';
                    counter.style.opacity = '1';
                    counter.style.color = '#ec4899';
                    counter.style.fontWeight = 'bold';
                }
                
                // 🎉 При 5 кликах — показываем админ-панель
                if (clickCount >= 5) {
                    adminPanel.style.display = 'block';
                    adminFlag.value = '1';
                    counter.textContent = '✨ Режим админа активирован!';
                    counter.style.color = '#10b981';
                    keyIcon.style.transform = 'rotate(360deg) scale(1.2)';
                    
                    // Меняем заголовок формы
                    document.querySelector('h2').innerHTML = '👑 Вход администратора';
                    
                    // Блокируем дальнейшие клики
                    keyIcon.style.pointerEvents = 'none';
                }
                
                // Сброс счётчика через 3 секунды бездействия
                clearTimeout(resetTimer);
                resetTimer = setTimeout(() => {
                    if (clickCount < 5) {
                        clickCount = 0;
                        counter.textContent = '';
                        counter.style.opacity = '0.5';
                        keyIcon.style.transform = 'rotate(0deg) scale(1)';
                    }
                }, 3000);
            });
            
            // Предотвращаем выделение
            keyIcon.addEventListener('mousedown', (e) => e.preventDefault());
        })();
    </script>
    '''
    
    return render_template_string(HTML_BASE, theme=theme, title='Вход', content=content)

@app.route('/logout')
def logout():
    session.clear()
    flash('👋 Ты вышел. Возвращайся скорее!', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    theme = session.get('theme', 'light')
    
    conn = sqlite3.connect('wishlist.db')
    wishlists = conn.execute('''
        SELECT w.*, 
               (SELECT COUNT(*) FROM wishlist_items WHERE wishlist_id=w.id) as items_count,
               (SELECT COUNT(*) FROM wishlist_items WHERE wishlist_id=w.id AND reserved_by IS NOT NULL) as reserved_count
        FROM wishlists w 
        WHERE w.user_id = ? 
        ORDER BY w.is_default DESC, w.created_at DESC
    ''', (user_id,)).fetchall()
    conn.close()
    
    if not wishlists:
        content = '''
        <div class="empty-state animate-scale">
            <div class="empty-state-icon">🎁</div>
            <h2 style="margin-bottom: 12px;">У тебя пока нет вишей</h2>
            <p style="color: var(--text-secondary); margin-bottom: 24px;">
                Виш — это твой персональный вишлист. Создай первый и начни собирать желания!
            </p>
            <a href="/wishlist/new" class="btn btn-lg">✨ Создать первый виш</a>
        </div>
        '''
    else:
        wishes_html = ''
        for w in wishlists:
            items_count = w['items_count']  # Всегда работает, читаемо, надёжно
            reserved_count = w[11]
            progress = int((reserved_count / items_count * 100)) if items_count > 0 else 0
            slug = w[5]
            cover = w[7] or '🎁'
            
            wishes_html += f'''
            <a href="/w/{slug}" class="wish-card" style="text-decoration: none; color: inherit;">
                <span class="wish-card-emoji">{cover}</span>
                <div class="wish-card-title">{w[2]}</div>
                <div class="wish-card-meta">
                    <span>🎯 {items_count} желаний</span>
                    <span>✅ {reserved_count} забрано</span>
                    {'<span class="badge badge-primary">⭐ Главный</span>' if w[6] else ''}
                </div>
                <div style="height: 6px; background: var(--bg); border-radius: 3px; margin-top: 10px; overflow: hidden;">
                    <div style="height: 100%; width: {progress}%; background: linear-gradient(90deg, var(--primary), #a855f7); border-radius: 3px;"></div>
                </div>
            </a>
            '''
        
        content = f'''
        <div class="flex-between mb-4">
            <div>
                <h1 style="font-size: 32px;">✨ Мои виши</h1>
                <p style="color: var(--text-secondary);">Всего вишей: {len(wishlists)}</p>
            </div>
            <div class="flex">
                <a href="/wishlist/new" class="btn">➕ Новый виш</a>
            </div>
        </div>
        
        <div class="grid-2">
            {wishes_html}
        </div>
        '''
    
    return render_template_string(HTML_BASE, theme=theme, title='Мои виши', content=content)

@app.route('/wishlist/new', methods=['GET', 'POST'])
def new_wishlist():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description', '').strip()
        cover_emoji = request.form.get('cover_emoji', '🎁')
        is_public = 1 if request.form.get('is_public') else 0
        
        if not title:
            flash('Введите название виша', 'error')
            return redirect(url_for('new_wishlist'))
        
        slug = slugify(title)
        
        conn = sqlite3.connect('wishlist.db')
        conn.execute('''INSERT INTO wishlists (user_id, title, description, slug, is_public, cover_emoji, created_at) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (session['user_id'], title, description, slug, is_public, cover_emoji, datetime.now().date()))
        conn.commit()
        conn.close()
        
        flash(f'🎉 Виш "{title}" создан! Добавь в него желания.', 'success')
        return redirect(url_for('view_wishlist', slug=slug))
    
    theme = session.get('theme', 'light')
    emojis = ['🎁', '🎂', '🎄', '💝', '🎓', '👰', '🏠', '🚗', '✈️', '💻', '📱', '🎮', '📚', '🎨', '⚽', '🎵', '💎', '🌹', '🍰', '🎈']
    emoji_html = ''.join([f'<div class="emoji-option" onclick="selectEmoji(this, \'{e}\')">{e}</div>' for e in emojis])
    
    content = f'''
    <div class="card animate-scale" style="max-width: 600px; margin: 0 auto;">
        <h2 style="margin-bottom: 8px;">✨ Новый виш</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">Создай свой персональный вишлист</p>
        <form method="POST">
            <div class="form-group">
                <label>Название виша *</label>
                <input type="text" name="title" required placeholder="Например: День рождения 2026" maxlength="50">
            </div>
            <div class="form-group">
                <label>Описание</label>
                <textarea name="description" rows="3" placeholder="Расскажи о своём више..."></textarea>
            </div>
            <div class="form-group">
                <label>Обложка виша</label>
                <div class="emoji-picker" id="emojiPicker">
                    {emoji_html}
                </div>
                <input type="hidden" name="cover_emoji" id="coverEmoji" value="🎁">
            </div>
            <div class="form-group">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" name="is_public" value="1" checked style="width: auto;">
                    <span>Публичный виш (виден всем по ссылке)</span>
                </label>
            </div>
            <div class="flex" style="gap: 10px;">
                <button type="submit" class="btn" style="flex: 1;">✨ Создать виш</button>
                <a href="/dashboard" class="btn btn-secondary" style="flex: 1;">Отмена</a>
            </div>
        </form>
    </div>
    
    <script>
        function selectEmoji(el, emoji) {{
            document.querySelectorAll(".emoji-option").forEach(e => e.classList.remove("selected"));
            el.classList.add("selected");
            document.getElementById("coverEmoji").value = emoji;
        }}
        document.querySelector(".emoji-option").classList.add("selected");
    </script>
    '''
    
    return render_template_string(HTML_BASE, theme=theme, title='Новый виш', content=content)

@app.route('/w/<slug>')
def view_wishlist(slug):
    conn = sqlite3.connect('wishlist.db')
    wishlist = conn.execute('SELECT * FROM wishlists WHERE slug=?', (slug,)).fetchone()
    
    if not wishlist:
        flash('Виш не найден 😕', 'error')
        conn.close()
        return redirect(url_for('index'))
    
    user_id = wishlist[1]
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    
    current_user_id = session.get('user_id')
    if not wishlist[6] and current_user_id != user_id and not session.get('is_admin'):
        flash('Этот виш приватный 🔒', 'error')
        conn.close()
        return redirect(url_for('index'))
    
    items = conn.execute('''
        SELECT i.*, u.username as reserved_by_name 
        FROM wishlist_items i 
        LEFT JOIN users u ON i.reserved_by = u.id 
        WHERE i.wishlist_id = ? 
        ORDER BY i.priority DESC, i.created_at DESC
    ''', (wishlist[0],)).fetchall()
    conn.close()
    
    is_owner = current_user_id == user_id
    cover = wishlist[7] or '🎁'
    
    items_html = ''
    if items:
        for item in items:
            price_html = f'<div class="item-price">💰 {item[5]} {item[6] or "BYN"}</div>' if item[5] else ''
            desc_html = f'<p class="item-description">{item[3]}</p>' if item[3] else ''
            link_html = f'<a href="{item[4]}" target="_blank" class="btn btn-secondary btn-sm">🔗 Купить</a>' if item[4] else ''
            
            if item[7]:
                img_html = f'<img src="{item[7]}" alt="{item[2]}" onerror="this.parentElement.innerHTML=\'🎁\'">'
            else:
                img_html = '🎁'
            
            reserve_html = ''
            if item[9]:
                if item[9] == current_user_id:
                    reserve_html = f'''
                        <span class="badge badge-success">✓ Вы забрали</span>
                        <a href="/unreserve/{item[0]}" class="btn btn-secondary btn-sm" style="margin-top: 8px; display: block;">↩️ Отменить</a>
                    '''
                else:
                    reserve_html = '<span class="badge badge-warning">🔒 Забронировано</span>'
            elif current_user_id and current_user_id != user_id:
                reserve_html = f'<a href="/reserve/{item[0]}" class="btn btn-success btn-block">🎯 Забрать</a>'
            elif not current_user_id:
                reserve_html = '<a href="/login" class="btn btn-secondary btn-block">Войти чтобы забрать</a>'
            
            owner_actions = ''
            if is_owner:
                owner_actions = f'''
                    <div style="margin-top: 10px; display: flex; gap: 6px;">
                        <a href="/item/{item[0]}/edit" class="btn btn-secondary btn-sm" style="flex: 1;">✏️</a>
                        <a href="/item/{item[0]}/delete" class="btn btn-danger btn-sm" style="flex: 1;" 
                           onclick="return confirm('Удалить желание?')">🗑️</a>
                    </div>
                '''
            
            items_html += f'''
            <div class="item-card">
                <div class="item-image">{img_html}</div>
                <div class="item-content">
                    <h3 class="item-title">{item[2]}</h3>
                    {price_html}
                    {desc_html}
                    {link_html}
                    <div style="margin-top: 12px;">{reserve_html}</div>
                    {owner_actions}
                </div>
            </div>
            '''
    else:
        if is_owner:
            items_html = f'''
            <div class="empty-state" style="grid-column: 1/-1;">
                <div class="empty-state-icon">🎁</div>
                <h3>Виш пока пустой</h3>
                <p style="color: var(--text-secondary); margin: 12px 0 20px;">Добавь первое желание!</p>
                <div class="flex-center">
                    <a href="/w/{slug}/add" class="btn">➕ Добавить желание</a>
                    <a href="/ideas" class="btn btn-secondary">💡 Из идей</a>
                </div>
            </div>
            '''
        else:
            items_html = '<div class="empty-state" style="grid-column: 1/-1;"><div class="empty-state-icon">🤷</div><h3>Пока пусто</h3></div>'
    
    owner_actions_html = ''
    if is_owner:
        owner_actions_html = f'''
            <div class="flex" style="margin-top: 16px; justify-content: center;">
                <a href="/w/{slug}/add" class="btn">➕ Добавить желание</a>
                <a href="/w/{slug}/edit" class="btn btn-secondary">✏️ Редактировать</a>
                <button onclick="copyLink()" class="btn btn-secondary">📋 Копировать ссылку</button>
                <a href="/w/{slug}/delete" class="btn btn-danger" onclick="return confirm('Удалить виш со всеми желаниями?')">🗑️</a>
            </div>
        '''
    
    share_url = f"{BASE_URL}/w/{slug}"
    
    content = f'''
    <div class="card text-center animate-scale" style="margin-bottom: 30px; background: linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(168, 85, 247, 0.05) 100%);">
        <div style="font-size: 72px; margin-bottom: 12px;" class="animate-float">{cover}</div>
        <h1 style="font-size: 36px; margin-bottom: 8px;">{wishlist[2]}</h1>
        {f'<p style="color: var(--text-secondary); margin-bottom: 12px;">{wishlist[3]}</p>' if wishlist[3] else ''}
        <p style="color: var(--text-secondary);">
            👤 {user[1]} • 🎯 {len(items)} желаний
        </p>
        <div style="margin-top: 12px; font-size: 13px; color: var(--text-secondary);">
            🔗 <code style="background: var(--bg); padding: 4px 10px; border-radius: 6px;">{share_url}</code>
        </div>
        {owner_actions_html}
    </div>
    
    <div class="grid">{items_html}</div>
    
    <script>
        function copyLink() {{
            navigator.clipboard.writeText("{share_url}").then(() => {{
                showToast("📋 Ссылка скопирована!");
            }});
        }}
    </script>
    '''
    
    return render_template_string(HTML_BASE, theme=user[4] if user[4] else 'light', 
                                 title=f'{wishlist[2]} • Виш', content=content)

@app.route('/w/<slug>/add', methods=['GET', 'POST'])
def add_to_wishlist(slug):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    wishlist = conn.execute('SELECT * FROM wishlists WHERE slug=? AND user_id=?', 
                           (slug, session['user_id'])).fetchone()
    
    if not wishlist:
        flash('Виш не найден', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description', '').strip()
        link = request.form.get('link', '').strip()
        price = request.form.get('price')
        currency = request.form.get('currency', session.get('currency', 'BYN'))
        image_url = request.form.get('image_url', '').strip()
        priority = int(request.form.get('priority', 0))
        
        if not title:
            flash('Введите название', 'error')
            conn.close()
            return redirect(url_for('add_to_wishlist', slug=slug))
        
        conn.execute('''INSERT INTO wishlist_items 
                        (wishlist_id, title, description, link, price, currency, image_url, priority, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (wishlist[0], title, description, link, 
                     float(price) if price else None, currency, image_url, priority, datetime.now().date()))
        conn.commit()
        conn.close()
        
        flash('✨ Желание добавлено в виш!', 'success')
        return redirect(url_for('view_wishlist', slug=slug))
    
    conn.close()
    theme = session.get('theme', 'light')
    user_currency = session.get('currency', 'BYN')
    currency_options = ''.join([f'<option value="{code}" {"selected" if code == user_currency else ""}>{name}</option>' for code, name in CURRENCIES.items()])
    
    content = f'''
    <div class="card animate-scale" style="max-width: 650px; margin: 0 auto;">
        <h2 style="margin-bottom: 8px;">➕ Новое желание</h2>
        <p style="color: var(--text-secondary); margin-bottom: 24px;">В виш: <b>{wishlist[2]}</b></p>
        <form method="POST">
            <div class="form-group">
                <label>Название *</label>
                <input type="text" name="title" required placeholder="Что хочешь?">
            </div>
            <div class="form-group">
                <label>Описание</label>
                <textarea name="description" rows="2" placeholder="Цвет, размер, модель..."></textarea>
            </div>
            <div class="flex" style="gap: 12px;">
                <div class="form-group" style="flex: 1;">
                    <label>Цена</label>
                    <input type="number" name="price" step="0.01" placeholder="0.00">
                </div>
                <div class="form-group" style="flex: 1;">
                    <label>Валюта</label>
                    <select name="currency">{currency_options}</select>
                </div>
            </div>
            <div class="form-group">
                <label>🔗 Ссылка на товар</label>
                <input type="url" name="link" placeholder="https://...">
            </div>
            <div class="form-group">
                <label>🖼️ URL картинки</label>
                <input type="url" name="image_url" placeholder="https://...jpg" 
                       oninput="previewImage(this, 'imgPreview')">
                <div class="image-preview" id="imgPreview">🖼️ Превью появится тут</div>
            </div>
            <div class="form-group">
                <label>⭐ Приоритет (0-10)</label>
                <input type="number" name="priority" min="0" max="10" value="0">
            </div>
            <div class="flex" style="gap: 10px;">
                <button type="submit" class="btn" style="flex: 1;">✨ Добавить в виш</button>
                <a href="/w/{slug}" class="btn btn-secondary" style="flex: 1;">Отмена</a>
            </div>
        </form>
    </div>
    '''
    
    return render_template_string(HTML_BASE, theme=theme, title='Добавить желание', content=content)

@app.route('/w/<slug>/edit', methods=['GET', 'POST'])
def edit_wishlist(slug):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    wishlist = conn.execute('SELECT * FROM wishlists WHERE slug=? AND user_id=?', 
                           (slug, session['user_id'])).fetchone()
    
    if not wishlist:
        flash('Виш не найден', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description', '').strip()
        cover_emoji = request.form.get('cover_emoji', wishlist[7])
        is_public = 1 if request.form.get('is_public') else 0
        
        conn.execute('''UPDATE wishlists SET title=?, description=?, cover_emoji=?, is_public=? 
                        WHERE id=?''', (title, description, cover_emoji, is_public, wishlist[0]))
        conn.commit()
        conn.close()
        
        flash('✅ Виш обновлён!', 'success')
        return redirect(url_for('view_wishlist', slug=slug))
    
    conn.close()
    theme = session.get('theme', 'light')
    emojis = ['🎁', '🎂', '🎄', '💝', '🎓', '👰', '🏠', '🚗', '✈️', '💻', '📱', '🎮', '📚', '🎨', '⚽', '🎵', '💎', '🌹', '🍰', '🎈']
    emoji_html = ''.join([f'<div class="emoji-option {"selected" if e == wishlist[7] else ""}" onclick="selectEmoji(this, \'{e}\')">{e}</div>' for e in emojis])
    
    content = f'''
    <div class="card animate-scale" style="max-width: 600px; margin: 0 auto;">
        <h2 style="margin-bottom: 24px;">✏️ Редактировать виш</h2>
        <form method="POST">
            <div class="form-group">
                <label>Название</label>
                <input type="text" name="title" required value="{wishlist[2]}" maxlength="50">
            </div>
            <div class="form-group">
                <label>Описание</label>
                <textarea name="description" rows="3">{wishlist[3] or ''}</textarea>
            </div>
            <div class="form-group">
                <label>Обложка</label>
                <div class="emoji-picker">{emoji_html}</div>
                <input type="hidden" name="cover_emoji" id="coverEmoji" value="{wishlist[7] or '🎁'}">
            </div>
            <div class="form-group">
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" name="is_public" value="1" {"checked" if wishlist[6] else ""} style="width: auto;">
                    <span>Публичный виш</span>
                </label>
            </div>
            <div class="flex" style="gap: 10px;">
                <button type="submit" class="btn" style="flex: 1;">💾 Сохранить</button>
                <a href="/w/{slug}" class="btn btn-secondary" style="flex: 1;">Отмена</a>
            </div>
        </form>
    </div>
    <script>
        function selectEmoji(el, emoji) {{
            document.querySelectorAll(".emoji-option").forEach(e => e.classList.remove("selected"));
            el.classList.add("selected");
            document.getElementById("coverEmoji").value = emoji;
        }}
    </script>
    '''
    
    return render_template_string(HTML_BASE, theme=theme, title='Редактировать виш', content=content)

@app.route('/w/<slug>/delete')
def delete_wishlist(slug):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    wishlist = conn.execute('SELECT * FROM wishlists WHERE slug=? AND user_id=?', 
                           (slug, session['user_id'])).fetchone()
    
    if wishlist:
        conn.execute('DELETE FROM wishlist_items WHERE wishlist_id=?', (wishlist[0],))
        conn.execute('DELETE FROM wishlists WHERE id=?', (wishlist[0],))
        conn.commit()
        flash('🗑️ Виш удалён', 'success')
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/item/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_item(item_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    item = conn.execute('''SELECT i.*, w.user_id, w.slug FROM wishlist_items i 
                          JOIN wishlists w ON i.wishlist_id=w.id WHERE i.id=?''', (item_id,)).fetchone()
    
    if not item or item[11] != session['user_id']:
        flash('Нет доступа', 'error')
        conn.close()
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        conn.execute('''UPDATE wishlist_items SET title=?, description=?, link=?, price=?, 
                        currency=?, image_url=?, priority=? WHERE id=?''',
                    (request.form['title'], request.form.get('description', ''),
                     request.form.get('link', ''), 
                     float(request.form['price']) if request.form.get('price') else None,
                     request.form.get('currency', 'BYN'),
                     request.form.get('image_url', ''),
                     int(request.form.get('priority', 0)), item_id))
        conn.commit()
        conn.close()
        flash('✅ Желание обновлено!', 'success')
        return redirect(url_for('view_wishlist', slug=item[12]))
    
    conn.close()
    theme = session.get('theme', 'light')
    user_currency = session.get('currency', 'BYN')
    currency_options = ''.join([f'<option value="{code}" {"selected" if code == (item[6] or user_currency) else ""}>{name}</option>' for code, name in CURRENCIES.items()])
    
    content = f'''
    <div class="card animate-scale" style="max-width: 650px; margin: 0 auto;">
        <h2 style="margin-bottom: 24px;">✏️ Редактировать желание</h2>
        <form method="POST">
            <div class="form-group">
                <label>Название</label>
                <input type="text" name="title" required value="{item[2]}">
            </div>
            <div class="form-group">
                <label>Описание</label>
                <textarea name="description" rows="2">{item[3] or ''}</textarea>
            </div>
            <div class="flex" style="gap: 12px;">
                <div class="form-group" style="flex: 1;">
                    <label>Цена</label>
                    <input type="number" name="price" step="0.01" value="{item[5] or ''}">
                </div>
                <div class="form-group" style="flex: 1;">
                    <label>Валюта</label>
                    <select name="currency">{currency_options}</select>
                </div>
            </div>
            <div class="form-group">
                <label>Ссылка</label>
                <input type="url" name="link" value="{item[4] or ''}">
            </div>
            <div class="form-group">
                <label>URL картинки</label>
                <input type="url" name="image_url" value="{item[7] or ''}" oninput="previewImage(this, 'imgPreview')">
                <div class="image-preview" id="imgPreview">
                    {f'<img src="{item[7]}">' if item[7] else '🖼️ Превью'}
                </div>
            </div>
            <div class="form-group">
                <label>Приоритет (0-10)</label>
                <input type="number" name="priority" min="0" max="10" value="{item[10] or 0}">
            </div>
            <div class="flex" style="gap: 10px;">
                <button type="submit" class="btn" style="flex: 1;">💾 Сохранить</button>
                <a href="/w/{item[12]}" class="btn btn-secondary" style="flex: 1;">Отмена</a>
            </div>
        </form>
    </div>
    '''
    
    return render_template_string(HTML_BASE, theme=theme, title='Редактировать', content=content)

@app.route('/item/<int:item_id>/delete')
def delete_item(item_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    item = conn.execute('''SELECT i.wishlist_id, w.slug, w.user_id FROM wishlist_items i 
                          JOIN wishlists w ON i.wishlist_id=w.id WHERE i.id=?''', (item_id,)).fetchone()
    
    if item and item[2] == session['user_id']:
        conn.execute('DELETE FROM wishlist_items WHERE id=?', (item_id,))
        conn.commit()
        flash('🗑️ Желание удалено', 'success')
        slug = item[1]
    else:
        slug = None
    conn.close()
    
    return redirect(url_for('view_wishlist', slug=slug) if slug else url_for('dashboard'))

@app.route('/reserve/<int:item_id>')
def reserve(item_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    item = conn.execute('SELECT * FROM wishlist_items WHERE id=? AND reserved_by IS NULL', (item_id,)).fetchone()
    if item:
        conn.execute('UPDATE wishlist_items SET reserved_by=? WHERE id=?', (session['user_id'], item_id))
        conn.execute('INSERT INTO reservations (item_id, reserved_by, reserved_at) VALUES (?, ?, ?)',
                    (item_id, session['user_id'], datetime.now().date()))
        conn.commit()
        flash('🎯 Подарок забронирован!', 'success')
    conn.close()
    return redirect(request.referrer or url_for('index'))

@app.route('/unreserve/<int:item_id>')
def unreserve(item_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    conn.execute('UPDATE wishlist_items SET reserved_by=NULL WHERE id=? AND reserved_by=?',
                (item_id, session['user_id']))
    conn.execute('DELETE FROM reservations WHERE item_id=? AND reserved_by=?', (item_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('↩️ Бронь снята', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/ideas')
def ideas():
    theme = session.get('theme', 'light')
    user_currency = session.get('currency', 'BYN')
    
    conn = sqlite3.connect('wishlist.db')
    category = request.args.get('category', '')
    search = request.args.get('search', '').strip()
    
    if category:
        ideas = conn.execute('SELECT * FROM ideas WHERE category=? ORDER BY created_at DESC', (category,)).fetchall()
    elif search:
        ideas = conn.execute('SELECT * FROM ideas WHERE title LIKE ? ORDER BY created_at DESC', (f'%{search}%',)).fetchall()
    else:
        ideas = conn.execute('SELECT * FROM ideas ORDER BY created_at DESC').fetchall()
    
    categories = conn.execute('SELECT DISTINCT category FROM ideas WHERE category IS NOT NULL').fetchall()
    conn.close()
    
    category_buttons = ''.join([f'<a href="/ideas?category={cat[0]}" class="btn btn-sm {"btn-success" if category == cat[0] else "btn-secondary"}">{cat[0]}</a>' for cat in categories])
    
    ideas_html = ''
    for idea in ideas:
        wb_badge = '<span class="badge badge-wb">WB</span>' if idea[8] == 'wildberries' else ''
        price_html = f'<div class="item-price">💰 {idea[3]} {idea[4] or user_currency}</div>' if idea[3] else ''
        link_html = f'<a href="{idea[6]}" target="_blank" class="btn btn-secondary btn-sm">🔗</a>' if idea[6] else ''
        
        if idea[5]:
            img_html = f'<img src="{idea[5]}" alt="{idea[1]}" onerror="this.parentElement.innerHTML=\'🎁\'">'
        else:
            img_html = '🎁'
        
        add_btn = ''
        if session.get('user_id'):
            add_btn = f'<a href="/add_item_from_idea/{idea[0]}" class="btn btn-block">➕ В мой виш</a>'
        else:
            add_btn = '<a href="/login" class="btn btn-secondary btn-block">Войти чтобы добавить</a>'
        
        ideas_html += f'''
        <div class="item-card">
            <div class="item-image">{img_html}</div>
            <div class="item-content">
                <div class="flex-between" style="margin-bottom: 8px;">
                    <h3 class="item-title" style="margin: 0;">{idea[1]}</h3>
                    {wb_badge}
                </div>
                {price_html}
                <p class="item-description">{idea[2]}</p>
                {link_html}
                <div style="margin-top: 10px;">{add_btn}</div>
            </div>
        </div>
        '''
    
    if not ideas_html:
        ideas_html = '<div class="empty-state" style="grid-column: 1/-1;"><div class="empty-state-icon">🔍</div><h3>Ничего не найдено</h3></div>'
    
    content = f'''
    <div class="flex-between mb-4">
        <div>
            <h1 style="font-size: 32px;">💡 Идеи подарков</h1>
            <p style="color: var(--text-secondary);">Готовые идеи для твоих вишей</p>
        </div>
    </div>
    
    <div class="card" style="margin-bottom: 20px;">
        <form method="GET" class="flex" style="gap: 10px;">
            <input type="search" name="search" placeholder="🔍 Поиск идей..." 
                   value="{search}" style="flex: 1;">
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
    
    return render_template_string(HTML_BASE, theme=theme, title='Идеи подарков', content=content)

@app.route('/wb_random')
def wb_random():
    theme = session.get('theme', 'light')
    
    conn = sqlite3.connect('wishlist.db')
    wb_random = conn.execute('SELECT * FROM wb_items ORDER BY RANDOM() LIMIT 20').fetchall()
    total_wb = conn.execute('SELECT COUNT(*) FROM wb_items').fetchone()[0]
    conn.close()
    
    wb_html = ''
    for item in wb_random:
        wb_html += f'''
        <div class="item-card">
            <div class="item-image"><img src="{item[5]}" alt="{item[1]}" onerror="this.parentElement.innerHTML='🎁'"></div>
            <div class="item-content">
                <h3 class="item-title">{item[1]}</h3>
                <div class="item-price">💰 {item[3]} {item[4]}</div>
                <p class="item-description">{item[2]}</p>
                <span class="badge badge-wb" style="margin-bottom: 10px; display: inline-block;">{item[7]}</span>
                <a href="{item[6]}" target="_blank" class="btn btn-sm" style="margin-bottom: 8px; display: block;">🔗 На WB</a>
                <a href="/add_wb_to_wishlist/{item[0]}" class="btn btn-success btn-sm btn-block">➕ В мой виш</a>
            </div>
        </div>
        '''
    
    content = f'''
    <div class="flex-between mb-4">
        <div>
            <h1 style="font-size: 32px;">🎲 WB Рандом</h1>
            <p style="color: var(--text-secondary);">Всего товаров в базе: {total_wb}</p>
        </div>
        <a href="/wb_random" class="btn btn-warning btn-lg">🔄 Обновить</a>
    </div>
    
    <div class="card" style="background: linear-gradient(135deg, rgba(203, 17, 171, 0.1) 0%, rgba(139, 10, 175, 0.1) 100%); border: 2px solid rgba(203, 17, 171, 0.3);">
        <h2 style="margin-bottom: 12px;">🎁 Случайные товары с Wildberries</h2>
        <p style="color: var(--text-secondary);">Каждый раз новые 20 товаров! Добавляй в свой виш одним кликом.</p>
    </div>
    
    <div class="grid">{wb_html}</div>
    '''
    
    return render_template_string(HTML_BASE, theme=theme, title='WB Рандом', content=content)

@app.route('/add_wb_to_wishlist/<int:wb_id>')
def add_wb_to_wishlist(wb_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    wb_item = conn.execute('SELECT * FROM wb_items WHERE id=?', (wb_id,)).fetchone()
    
    if wb_item:
        wishlist = conn.execute('SELECT slug FROM wishlists WHERE user_id=? ORDER BY is_default DESC, id ASC LIMIT 1', 
                               (session['user_id'],)).fetchone()
        
        if not wishlist:
            slug = slugify(f"{session['username']}-main")
            conn.execute('''INSERT INTO wishlists (user_id, title, slug, is_default, created_at) 
                           VALUES (?, ?, ?, 1, ?)''',
                        (session['user_id'], 'Мой виш', slug, datetime.now().date()))
            conn.commit()
            wishlist = conn.execute('SELECT slug FROM wishlists WHERE user_id=? ORDER BY is_default DESC LIMIT 1', 
                                   (session['user_id'],)).fetchone()
        
        wishlist_id = conn.execute('SELECT id FROM wishlists WHERE user_id=? ORDER BY is_default DESC LIMIT 1', 
                                  (session['user_id'],)).fetchone()[0]
        
        conn.execute('''INSERT INTO wishlist_items 
                        (wishlist_id, title, description, link, price, currency, image_url, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (wishlist_id, wb_item[1], wb_item[2], wb_item[6], wb_item[3], wb_item[4], wb_item[5], datetime.now().date()))
        conn.commit()
        flash(f'✨ Добавлено в виш!', 'success')
    conn.close()
    return redirect(request.referrer or url_for('wb_random'))

@app.route('/add_item_from_idea/<int:idea_id>')
def add_from_idea(idea_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    idea = conn.execute('SELECT * FROM ideas WHERE id=?', (idea_id,)).fetchone()
    
    if idea:
        wishlist = conn.execute('SELECT id FROM wishlists WHERE user_id=? ORDER BY is_default DESC, id ASC LIMIT 1', 
                               (session['user_id'],)).fetchone()
        
        if not wishlist:
            slug = slugify(f"{session['username']}-main")
            conn.execute('''INSERT INTO wishlists (user_id, title, slug, is_default, created_at) 
                           VALUES (?, ?, ?, 1, ?)''',
                        (session['user_id'], 'Мой виш', slug, datetime.now().date()))
            conn.commit()
            wishlist = conn.execute('SELECT id FROM wishlists WHERE user_id=? ORDER BY is_default DESC LIMIT 1', 
                                   (session['user_id'],)).fetchone()
        
        wishlist_id = conn.execute('SELECT id FROM wishlists WHERE user_id=? ORDER BY is_default DESC LIMIT 1', 
                                  (session['user_id'],)).fetchone()[0]
        
        conn.execute('''INSERT INTO wishlist_items 
                        (wishlist_id, title, description, link, price, currency, image_url, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (wishlist_id, idea[1], idea[2], idea[6], idea[3], idea[4], idea[5], datetime.now().date()))
        conn.commit()
        flash(f'✨ Добавлено в виш!', 'success')
    conn.close()
    return redirect(url_for('ideas'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        
        if action == 'save':
            theme = request.form['theme']
            currency = request.form['currency']
            
            conn = sqlite3.connect('wishlist.db')
            conn.execute('UPDATE users SET theme=?, currency=? WHERE id=?',
                        (theme, currency, session['user_id']))
            conn.commit()
            conn.close()
            
            session['theme'] = theme
            session['currency'] = currency
            flash('💾 Настройки сохранены!', 'success')
        
        elif action == 'change_password':
            old_password = request.form.get('old_password', '')
            new_password = request.form.get('new_password', '')
            
            if len(new_password) < 4:
                flash('Пароль минимум 4 символа', 'error')
                return redirect(url_for('settings'))
            
            conn = sqlite3.connect('wishlist.db')
            user = conn.execute('SELECT password FROM users WHERE id=?', (session['user_id'],)).fetchone()
            
            if user[0] != hashlib.sha256(old_password.encode()).hexdigest():
                flash('❌ Неверный текущий пароль', 'error')
                conn.close()
                return redirect(url_for('settings'))
            
            new_hash = hashlib.sha256(new_password.encode()).hexdigest()
            conn.execute('UPDATE users SET password=? WHERE id=?', (new_hash, session['user_id']))
            conn.commit()
            conn.close()
            flash('🔐 Пароль изменён!', 'success')
        
        return redirect(url_for('settings'))
    
    user_theme = session.get('theme', 'light')
    user_currency = session.get('currency', 'BYN')
    
    theme_options = ''.join([f'<option value="{code}" {"selected" if code == user_theme else ""}>{name}</option>' for code, name in THEMES.items()])
    currency_options = ''.join([f'<option value="{code}" {"selected" if code == user_currency else ""}>{name}</option>' for code, name in CURRENCIES.items()])
    
    conn = sqlite3.connect('wishlist.db')
    user = conn.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    wishlists_count = conn.execute('SELECT COUNT(*) FROM wishlists WHERE user_id=?', (session['user_id'],)).fetchone()[0]
    items_count = conn.execute('SELECT COUNT(*) FROM wishlist_items i JOIN wishlists w ON i.wishlist_id=w.id WHERE w.user_id=?', (session['user_id'],)).fetchone()[0]
    conn.close()
    
    content = f'''
    <h1 style="margin-bottom: 30px;">⚙️ Настройки</h1>
    
    <div class="grid-2">
        <div class="card animate-slide">
            <h2 style="margin-bottom: 20px;">🎨 Оформление</h2>
            <form method="POST">
                <input type="hidden" name="action" value="save">
                <div class="form-group">
                    <label>Тема</label>
                    <select name="theme">{theme_options}</select>
                </div>
                <div class="form-group">
                    <label>Валюта</label>
                    <select name="currency">{currency_options}</select>
                </div>
                <button type="submit" class="btn btn-block">💾 Сохранить</button>
            </form>
        </div>
        
        <div class="card animate-slide" style="animation-delay: 0.1s;">
            <h2 style="margin-bottom: 20px;">👤 Профиль</h2>
            <p style="margin-bottom: 8px;"><b>Имя:</b> {session['username']}</p>
            <p style="margin-bottom: 8px;"><b>Email:</b> {user[3] or 'не указан'}</p>
            <p style="margin-bottom: 8px;"><b>Регистрация:</b> {user[6]}</p>
            <p style="margin-bottom: 8px;"><b>Входов:</b> {user[10]}</p>
            <p style="margin-bottom: 16px;"><b>Вишей:</b> {wishlists_count} | <b>Желаний:</b> {items_count}</p>
        </div>
    </div>
    
    <div class="card animate-slide" style="animation-delay: 0.2s;">
        <h2 style="margin-bottom: 20px;">🔐 Сменить пароль</h2>
        <form method="POST" style="max-width: 500px;">
            <input type="hidden" name="action" value="change_password">
            <div class="form-group">
                <label>Текущий пароль</label>
                <input type="password" name="old_password" required>
            </div>
            <div class="form-group">
                <label>Новый пароль</label>
                <input type="password" name="new_password" required minlength="4">
            </div>
            <button type="submit" class="btn">Сменить пароль</button>
        </form>
    </div>
    '''
    
    return render_template_string(HTML_BASE, theme=user_theme, title='Настройки', content=content)


@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('wishlist.db')
    users_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    wishlists_count = conn.execute('SELECT COUNT(*) FROM wishlists').fetchone()[0]
    items_count = conn.execute('SELECT COUNT(*) FROM wishlist_items').fetchone()[0]
    ideas_count = conn.execute('SELECT COUNT(*) FROM ideas').fetchone()[0]
    wb_count = conn.execute('SELECT COUNT(*) FROM wb_items').fetchone()[0]
    reservations_count = conn.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]
    
    recent_users = conn.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 5').fetchall()
    conn.close()
    
    recent_users_html = ''.join([f'''
        <tr>
            <td>{u[0]}</td>
            <td><b>{u[1]}</b></td>
            <td>{u[3] or '-'}</td>
            <td>{u[6]}</td>
            <td>{"🚫" if u[8] else "✅"}</td>
        </tr>
    ''' for u in recent_users])
    
    content = f'''
    <div class="flex-between mb-4">
        <div>
            <h1 style="font-size: 32px;">🔧 Админ-панель</h1>
            <p style="color: var(--text-secondary);">Привет, {session['username']}!</p>
        </div>
    </div>
    
    <div class="grid" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); margin-bottom: 30px;">
        <div class="stat-card animate-scale">
            <div style="font-size: 32px; margin-bottom: 8px;">👥</div>
            <div class="stat-number">{users_count}</div>
            <div class="stat-label">Пользователей</div>
        </div>
        <div class="stat-card animate-scale">
            <div style="font-size: 32px; margin-bottom: 8px;">🎁</div>
            <div class="stat-number">{wishlists_count}</div>
            <div class="stat-label">Вишей</div>
        </div>
        <div class="stat-card animate-scale">
            <div style="font-size: 32px; margin-bottom: 8px;">⭐</div>
            <div class="stat-number">{items_count}</div>
            <div class="stat-label">Желаний</div>
        </div>
        <div class="stat-card animate-scale">
            <div style="font-size: 32px; margin-bottom: 8px;">💡</div>
            <div class="stat-number">{ideas_count}</div>
            <div class="stat-label">Идей</div>
        </div>
        <div class="stat-card animate-scale">
            <div style="font-size: 32px; margin-bottom: 8px;">🛍️</div>
            <div class="stat-number">{wb_count}</div>
            <div class="stat-label">Товаров WB</div>
        </div>
        <div class="stat-card animate-scale">
            <div style="font-size: 32px; margin-bottom: 8px;">🎯</div>
            <div class="stat-number">{reservations_count}</div>
            <div class="stat-label">Броней</div>
        </div>
    </div>
    
    <div class="card">
        <h2 style="margin-bottom: 20px;">👥 Последние пользователи</h2>
        <div class="table-responsive">
            <table>
                <thead><tr><th>ID</th><th>Имя</th><th>Email</th><th>Дата</th><th>Статус</th></tr></thead>
                <tbody>{recent_users_html}</tbody>
            </table>
        </div>
    </div>
    '''
    
    return render_template_string(HTML_BASE, theme=session.get('theme', 'dark'), title='Админка', content=content)

@app.route('/admin/users')
def admin_users():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('wishlist.db')
    users = conn.execute('''SELECT u.*, 
                           (SELECT COUNT(*) FROM wishlists WHERE user_id=u.id) as wishlists_count,
                           (SELECT COUNT(*) FROM wishlist_items i JOIN wishlists w ON i.wishlist_id=w.id WHERE w.user_id=u.id) as items_count
                           FROM users u ORDER BY u.created_at DESC''').fetchall()
    conn.close()
    
    users_html = ''.join([f'''
        <tr>
            <td>{u[0]}</td>
            <td><b>{u[1]}</b></td>
            <td>{u[3] or '-'}</td>
            <td>{u[6]}</td>
            <td>{u[10]}</td>
            <td>{u[11]}</td>
            <td>{u[12]}</td>
            <td>
                {"<span class='badge badge-danger'>🚫 Бан</span>" if u[8] else "<span class='badge badge-success'>✅ OK</span>"}
                {"<span class='badge badge-primary'>⚡</span>" if u[7] else ""}
            </td>
            <td>
                <a href="/admin/user/{u[0]}/toggle_ban" class="btn btn-sm {"btn-success" if u[8] else "btn-warning"}">
                    {"✅ Разбан" if u[8] else "🚫 Бан"}
                </a>
            </td>
        </tr>
    ''' for u in users])
    
    content = f'''
    <div class="flex-between mb-4">
        <h1>👥 Пользователи ({len(users)})</h1>
        <a href="/admin" class="btn btn-secondary">← Назад</a>
    </div>
    <div class="card">
        <div class="table-responsive">
            <table>
                <thead><tr><th>ID</th><th>Имя</th><th>Email</th><th>Рег.</th><th>Входов</th><th>Вишей</th><th>Желаний</th><th>Статус</th><th>Действия</th></tr></thead>
                <tbody>{users_html}</tbody>
            </table>
        </div>
    </div>
    '''
    
    return render_template_string(HTML_BASE, theme=session.get('theme', 'dark'), title='Пользователи', content=content)

@app.route('/admin/user/<int:user_id>/toggle_ban')
def admin_toggle_ban(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    if user_id == session['user_id']:
        flash('Нельзя забанить самого себя!', 'error')
        return redirect(url_for('admin_users'))
    
    conn = sqlite3.connect('wishlist.db')
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    
    if user:
        new_status = 0 if user[8] else 1
        conn.execute('UPDATE users SET is_banned=? WHERE id=?', (new_status, user_id))
        conn.commit()
        flash(f'{"✅ Разбанен" if new_status == 0 else "🚫 Забанен"}: {user[1]}', 'success')
    
    conn.close()
    return redirect(url_for('admin_users'))

@app.route('/u/<username>')
def public_wishlist(username):
    conn = sqlite3.connect('wishlist.db')
    user = conn.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    if not user:
        flash('Пользователь не найден', 'error')
        conn.close()
        return redirect(url_for('index'))
    
    wishlist = conn.execute('SELECT slug FROM wishlists WHERE user_id=? AND is_public=1 ORDER BY is_default DESC LIMIT 1', 
                           (user[0],)).fetchone()
    conn.close()
    
    if wishlist:
        return redirect(url_for('view_wishlist', slug=wishlist[0]))
    else:
        flash('У пользователя нет публичных вишей', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    print(f'✅ WishList Pro запущен!')
    print(f'🌐 URL: {BASE_URL}')
    print(f'👤 Админ: {ADMIN_USERNAME} / {ADMIN_PASSWORD}')
    print(f'🧮 Математическая капча включена')
    app.run(host='0.0.0.0', port=PORT, debug=True)