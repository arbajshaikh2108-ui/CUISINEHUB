import os
import json
import urllib.parse
import urllib.request
import uuid

from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, request, session, send_from_directory
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

# Always load backend/.env
load_dotenv(os.path.join(BACKEND_DIR, '.env'))


# ============================================================
# FLASK
# ============================================================

app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=''
)

app.secret_key = os.getenv(
    'SECRET_KEY',
    'cuisinehub-dev-secret-change-me'
)


# ============================================================
# MYSQL
# ============================================================

DB_NAME = os.getenv('MYSQL_DATABASE', 'cuisinehub')

DB_CONFIG = {
    'host': os.getenv('MYSQL_HOST', '127.0.0.1'),
    'port': int(os.getenv('MYSQL_PORT', '3306')),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'Arbaz@123'),
    'database': DB_NAME,
}

ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@cuisinehub.local').strip().lower()
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Admin@12345')
ACTIVE_WINDOW_MINUTES = int(os.getenv('ACTIVE_WINDOW_MINUTES', '2'))




# ============================================================
# YOUTUBE VIDEO RESOLUTION
# ============================================================

YOUTUBE_SEARCH_PREFIX = 'https://www.youtube.com/results?search_query='


def youtube_video_id(value):
    """Return a YouTube video ID from watch/youtu.be/embed/shorts/live URLs."""
    value = str(value or '').strip()
    if not value:
        return ''

    try:
        parsed = urllib.parse.urlparse(value)
        host = parsed.netloc.lower().replace('www.', '')
        if host == 'youtu.be':
            return parsed.path.strip('/').split('/')[0]
        if host in {'youtube.com', 'm.youtube.com', 'youtube-nocookie.com'}:
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get('v'):
                return qs['v'][0]
            parts = [x for x in parsed.path.split('/') if x]
            if len(parts) >= 2 and parts[0] in {'embed', 'shorts', 'live'}:
                return parts[1]
    except Exception:
        pass

    return ''


def youtube_watch_url(video_id):
    video_id = str(video_id or '').strip()
    return f'https://www.youtube.com/watch?v={video_id}' if video_id else ''


def resolve_youtube_video(recipe_name, current_url=''):
    """
    Resolve any recipe to a direct YouTube watch URL.

    Existing direct YouTube URLs are checked first. Search-result URLs are
    resolved with yt-dlp and the first matching video is cached by the caller.
    """
    current_id = youtube_video_id(current_url)

    try:
        import yt_dlp
    except Exception as exc:
        print(f'[YouTube] yt-dlp unavailable: {exc}')
        return youtube_watch_url(current_id), current_id

    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'extract_flat': True,
    }

    # Validate the existing direct URL first. A dead/removed video gets
    # replaced automatically by a fresh search result.
    if current_id:
        direct = youtube_watch_url(current_id)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(direct, download=False)
                if info and (info.get('id') or info.get('webpage_url')):
                    fresh_id = info.get('id') or youtube_video_id(info.get('webpage_url'))
                    fresh_url = youtube_watch_url(fresh_id) if fresh_id else direct
                    return fresh_url, fresh_id or current_id
        except Exception as exc:
            print(f'[YouTube] Existing video failed for {recipe_name!r}: {exc}')

    # Search every recipe by name. This is what converts old
    # youtube.com/results?search_query=... values into direct videos.
    query = f'ytsearch1:{recipe_name} recipe cooking tutorial'
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = info.get('entries') if isinstance(info, dict) else None
            entry = next((x for x in (entries or []) if x), None)
            if not entry:
                return '', ''

            vid = entry.get('id') or youtube_video_id(entry.get('webpage_url'))
            url = youtube_watch_url(vid)
            return url, vid
    except Exception as exc:
        print(f'[YouTube] Search failed for {recipe_name!r}: {exc}')
        return '', ''


# ============================================================
# DATABASE SCHEMA
# ============================================================

SCHEMA = [

'''
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'USER',
    plan ENUM('FREE','PREMIUM','CUISINE') NOT NULL DEFAULT 'FREE',
    selected_cuisine VARCHAR(50) NULL,
    free_recipes_left INT NOT NULL DEFAULT 2,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB
''',

'''
CREATE TABLE IF NOT EXISTS visitor_activity (
    visitor_id VARCHAR(64) NOT NULL,
    visit_date DATE NOT NULL,
    user_id INT NULL,
    first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_path VARCHAR(255) NULL,
    PRIMARY KEY(visitor_id, visit_date),
    INDEX idx_visitor_last_seen(last_seen),
    INDEX idx_visitor_user(user_id),
    CONSTRAINT fk_visitor_user
        FOREIGN KEY(user_id) REFERENCES users(id)
        ON DELETE SET NULL
) ENGINE=InnoDB
''',

'''
CREATE TABLE IF NOT EXISTS recipes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    cuisine VARCHAR(60) NOT NULL,
    category VARCHAR(30) NOT NULL,
    diet VARCHAR(30) NOT NULL,
    prep_time INT NOT NULL,
    difficulty VARCHAR(20) NOT NULL,
    calories INT NOT NULL,
    protein DECIMAL(8,2) NOT NULL,
    carbs DECIMAL(8,2) NOT NULL,
    fats DECIMAL(8,2) NOT NULL,
    image_url TEXT,
    video_url TEXT,
    description TEXT,
    ingredients TEXT NOT NULL,
    instructions TEXT NOT NULL,
    is_premium TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB
''',

'''
CREATE TABLE IF NOT EXISTS favorites (
    user_id INT NOT NULL,
    recipe_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, recipe_id),
    FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,
    FOREIGN KEY(recipe_id)
        REFERENCES recipes(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
''',

'''
CREATE TABLE IF NOT EXISTS reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    recipe_id INT NOT NULL,
    rating TINYINT NOT NULL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY one_review_per_user(user_id, recipe_id),
    FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,
    FOREIGN KEY(recipe_id)
        REFERENCES recipes(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
''',

'''
CREATE TABLE IF NOT EXISTS recipe_views (
    user_id INT NOT NULL,
    recipe_id INT NOT NULL,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, recipe_id),
    FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,
    FOREIGN KEY(recipe_id)
        REFERENCES recipes(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
'''

]


# ============================================================
# INITIAL SAMPLE RECIPES
# ============================================================

SEED_RECIPES = [('Butter Chicken',
  'Indian',
  'Dinner',
  'Non-Vegetarian',
  45,
  'Medium',
  520,
  34,
  18,
  31,
  'https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/embed/KpqP43npDnQ',
  'Creamy tomato chicken with aromatic spices.',
  'Chicken breast\nTomato puree\nYogurt\nButter\nGaram masala\nCream',
  'Marinate chicken with yogurt and spices.\n'
  'Sear until golden.\n'
  'Cook tomato base with butter and spices.\n'
  'Add chicken and simmer.\n'
  'Finish with cream and coriander.',
  1),
 ('Paneer Tikka',
  'Indian',
  'Snack',
  'Vegetarian',
  30,
  'Easy',
  310,
  22,
  12,
  18,
  'https://images.unsplash.com/photo-1567188040759-fb8a883dc6d8?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Paneer+Tikka+recipe',
  'Smoky yogurt-marinated paneer skewers.',
  'Paneer\nHung curd\nCapsicum\nOnion\nTikka masala',
  'Mix marinade.\nCoat paneer and vegetables.\nRest for 20 minutes.\nGrill or air-fry until charred.',
  1),
 ('Chole Masala',
  'Indian',
  'Lunch',
  'Vegetarian',
  40,
  'Easy',
  390,
  18,
  54,
  9,
  'https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/embed/LoGSdcCYjp0',
  'Protein-rich chickpea curry.',
  'Chickpeas\nOnion\nTomato\nGinger garlic\nChole masala',
  'Soak and pressure-cook chickpeas.\nPrepare onion-tomato masala.\nAdd spices and chickpeas.\nSimmer for 15 minutes.',
  1),
 ('Chicken Biryani',
  'Indian',
  'Dinner',
  'Non-Vegetarian',
  60,
  'Medium',
  610,
  36,
  61,
  21,
  'https://images.unsplash.com/photo-1563379926898-05f4575a45d8?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Chicken+Biryani+recipe',
  'Fragrant basmati rice layered with spiced chicken and saffron.',
  'Chicken\nBasmati rice\nYogurt\nOnion\nBiryani masala\nSaffron',
  'Marinate chicken with yogurt and spices.\nParboil rice.\nCook chicken masala.\nLayer rice over chicken.\nDum cook until aromatic.',
  1),
 ('Kung Pao Chicken',
  'Chinese',
  'Dinner',
  'Non-Vegetarian',
  35,
  'Medium',
  460,
  36,
  28,
  22,
  'https://images.unsplash.com/photo-1603133872878-684f208fb84b?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/embed/tjVu_2eQ9SE',
  'Spicy stir-fried chicken with peanuts.',
  'Chicken\nPeanuts\nBell pepper\nSoy sauce\nChilli\nGarlic',
  'Marinate chicken.\nStir-fry chicken on high heat.\nAdd vegetables and sauce.\nFinish with peanuts and spring onion.',
  1),
 ('Veg Hakka Noodles',
  'Chinese',
  'Lunch',
  'Vegetarian',
  25,
  'Easy',
  340,
  11,
  52,
  10,
  'https://images.unsplash.com/photo-1585032226651-759b368d7246?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Vegetable+Hakka+Noodles+recipe',
  'Fast wok-tossed noodles with vegetables.',
  'Noodles\nCabbage\nCarrot\nCapsicum\nSoy sauce',
  'Boil noodles.\nStir-fry vegetables.\nAdd noodles and sauces.\nToss on high heat.',
  1),
 ('Chicken Manchurian',
  'Chinese',
  'Dinner',
  'Non-Vegetarian',
  35,
  'Medium',
  470,
  30,
  34,
  22,
  'https://images.unsplash.com/photo-1544025162-d76694265947?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/embed/irAcXcDtaYw',
  'Crispy chicken tossed in a glossy, spicy Indo-Chinese Manchurian sauce.',
  'Chicken\nCorn flour\nGarlic\nSpring onion\nSoy sauce\nChilli sauce',
  'Coat chicken and fry.\nSaute garlic and spring onion.\nAdd sauces.\nToss fried chicken in the sauce.\nServe hot.',
  1),
 ('Vegetable Fried Rice',
  'Chinese',
  'Lunch',
  'Vegetarian',
  25,
  'Easy',
  320,
  9,
  49,
  10,
  'https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Vegetable+Fried+Rice+recipe',
  'Wok-tossed rice packed with crunchy vegetables and Asian seasonings.',
  'Cooked rice\nCarrot\nBeans\nCapsicum\nSoy sauce\nSpring onion',
  'Chill cooked rice.\nStir-fry vegetables on high heat.\nAdd rice and soy sauce.\nToss quickly.\nFinish with spring onion.',
  0),
 ('Margherita Pizza',
  'Italian',
  'Dinner',
  'Vegetarian',
  30,
  'Medium',
  410,
  17,
  48,
  17,
  'https://images.unsplash.com/photo-1574071318508-1cdbab80d002?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/embed/vcfNpDtVqOw',
  'Classic tomato, mozzarella and basil pizza.',
  'Pizza dough\nTomato sauce\nMozzarella\nBasil\nOlive oil',
  'Stretch dough.\nSpread sauce.\nAdd mozzarella.\nBake at high heat until blistered.\nFinish with basil.',
  1),
 ('Chicken Alfredo Pasta',
  'Italian',
  'Dinner',
  'Non-Vegetarian',
  35,
  'Easy',
  570,
  32,
  54,
  27,
  'https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Chicken+Alfredo+Pasta+recipe',
  'Creamy fettuccine with tender chicken, garlic and Parmesan.',
  'Fettuccine\nChicken breast\nCream\nParmesan\nGarlic\nButter',
  'Cook pasta.\nSeason and sear chicken.\nMake garlic cream sauce.\nAdd Parmesan.\nToss pasta and chicken together.',
  1),
 ('Pasta Arrabbiata',
  'Italian',
  'Lunch',
  'Vegetarian',
  25,
  'Easy',
  390,
  13,
  56,
  12,
  'https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/embed/6YF3zsZwFVc',
  'Spicy tomato pasta with garlic, olive oil and chilli.',
  'Penne pasta\nTomatoes\nGarlic\nRed chilli\nOlive oil\nParsley',
  'Cook pasta.\nSaute garlic and chilli.\nAdd tomato and simmer.\nToss pasta in the sauce.\nFinish with parsley.',
  0),
 ('Chicken Parmesan',
  'Italian',
  'Dinner',
  'Non-Vegetarian',
  45,
  'Medium',
  540,
  40,
  30,
  24,
  'https://images.unsplash.com/photo-1547592166-23ac45744acd?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Chicken+Parmesan+recipe',
  'Crispy breaded chicken baked with tomato sauce and melted cheese.',
  'Chicken breast\nBreadcrumbs\nParmesan\nTomato sauce\nMozzarella\nEgg',
  'Bread chicken.\nPan-fry until golden.\nTop with tomato sauce and cheese.\nBake until bubbling.\nServe warm.',
  1),
 ('Beef Tacos',
  'Mexican',
  'Dinner',
  'Non-Vegetarian',
  30,
  'Easy',
  440,
  29,
  32,
  21,
  'https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Beef+Tacos+recipe',
  'Loaded tacos with seasoned beef and fresh salsa.',
  'Minced beef\nTaco shells\nTomato\nOnion\nLime\nCheese',
  'Brown beef with taco spices.\nPrepare salsa.\nWarm shells.\nFill with beef, salsa and cheese.',
  1),
 ('Chicken Tacos',
  'Mexican',
  'Dinner',
  'Non-Vegetarian',
  30,
  'Easy',
  450,
  31,
  35,
  20,
  'https://images.unsplash.com/photo-1552332386-f8dd00dc2f85?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Chicken+Tacos+recipe',
  'Seasoned grilled chicken tucked into warm tortillas with salsa and lime.',
  'Chicken\nCorn tortillas\nTomato\nOnion\nLime\nAvocado',
  'Season chicken.\nGrill until cooked.\nSlice chicken.\nWarm tortillas.\nFill with chicken, salsa, lime and avocado.',
  1),
 ('Vegetarian Quesadilla',
  'Mexican',
  'Snack',
  'Vegetarian',
  20,
  'Easy',
  360,
  17,
  38,
  17,
  'https://images.unsplash.com/photo-1618040996337-56904b7850b9?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Vegetarian+Quesadilla+recipe',
  'Crisp tortillas filled with beans, vegetables and melted cheese.',
  'Tortillas\nBlack beans\nCapsicum\nCorn\nCheese\nSalsa',
  'Saute vegetables.\nPlace filling and cheese on tortilla.\nFold and toast on a pan.\nSlice and serve with salsa.',
  0),
 ('Mexican Bean Burrito',
  'Mexican',
  'Lunch',
  'Vegetarian',
  25,
  'Easy',
  390,
  16,
  51,
  12,
  'https://images.unsplash.com/photo-1626700051175-6818013e1d4f?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Mexican+Bean+Burrito+recipe',
  'Hearty burrito filled with spiced beans, rice, salsa and cheese.',
  'Flour tortillas\nBlack beans\nCooked rice\nCorn\nSalsa\nCheese',
  'Warm tortillas.\nSeason beans.\nLayer rice, beans, corn, salsa and cheese.\nFold tightly.\nToast lightly and serve.',
  0),
 ('Greek Yogurt Power Bowl',
  'Mediterranean',
  'Breakfast',
  'Vegetarian',
  10,
  'Easy',
  280,
  24,
  30,
  7,
  'https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Greek+Yogurt+Power+Bowl+recipe',
  'Quick high-protein breakfast bowl.',
  'Greek yogurt\nBanana\nBerries\nOats\nChia seeds\nHoney',
  'Add yogurt to bowl.\nTop with fruit, oats and seeds.\nDrizzle honey and serve.',
  0),
 ('Chicken Shawarma',
  'Mediterranean',
  'Dinner',
  'Non-Vegetarian',
  40,
  'Medium',
  480,
  38,
  34,
  20,
  'https://images.unsplash.com/photo-1529006557810-274b9b2fc783?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/embed/gkkh-yx_4Gc',
  'Spiced chicken shawarma served with warm pita and fresh salad.',
  'Chicken thighs\nYogurt\nGarlic\nPaprika\nCumin\nPita',
  'Mix chicken with yogurt and spices.\nMarinate.\nRoast or grill until browned.\nSlice thinly.\nServe in pita with salad and sauce.',
  1),
 ('Falafel',
  'Mediterranean',
  'Snack',
  'Vegetarian',
  35,
  'Medium',
  330,
  15,
  37,
  14,
  'https://images.unsplash.com/photo-1593001874117-c99c4e7f9c34?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/results?search_query=Falafel+recipe',
  'Crispy chickpea and herb fritters with tahini and salad.',
  'Dried chickpeas\nParsley\nCoriander\nGarlic\nCumin\nSesame tahini',
  'Soak chickpeas overnight.\nBlend with herbs and spices.\nShape into balls.\nFry or air-fry until crisp.\nServe with tahini.',
  0),
 ('Grilled Mediterranean Chicken',
  'Mediterranean',
  'Lunch',
  'Non-Vegetarian',
  30,
  'Easy',
  410,
  43,
  12,
  19,
  'https://images.unsplash.com/photo-1532550907401-a500c9a57435?auto=format&fit=crop&w=1000&q=80',
  'https://www.youtube.com/watch?v=S2Y1fXsQpgE',
  'Lemon-herb grilled chicken with garlic, oregano and olive oil.',
  'Chicken breast\nLemon\nGarlic\nOregano\nOlive oil\nParsley',
  'Make lemon-herb marinade.\nMarinate chicken.\nGrill until fully cooked.\nRest and slice.\nServe with salad.',
  0)]



# ============================================================
# MYSQL CONNECTION
# ============================================================

def get_connection(with_db=True):
    cfg = dict(DB_CONFIG)

    if not with_db:
        cfg.pop('database', None)

    return mysql.connector.connect(**cfg)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = None
    cur = None

    try:

        conn = get_connection(False)
        cur = conn.cursor()

        cur.execute(
            f"""
            CREATE DATABASE IF NOT EXISTS `{DB_NAME}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
            """
        )

        conn.commit()

        cur.close()
        conn.close()

        conn = get_connection(True)
        cur = conn.cursor()

        for statement in SCHEMA:
            cur.execute(statement)

        # Backward compatibility for existing databases created before role support.
        cur.execute("SHOW COLUMNS FROM users LIKE 'role'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'USER' AFTER password_hash")

        # Ensure the configured admin account exists and has a hashed password.
        admin_hash = generate_password_hash(ADMIN_PASSWORD)
        cur.execute('SELECT id FROM users WHERE email=%s', (ADMIN_EMAIL,))
        admin_row = cur.fetchone()

        if admin_row:
            cur.execute(
                "UPDATE users SET name=%s, password_hash=%s, role='ADMIN' WHERE email=%s",
                ('Administrator', admin_hash, ADMIN_EMAIL)
            )
        else:
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role, plan) VALUES (%s,%s,%s,'ADMIN','FREE')",
                ('Administrator', ADMIN_EMAIL, admin_hash)
            )

        # Keep the demo recipe catalogue synced on both fresh and existing databases.
        # Old sample-only rows are removed so every cuisine stays at exactly four recipes.
        cur.execute(
            "DELETE FROM recipes WHERE name IN (%s,%s,%s,%s)",
            ('Mushroom Risotto','Greek Salad','Grilled Chicken Salad','Mapo Tofu')
        )

        sql = '''
        INSERT INTO recipes
        (
            name,cuisine,category,diet,prep_time,difficulty,calories,protein,carbs,fats,
            image_url,video_url,description,ingredients,instructions,is_premium
        )
        VALUES
        (
            %s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,%s,%s
        )
        '''

        for recipe in SEED_RECIPES:
            cur.execute(
                'SELECT id FROM recipes WHERE name=%s AND cuisine=%s LIMIT 1',
                (recipe[0], recipe[1])
            )
            if cur.fetchone():
                cur.execute(
                    'UPDATE recipes SET video_url=%s, image_url=%s WHERE name=%s AND cuisine=%s',
                    (recipe[11], recipe[10], recipe[0], recipe[1])
                )
            else:
                cur.execute(sql, recipe)

        conn.commit()

    finally:

        if cur:
            cur.close()

        if conn and conn.is_connected():
            conn.close()


# ============================================================
# GENERIC DB QUERY
# ============================================================

def db_query(sql, params=(), fetch=True, dictionary=True):

    conn = get_connection(True)

    cur = conn.cursor(dictionary=dictionary)

    try:

        cur.execute(sql, params)

        if fetch:
            return cur.fetchall()

        conn.commit()

        return cur.lastrowid

    finally:

        cur.close()
        conn.close()


# ============================================================
# CURRENT USER
# ============================================================

def current_user():

    uid = session.get('user_id')

    if not uid:
        return None

    rows = db_query(
        '''
        SELECT
            id,
            name,
            email,
            role,
            plan,
            selected_cuisine,
            free_recipes_left,
            created_at
        FROM users
        WHERE id=%s
        ''',
        (uid,)
    )

    return rows[0] if rows else None


# ============================================================
# LOGIN REQUIRED
# ============================================================

def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not current_user():
            return jsonify({
                'error': 'Login required'
            }), 401

        return fn(*args, **kwargs)

    return wrapper


# ============================================================
# ADMIN AUTHENTICATION
# ============================================================

def admin_current_user():

    uid = session.get('admin_id')

    if not uid:
        return None

    rows = db_query(
        '''
        SELECT id, name, email, role, plan, created_at
        FROM users
        WHERE id=%s AND role='ADMIN'
        ''',
        (uid,)
    )

    return rows[0] if rows else None


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not admin_current_user():
            return jsonify({'error': 'Admin login required'}), 401

        return fn(*args, **kwargs)

    return wrapper


# ============================================================
# RECIPE ACCESS
# ============================================================

def recipe_allowed(user, recipe):

    if not recipe.get('is_premium'):
        return True

    if user and user['plan'] == 'PREMIUM':
        return True

    if (
        user
        and user['plan'] == 'CUISINE'
        and user.get('selected_cuisine') == recipe['cuisine']
    ):
        return True

    return False


# ============================================================
# RECIPE IMAGE SEARCH
# ============================================================

def get_recipe_image(recipe_name):

    """
    Search TheMealDB using the actual recipe name.

    Example:
        Butter Chicken -> matching Butter Chicken image
        Paneer Tikka -> matching Paneer Tikka image

    Returns image URL or None.
    """

    try:

        clean_name = recipe_name.strip()

        if not clean_name:
            return None

        encoded_name = urllib.parse.quote(clean_name)

        url = (
            'https://www.themealdb.com/api/json/v1/1/search.php?s='
            + encoded_name
        )

        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'CuisineHub/1.0'
            }
        )

        with urllib.request.urlopen(req, timeout=5) as response:

            raw_data = response.read().decode('utf-8')

            data = json.loads(raw_data)

        meals = data.get('meals')

        if meals:

            image = meals[0].get('strMealThumb')

            if image:
                return image

    except Exception as e:

        print(
            f'[IMAGE] Could not find image for "{recipe_name}": {e}'
        )

    return None


# ============================================================
# UPDATE MISSING RECIPE IMAGES
# ============================================================

def ensure_recipe_image(recipe):

    """
    If recipe has no useful image, search by recipe name.

    We deliberately do NOT replace a valid stored image every
    time the API is called.
    """

    current_image = recipe.get('image_url')

    if current_image and str(current_image).strip():

        return recipe

    image = get_recipe_image(recipe.get('name', ''))

    if image:

        recipe['image_url'] = image

        try:

            db_query(
                '''
                UPDATE recipes
                SET image_url=%s
                WHERE id=%s
                ''',
                (
                    image,
                    recipe['id']
                ),
                fetch=False
            )

        except Exception as e:

            print(
                f'[IMAGE] Database save failed: {e}'
            )

    return recipe


# ============================================================
# VISITOR ACTIVITY / HEARTBEAT
# ============================================================

@app.route('/api/activity', methods=['POST'])
def activity():

    visitor_id = request.cookies.get('visitor_id') or uuid.uuid4().hex
    user = current_user()
    user_id = user['id'] if user else None
    path = (request.get_json(silent=True) or {}).get('path', request.path)
    path = str(path)[:255]
    now = datetime.now()
    today = now.date()

    db_query(
        '''
        INSERT INTO visitor_activity
            (visitor_id, visit_date, user_id, first_seen, last_seen, last_path)
        VALUES
            (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            user_id=VALUES(user_id),
            last_seen=VALUES(last_seen),
            last_path=VALUES(last_path)
        ''',
        (visitor_id, today, user_id, now, now, path),
        fetch=False
    )

    response = jsonify({'ok': True, 'server_time': now.isoformat(timespec='seconds')})
    if not request.cookies.get('visitor_id'):
        response.set_cookie(
            'visitor_id',
            visitor_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite='Lax'
        )
    return response


# ============================================================
# HEALTH
# ============================================================

@app.route('/api/health')
def health():

    try:

        init_db()

        return jsonify({
            'ok': True,
            'database': 'connected'
        })

    except Exception as e:

        return jsonify({
            'ok': False,
            'database': str(e)
        }), 500


# ============================================================
# REGISTER
# ============================================================

@app.route('/api/register', methods=['POST'])
def register():

    data = request.get_json() or {}

    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not name or not email or len(password) < 6:

        return jsonify({
            'error': 'Name, email and password (6+ chars) are required'
        }), 400

    try:

        uid = db_query(
            '''
            INSERT INTO users
            (
                name,
                email,
                password_hash
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
            ''',
            (
                name,
                email,
                generate_password_hash(password)
            ),
            fetch=False
        )

        session['user_id'] = uid

        return jsonify({
            'message': 'Registration successful',
            'user': current_user()
        })

    except Error as e:

        if getattr(e, 'errno', None) == 1062:

            return jsonify({
                'error': 'Email already registered'
            }), 409

        return jsonify({
            'error': str(e)
        }), 500


# ============================================================
# LOGIN
# ============================================================

@app.route('/api/login', methods=['POST'])
def login():

    data = request.get_json() or {}

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    rows = db_query(
        'SELECT * FROM users WHERE email=%s',
        (email,)
    )

    if (
        not rows
        or not check_password_hash(
            rows[0]['password_hash'],
            password
        )
    ):

        return jsonify({
            'error': 'Invalid email or password'
        }), 401

    session['user_id'] = rows[0]['id']

    return jsonify({
        'message': 'Login successful',
        'user': current_user()
    })


# ============================================================
# LOGOUT
# ============================================================

@app.route('/api/logout', methods=['POST'])
def logout():

    session.clear()

    return jsonify({
        'message': 'Logged out'
    })


# ============================================================
# CURRENT USER API
# ============================================================

@app.route('/api/me')
def me():

    user = current_user()

    return jsonify({
        'user': user
    })


# ============================================================
# RECIPES API
# ============================================================

@app.route('/api/recipes')
def recipes():

    q = request.args.get('q', '').strip()
    cuisine = request.args.get('cuisine', '').strip()
    diet = request.args.get('diet', '').strip()
    category = request.args.get('category', '').strip()
    max_time = request.args.get('max_time', '').strip()
    high = request.args.get('high_protein', '') == '1'

    where = []
    params = []

    # Search
    if q:

        where.append(
            '(name LIKE %s OR description LIKE %s)'
        )

        params += [
            f'%{q}%',
            f'%{q}%'
        ]

    # Cuisine
    if cuisine:

        where.append(
            'cuisine=%s'
        )

        params.append(cuisine)

    # Diet
    if diet:

        where.append(
            'diet=%s'
        )

        params.append(diet)

    # Category
    if category:

        where.append(
            'category=%s'
        )

        params.append(category)

    # Preparation time
    if max_time.isdigit():

        where.append(
            'prep_time<=%s'
        )

        params.append(
            int(max_time)
        )

    # High protein
    if high:

        where.append(
            'protein>=20'
        )

    clause = (
        ' WHERE ' + ' AND '.join(where)
        if where
        else ''
    )

    rows = db_query(
        f'''
        SELECT
            r.*,
            COALESCE(
                ROUND(AVG(rv.rating),1),
                0
            ) AS rating,
            COUNT(rv.id) AS review_count

        FROM recipes r

        LEFT JOIN reviews rv
            ON r.id=rv.recipe_id

        {clause}

        GROUP BY r.id

        ORDER BY
            r.protein DESC,
            r.id DESC
        ''',
        tuple(params)
    )

    # --------------------------------------------------------
    # IMAGE HANDLING
    # --------------------------------------------------------

    for recipe in rows:

        ensure_recipe_image(recipe)

    return jsonify({
        'recipes': rows
    })


# ============================================================
# SINGLE RECIPE
# ============================================================

@app.route('/api/recipes/<int:rid>')
def recipe_detail(rid):

    rows = db_query(
        '''
        SELECT
            r.*,
            COALESCE(
                ROUND(AVG(rv.rating),1),
                0
            ) AS rating,
            COUNT(rv.id) AS review_count

        FROM recipes r

        LEFT JOIN reviews rv
            ON r.id=rv.recipe_id

        WHERE r.id=%s

        GROUP BY r.id
        ''',
        (rid,)
    )

    if not rows:

        return jsonify({
            'error': 'Recipe not found'
        }), 404

    recipe = rows[0]

    ensure_recipe_image(recipe)

    user = current_user()

    allowed = (
        recipe_allowed(user, recipe)
        if user
        else not recipe['is_premium']
    )

    return jsonify({
        'recipe': recipe,
        'locked': not allowed,
        'user': user
    })




# ============================================================
# DIRECT YOUTUBE VIDEO
# ============================================================

@app.route('/api/recipes/<int:rid>/youtube')
def recipe_youtube(rid):
    rows = db_query(
        'SELECT id, name, video_url FROM recipes WHERE id=%s',
        (rid,)
    )

    if not rows:
        return jsonify({'error': 'Recipe not found'}), 404

    recipe = rows[0]
    current_url = recipe.get('video_url') or ''
    video_url, video_id = resolve_youtube_video(recipe['name'], current_url)

    if video_url and video_id:
        # Cache the direct watch URL so the next visit is instant.
        db_query(
            'UPDATE recipes SET video_url=%s WHERE id=%s',
            (video_url, rid),
            fetch=False
        )

        return jsonify({
            'video_url': video_url,
            'video_id': video_id,
            'resolved': True,
        })

    # Keep an already-stored URL as a last-resort fallback.
    return jsonify({
        'video_url': current_url,
        'video_id': youtube_video_id(current_url),
        'resolved': False,
        'message': 'Direct YouTube video could not be resolved right now.'
    })


# ============================================================
# UNLOCK RECIPE
# ============================================================

@app.route('/api/recipes/<int:rid>/unlock', methods=['POST'])
@login_required
def unlock(rid):

    user = current_user()

    rows = db_query(
        'SELECT * FROM recipes WHERE id=%s',
        (rid,)
    )

    if not rows:

        return jsonify({
            'error': 'Recipe not found'
        }), 404

    recipe = rows[0]

    ensure_recipe_image(recipe)

    if recipe_allowed(user, recipe):

        return jsonify({
            'unlocked': True,
            'recipe': recipe
        })

    if user['free_recipes_left'] > 0:

        db_query(
            '''
            UPDATE users
            SET free_recipes_left=free_recipes_left-1
            WHERE id=%s
            ''',
            (user['id'],),
            fetch=False
        )

        return jsonify({
            'unlocked': True,
            'free_trial_used': True,
            'remaining': user['free_recipes_left'] - 1,
            'recipe': recipe
        })

    return jsonify({
        'unlocked': False,
        'error': 'Free recipe limit reached',
        'upgrade_required': True
    }), 403


# ============================================================
# FAVORITES
# ============================================================

@app.route('/api/favorites')
@login_required
def favorites():

    rows = db_query(
        '''
        SELECT
            r.*,
            COALESCE(
                ROUND(AVG(rv.rating),1),
                0
            ) AS rating

        FROM favorites f

        JOIN recipes r
            ON r.id=f.recipe_id

        LEFT JOIN reviews rv
            ON r.id=rv.recipe_id

        WHERE f.user_id=%s

        GROUP BY r.id

        ORDER BY f.created_at DESC
        ''',
        (
            current_user()['id'],
        )
    )

    for recipe in rows:

        ensure_recipe_image(recipe)

    return jsonify({
        'recipes': rows
    })


# ============================================================
# ADD / REMOVE FAVORITE
# ============================================================

@app.route('/api/favorites/<int:rid>', methods=['POST', 'DELETE'])
@login_required
def favorite(rid):

    uid = current_user()['id']

    if request.method == 'POST':

        db_query(
            '''
            INSERT IGNORE INTO favorites
            (
                user_id,
                recipe_id
            )
            VALUES
            (
                %s,
                %s
            )
            ''',
            (
                uid,
                rid
            ),
            fetch=False
        )

    else:

        db_query(
            '''
            DELETE FROM favorites
            WHERE user_id=%s
            AND recipe_id=%s
            ''',
            (
                uid,
                rid
            ),
            fetch=False
        )

    return jsonify({
        'ok': True
    })


# ============================================================
# REVIEWS
# ============================================================

@app.route('/api/reviews/<int:rid>', methods=['GET', 'POST'])
def reviews(rid):

    if request.method == 'GET':

        rows = db_query(
            '''
            SELECT
                rv.id,
                rv.rating,
                rv.comment,
                rv.created_at,
                u.name

            FROM reviews rv

            JOIN users u
                ON u.id=rv.user_id

            WHERE rv.recipe_id=%s

            ORDER BY rv.created_at DESC
            ''',
            (rid,)
        )

        return jsonify({
            'reviews': rows
        })

    user = current_user()

    if not user:

        return jsonify({
            'error': 'Login required'
        }), 401

    data = request.get_json() or {}

    rating = int(
        data.get(
            'rating',
            0
        )
    )

    comment = data.get(
        'comment',
        ''
    ).strip()

    if rating < 1 or rating > 5:

        return jsonify({
            'error': 'Rating must be 1-5'
        }), 400

    try:

        db_query(
            '''
            INSERT INTO reviews
            (
                user_id,
                recipe_id,
                rating,
                comment
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )

            ON DUPLICATE KEY UPDATE
                rating=VALUES(rating),
                comment=VALUES(comment)
            ''',
            (
                user['id'],
                rid,
                rating,
                comment
            ),
            fetch=False
        )

        return jsonify({
            'message': 'Review saved'
        })

    except Error as e:

        return jsonify({
            'error': str(e)
        }), 500


# ============================================================
# PROFILE
# ============================================================

@app.route('/api/profile', methods=['PUT'])
@login_required
def profile_update():

    user = current_user()

    data = request.get_json() or {}

    name = data.get(
        'name',
        user['name']
    ).strip()

    db_query(
        '''
        UPDATE users
        SET name=%s
        WHERE id=%s
        ''',
        (
            name,
            user['id']
        ),
        fetch=False
    )

    return jsonify({
        'user': current_user()
    })


# ============================================================
# SUBSCRIPTION
# ============================================================

@app.route('/api/subscription', methods=['POST'])
@login_required
def subscription():

    user = current_user()

    data = request.get_json() or {}

    plan = data.get('plan')
    cuisine = data.get('cuisine')

    if plan not in (
        'PREMIUM',
        'CUISINE'
    ):

        return jsonify({
            'error': 'Invalid plan'
        }), 400

    if plan == 'CUISINE' and not cuisine:

        return jsonify({
            'error': 'Choose a cuisine'
        }), 400

    db_query(
        '''
        UPDATE users
        SET
            plan=%s,
            selected_cuisine=%s
        WHERE id=%s
        ''',
        (
            plan,
            cuisine if plan == 'CUISINE' else None,
            user['id']
        ),
        fetch=False
    )

    return jsonify({
        'message': 'Plan activated for demo',
        'user': current_user()
    })


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route('/api/admin/login', methods=['POST'])
def admin_login():

    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    rows = db_query(
        'SELECT * FROM users WHERE email=%s AND role=\'ADMIN\'',
        (email,)
    )

    if not rows or not check_password_hash(rows[0]['password_hash'], password):
        return jsonify({'error': 'Invalid admin email or password'}), 401

    session['admin_id'] = rows[0]['id']

    return jsonify({
        'message': 'Admin login successful',
        'admin': admin_current_user()
    })


@app.route('/api/admin/me')
def admin_me():

    return jsonify({'admin': admin_current_user()})


@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():

    session.pop('admin_id', None)

    return jsonify({'message': 'Admin logged out'})


@app.route('/api/admin/dashboard')
@admin_required
def admin_dashboard():

    now = datetime.now()
    today = now.date()
    active_since = now - timedelta(minutes=ACTIVE_WINDOW_MINUTES)

    stats = db_query(
        '''
        SELECT
            (SELECT COUNT(*) FROM users WHERE role='USER') AS total_clients,
            (SELECT COUNT(*) FROM visitor_activity
             WHERE visit_date=%s AND last_seen >= %s) AS active_clients,
            (SELECT COUNT(*) FROM visitor_activity
             WHERE visit_date=%s) AS today_visits
        ''',
        (today, active_since, today)
    )[0]

    recent = db_query(
        '''
        SELECT
            va.visitor_id,
            COALESCE(u.name, 'Guest') AS name,
            COALESCE(u.email, 'Guest visitor') AS email,
            va.first_seen,
            va.last_seen,
            va.last_path
        FROM visitor_activity va
        LEFT JOIN users u ON u.id = va.user_id
        WHERE va.visit_date=%s
        ORDER BY va.last_seen DESC
        LIMIT 20
        ''',
        (today,)
    )

    def dt(value):
        return value.strftime('%Y-%m-%d %H:%M:%S') if value else None

    for row in recent:
        row['first_seen'] = dt(row['first_seen'])
        row['last_seen'] = dt(row['last_seen'])
        row['active'] = bool(
            row['last_seen'] and
            datetime.strptime(row['last_seen'], '%Y-%m-%d %H:%M:%S') >= active_since
        )
        row.pop('visitor_id', None)

    return jsonify({
        'stats': {
            'total_clients': int(stats['total_clients']),
            'active_clients': int(stats['active_clients']),
            'today_visits': int(stats['today_visits']),
            'active_window_minutes': ACTIVE_WINDOW_MINUTES,
            'server_time': now.strftime('%Y-%m-%d %H:%M:%S')
        },
        'recent_visits': recent
    })


# ============================================================
# ADMIN RECIPE
# ============================================================

@app.route('/api/admin/recipes', methods=['POST'])
@admin_required
def admin_recipe():

    data = request.get_json() or {}

    fields = [
        'name',
        'cuisine',
        'category',
        'diet',
        'prep_time',
        'difficulty',
        'calories',
        'protein',
        'carbs',
        'fats',
        'image_url',
        'video_url',
        'description',
        'ingredients',
        'instructions',
        'is_premium'
    ]

    vals = [
        data.get(field)
        for field in fields
    ]

    if not all(vals[:6]):

        return jsonify({
            'error': 'Required fields missing'
        }), 400

    # If admin doesn't provide image,
    # automatically search by recipe name.
    if not vals[10]:

        vals[10] = get_recipe_image(
            vals[0]
        )

    placeholders = ','.join(
        ['%s'] * len(fields)
    )

    rid = db_query(
        '''
        INSERT INTO recipes
        (
            name,
            cuisine,
            category,
            diet,
            prep_time,
            difficulty,
            calories,
            protein,
            carbs,
            fats,
            image_url,
            video_url,
            description,
            ingredients,
            instructions,
            is_premium
        )
        VALUES
        (
            ''' + placeholders + '''
        )
        ''',
        tuple(vals),
        fetch=False
    )

    return jsonify({
        'id': rid
    }), 201


# ============================================================
# FRONTEND
# ============================================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def frontend(path):

    if path.startswith('api/'):

        return jsonify({
            'error': 'API route not found'
        }), 404

    target = os.path.join(
        FRONTEND_DIR,
        path
    )

    if (
        path
        and os.path.isfile(target)
    ):

        return send_from_directory(
            FRONTEND_DIR,
            path
        )

    return send_from_directory(
        FRONTEND_DIR,
        'index.html'
    )


# ============================================================
# START SERVER
# ============================================================

if __name__ == '__main__':

    try:

        init_db()

        print(
            f'CuisineHub running at '
            f'http://127.0.0.1:5000 '
            f'| MySQL database: {DB_NAME}'
        )

    except Exception as e:

        print(
            'MySQL initialization failed:',
            e
        )

        print(
            'Start MySQL service, '
            'then restart the backend.'
        )

    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True
    )