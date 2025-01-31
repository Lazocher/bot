import logging
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from database import get_cities, get_categories, add_restaurant, add_dish, add_category, get_restaurants, add_city, \
    delete_item, add_manager, delete_manager, authenticate_user, delete_dish, get_all_dishes, get_connection, \
    update_stop_list, get_stop_list
from flask import session
import sqlite3

conn = get_connection()
cursor = conn.cursor()

# Обновляем структуру таблицы users
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role INTEGER NOT NULL,
        city TEXT,
        restaurant TEXT
    )
''')

# Добавление новых колонок, если они отсутствуют
cursor.execute("PRAGMA table_info(users);")
columns = [column[1] for column in cursor.fetchall()]

if "city" not in columns:
    cursor.execute("ALTER TABLE users ADD COLUMN city TEXT;")
if "restaurant" not in columns:
    cursor.execute("ALTER TABLE users ADD COLUMN restaurant TEXT;")

conn.commit()
conn.close()
print("Таблица 'users' успешно обновлена.")

UPLOAD_FOLDER = 'static/images'  # Папка для загрузки изображений
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}  # Допустимые форматы файлов

app = Flask(__name__)
app.secret_key = 'AdminKwork'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def get_dishes_by_restaurant(restaurant_name):
    """
    Получает список блюд для указанного ресторана.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Запрос для получения данных о блюдах
    cursor.execute('''
        SELECT 
            menu.dish_name, 
            menu.price, 
            menu.description, 
            categories.name AS category_name,
            menu.image_url,
            menu.image_path,
            menu.is_in_stop_list,
            menu.restaurant_account_number
        FROM menu
        LEFT JOIN categories ON menu.category_id = categories.id
        LEFT JOIN restaurants ON menu.restaurant_id = restaurants.id
        WHERE restaurants.name = ?
    ''', (restaurant_name,))

    # Получаем все данные из результата запроса
    dishes = cursor.fetchall()

    # Преобразуем данные в список словарей для удобного доступа в шаблоне
    dishes = [
        {
            'dish_name': row[0],
            'price': row[1],
            'description': row[2],
            'category_name': row[3],
            'image_url': row[4],
            'image_path': row[5],
            'is_in_stop_list': row[6],
            'restaurant_account_number': row[7]
        }
        for row in dishes
    ]

    # Подключаем меню для ресторана
    dishes = get_dishes_by_restaurant(restaurant_name)


def allowed_file(filename):
    """Проверка, что файл имеет допустимый формат"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_connection_db():
    conn = sqlite3.connect('bot_database.db')  # Укажите путь к вашей базе данных
    return conn


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/get_restaurants', methods=['GET'])
@login_required
def get_restaurants():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, city, account FROM restaurants')
    restaurants = cursor.fetchall()
    conn.close()

    return jsonify([{'id': r[0], 'name': r[1], 'city': r[2], 'account': r[3]} for r in restaurants])


@app.route('/get_restaurant_details/<int:restaurant_id>')
@login_required
def get_restaurant_details(restaurant_id):
    if 'user_id' not in session:
        return jsonify({"error": "Пользователь не авторизован"}), 401

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
    role = cursor.fetchone()

    if role and role[0] != 1:  # Если не администратор
        return jsonify({"error": "У вас нет доступа к админ-панели."}), 403

    # Получаем данные о ресторане
    cursor.execute(''' 
        SELECT r.id, r.name, r.city_id, r.account_number, r.category_id, r.weekdays_schedule, r.weekend_schedule, r.closed_days, 
               c.name as city_name, ca.name as category_name
        FROM restaurants r
        LEFT JOIN cities c ON r.city_id = c.id
        LEFT JOIN categories ca ON r.category_id = ca.id
        WHERE r.id = ? 
    ''', (restaurant_id,))
    restaurant = cursor.fetchone()

    if not restaurant:
        return jsonify({"error": "Ресторан не найден"}), 404

    # Преобразуем закрытые дни в массив, если это необходимо
    closed_days = restaurant[7]
    if closed_days:
        closed_days = closed_days.split(',')  # Преобразуем строку в массив, если нужно
    else:
        closed_days = []

    # Получаем список всех городов
    cursor.execute('SELECT id, name FROM cities')
    cities = cursor.fetchall()

    # Получаем список всех категорий
    cursor.execute('SELECT id, name FROM categories')
    categories = cursor.fetchall()

    # Получаем меню ресторана с категориями
    cursor.execute(''' 
        SELECT m.id, m.dish_name, m.description, m.price, m.category_id, m.image_url, m.restaurant_account_number, 
               m.image_path, m.old_price, m.promo_end_date, m.ongoing_promo, m.is_in_stop_list, m.status, m.reviews,
               c.name as category_name
        FROM menu m
        LEFT JOIN categories c ON m.category_id = c.id
        WHERE m.restaurant_id = ? 
    ''', (restaurant_id,))
    dishes = cursor.fetchall()

    conn.close()

    return jsonify({
        "restaurant": {
            "id": restaurant[0],
            "name": restaurant[1] or 'Без имени',
            "city": {
                "id": restaurant[2] if restaurant[2] is not None else 'Не указан',
                "name": restaurant[8] or 'Не указан'
            },
            "category": {
                "id": restaurant[4] if restaurant[4] is not None else 'Не указана',
                "name": restaurant[9] or 'Не указана'
            },
            "account_number": restaurant[3] or '',
            "weekdays_schedule": restaurant[5] or '',
            "weekend_schedule": restaurant[6] or '',
            "closed_days": closed_days  # Передаем массив закрытых дней
        },
        "cities": [{"id": city[0], "name": city[1]} for city in cities],
        "categories": [{"id": category[0], "name": category[1]} for category in categories],
        "dishes": [{
            "id": dish[0],
            "dish_name": dish[1] or 'Без названия',
            "description": dish[2] or 'Нет описания',
            "price": dish[3] or 'Цена не указана',
            "category": dish[13] or 'Без категории',
            "image_url": dish[5] or '',
            "restaurant_account_number": dish[6] or '',
            "image_path": dish[7] or '',
            "old_price": dish[8] or '',
            "promo_end_date": dish[9] or '',
            "ongoing_promo": dish[10] if dish[10] is not None else False,
            "is_in_stop_list": dish[11] if dish[11] is not None else False,
            "status": dish[12] or '',
            "reviews": dish[13] or ''
        } for dish in dishes] if dishes else []
    })


@app.route('/delete_restaurant/<int:restaurant_id>', methods=['POST'])
@login_required
def delete_restaurant(restaurant_id):
    if 'user_id' not in session:
        return jsonify({"error": "Пользователь не авторизован"}), 401

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
    role = cursor.fetchone()

    if role and role[0] != 1:  # Если не администратор
        return jsonify({"error": "У вас нет доступа к админ-панели."}), 403

    cursor.execute('DELETE FROM restaurants WHERE id = ?', (restaurant_id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Ресторан успешно удалён."})


@app.route('/admin')
@login_required
def admin_panel():
    # Проверка роли (должен быть администратор)
    if 'user_id' not in session:
        flash("Ошибка: Пользователь не авторизован.", "error")
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
    role = cursor.fetchone()
    conn.close()

    if role and role[0] != 1:  # Если не администратор
        flash("У вас нет доступа к админ-панели.", "error")
        return redirect(url_for('login'))

    # Извлекаем данные из базы данных
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Получаем города, категории, рестораны и блюда
    cities = get_cities()  # Список городов
    categories = get_categories()  # Список категорий

    # Извлечение ресторанов
    cursor.execute('''
        SELECT 
            r.id, r.name, r.city_id, r.account_number, r.category_id, 
            r.weekdays_schedule, r.weekend_schedule, r.closed_days
        FROM restaurants r
    ''')
    restaurants = cursor.fetchall()

    # Извлечение блюд
    cursor.execute('''
        SELECT 
            m.id, m.restaurant_id, m.category_id, m.dish_name, m.description, 
            m.price, m.image_url, m.restaurant_account_number, m.image_path, 
            m.old_price, m.promo_end_date, m.ongoing_promo, m.is_in_stop_list, 
            m.status, m.reviews
        FROM menu m
    ''')
    dishes = cursor.fetchall()

    conn.close()

    # Передаем данные в шаблон
    return render_template(
        'admin_panel.html',
        cities=cities,
        categories=categories,
        restaurants=restaurants,
        dishes=dishes,
    )


import logging

logging.basicConfig(level=logging.INFO)


@app.route('/update_restaurant/<int:restaurant_id>', methods=['PUT'])
@login_required
def update_restaurant(restaurant_id):
    if 'user_id' not in session:
        return jsonify({"error": "Пользователь не авторизован"}), 401

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor()

    data = request.get_json()

    # Логируем данные, полученные от клиента
    logging.info(f"Получены данные для обновления ресторана {restaurant_id}: {data}")

    # Получаем текущие данные ресторана
    cursor.execute('''
        SELECT name, account_number, city_id, category_id, weekdays_schedule, weekend_schedule, closed_days
        FROM restaurants
        WHERE id = ?
    ''', (restaurant_id,))
    current_data = cursor.fetchone()

    if not current_data:
        return jsonify({"error": "Ресторан не найден"}), 404

    # Логируем текущие данные ресторана
    logging.info(f"Текущие данные ресторана {restaurant_id}: {current_data}")

    # Проверка обязательных данных
    if not all(field in data for field in ['name', 'account_number', 'city_id', 'category_id']):
        return jsonify({"error": "Отсутствуют обязательные данные"}), 400

    try:
        # Обновляем данные ресторана
        cursor.execute('''
            UPDATE restaurants
            SET name = ?, account_number = ?, city_id = ?, category_id = ?, weekdays_schedule = ?, weekend_schedule = ?, closed_days = ?
            WHERE id = ?
        ''', (
            data['name'],
            data['account_number'],
            data['city_id'],
            data['category_id'],
            data.get('weekdays_schedule', ''),
            data.get('weekend_schedule', ''),
            data.get('closed_days', ''),
            restaurant_id
        ))

        conn.commit()

        # Логируем результат изменения (сколько строк было обновлено)
        rows_updated = cursor.rowcount
        logging.info(f"Число обновлённых строк: {rows_updated}")

        if rows_updated == 0:
            logging.warning(f"Ресторан с ID {restaurant_id} не был обновлён.")
            return jsonify({"error": "Ресторан не был обновлён. Проверьте данные."}), 404

        # Логируем обновленные данные
        cursor.execute('''
            SELECT name, account_number, city_id, category_id, weekdays_schedule, weekend_schedule, closed_days
            FROM restaurants
            WHERE id = ?
        ''', (restaurant_id,))
        updated_data = cursor.fetchone()

        logging.info(f"Обновленные данные ресторана {restaurant_id}: {updated_data}")

        return jsonify({"message": "Ресторан обновлен успешно"}), 200

    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при обновлении ресторана: {e}")
        return jsonify({"error": "Не удалось обновить данные ресторана"}), 500

    finally:
        conn.close()


@app.route('/add_restaurant', methods=['POST'])
def add_restaurant_route():
    # Извлечение данных из формы
    name = request.form['restaurant_name']
    city_id = request.form['city_id']
    category_id = request.form['category_id']
    account_number = request.form['account_number']
    weekdays_schedule = request.form.get('weekdays_schedule')
    weekend_schedule = request.form.get('weekend_schedule')
    closed_days = request.form.getlist('closed_days')  # Получаем список закрытых дней
    closed_days_value = ",".join(closed_days) if closed_days else None  # Преобразуем в строку
    manager_username = request.form.get('manager_username')

    conn = get_db()  # Получаем соединение с базой данных
    cursor = conn.cursor()

    try:
        # Вставка данных о ресторане
        cursor.execute('''
            INSERT INTO restaurants (name, city_id, category_id, account_number, weekdays_schedule, weekend_schedule, closed_days)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, city_id, category_id, account_number, weekdays_schedule, weekend_schedule, closed_days_value))
        conn.commit()

        # Отображение сообщения об успешном добавлении
        flash(f"Ресторан '{name}' успешно добавлен!", "success")

        restaurant_id = cursor.lastrowid  # Получаем id только что добавленного ресторана

        # Если есть менеджер, добавляем его
        if manager_username:
            cursor.execute('''
                INSERT INTO managers (username, restaurant_id)
                VALUES (?, ?)
            ''', (manager_username, restaurant_id))
            conn.commit()

    except sqlite3.Error as e:
        # Обработка ошибки базы данных
        flash(f"Ошибка базы данных: {str(e)}", "error")
    finally:
        # Закрытие соединения с базой данных
        conn.close()

    # Возвращаем пользователя на панель администратора
    return redirect(url_for('admin_panel'))


@app.route('/edit_restaurant/<int:restaurant_id>', methods=['GET', 'POST'])
def edit_restaurant_route(restaurant_id):
    conn = get_db()  # Получаем соединение с базой данных
    cursor = conn.cursor()

    if request.method == 'POST':
        # Извлечение данных из формы
        name = request.form['restaurant_name']
        city_id = request.form['city_id']
        category_id = request.form['category_id']
        account_number = request.form['account_number']
        weekdays_schedule = request.form.get('weekdays_schedule')
        weekend_schedule = request.form.get('weekend_schedule')
        closed_days = request.form.getlist('closed_days')  # Получаем список закрытых дней
        closed_days_value = ",".join(closed_days) if closed_days else None  # Преобразуем в строку
        manager_username = request.form.get('manager_username')

        try:
            # Обновление данных ресторана
            cursor.execute('''
                UPDATE restaurants
                SET name = ?, city_id = ?, category_id = ?, account_number = ?, weekdays_schedule = ?, weekend_schedule = ?, closed_days = ?
                WHERE id = ?
            ''', (name, city_id, category_id, account_number, weekdays_schedule, weekend_schedule, closed_days_value,
                  restaurant_id))
            conn.commit()

            # Обновление менеджера, если указано имя пользователя
            if manager_username:
                cursor.execute('''
                    INSERT INTO managers (username, restaurant_id)
                    VALUES (?, ?)
                    ON CONFLICT(restaurant_id) DO UPDATE SET username = excluded.username
                ''', (manager_username, restaurant_id))
                conn.commit()

            flash(f"Ресторан '{name}' успешно обновлен!", "success")

        except sqlite3.Error as e:
            # Обработка ошибки базы данных
            flash(f"Ошибка базы данных: {str(e)}", "error")
        finally:
            conn.close()

        # Возвращаем пользователя на панель администратора
        return redirect(url_for('admin_panel'))

    else:
        # Если метод GET, получаем текущие данные ресторана для отображения в форме
        cursor.execute('SELECT * FROM restaurants WHERE id = ?', (restaurant_id,))
        restaurant = cursor.fetchone()

        if not restaurant:
            flash("Ресторан не найден!", "error")
            return redirect(url_for('admin_panel'))

        # Получаем данные текущего менеджера
        cursor.execute('SELECT username FROM managers WHERE restaurant_id = ?', (restaurant_id,))
        manager = cursor.fetchone()

        conn.close()

        # Рендерим шаблон с формой редактирования, передавая текущие данные
        return render_template('admin_panel.html', restaurant=restaurant, manager=manager)


def get_payment_history_db():
    return sqlite3.connect('payment_history.db')


def get_bot_database_db():
    return sqlite3.connect('bot_database.db')


from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Dish(db.Model):
    __tablename__ = 'menu'  # Указываем, что модель будет работать с таблицей 'menu'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer)
    category_id = db.Column(db.Integer)
    dish_name = db.Column(db.String(255), nullable=False)  # Название блюда
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)  # Цена блюда
    image_url = db.Column(db.String(255))  # URL изображения
    image_path = db.Column(db.String(255))  # Путь к изображению на сервере
    is_in_stop_list: object = db.Column(db.Integer, default=0)  # Статус, находится ли в стоп-листе
    restaurant_account_number = db.Column(db.String(255))  # Номер ресторана (если нужно)

    def __repr__(self):
        return f"<Dish {self.dish_name}>"


@app.route('/orders')
def orders():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT id, customer_name, receipt FROM orders')
    orders = cursor.fetchall()

    # Формируем данные для шаблона
    orders_data = []
    for order in orders:
        order_id, customer_name, receipt_path = order
        # Извлекаем имя файла и формируем полный путь
        receipt_filename = receipt_path.split('/')[-1]
        orders_data.append({
            'id': order_id,
            'customer_name': customer_name,
            'receipt': f'/Check/{receipt_filename}'
        })

    return render_template('manager.html', orders=orders_data)


# Маршрут для обслуживания файлов из папки Check
@app.route('/Check/<filename>')
def serve_check(filename):
    return send_from_directory('Check', filename)


@app.route('/manager')
@login_required
def manager_panel():
    # Проверка на авторизацию
    if 'user_id' not in session:
        flash("Ошибка: Пользователь не авторизован.", "error")
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    # Подключение к базе данных и проверка роли
    conn_users = get_bot_database_db()
    cursor_users = conn_users.cursor()

    cursor_users.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    role = cursor_users.fetchone()
    conn_users.close()

    if not role or role[0] != 2:  # Если роль не равна 2 (менеджер)
        flash("У вас нет доступа к панели менеджера.", "error")
        return redirect(url_for('login'))

    # Подключение к базе данных bot_database.db для получения информации о ресторане
    conn_users = get_bot_database_db()
    cursor_users = conn_users.cursor()
    cursor_users.execute("""
        SELECT r.name, r.id
        FROM users u
        JOIN restaurants r ON u.restaurant = r.name
        WHERE u.id = ?
    """, (user_id,))
    restaurant_row = cursor_users.fetchone()
    conn_users.close()

    if not restaurant_row:
        flash("Ошибка: Ресторан менеджера не найден.", "error")
        return redirect(url_for('login'))

    restaurant_name, restaurant_id = restaurant_row

    # Подключение к базе данных payment_history.db для получения заказов
    conn_orders = get_payment_history_db()
    cursor_orders = conn_orders.cursor()

    try:
        # Пример запроса для получения заказов для ресторана
        cursor_orders.execute("SELECT * FROM orders WHERE restaurant_name = ?", (restaurant_name,))

    except sqlite3.Error as e:
        print(f"Ошибка при выполнении запроса:")
        print(f"Запрос: SELECT * FROM orders WHERE restaurant_name = ?")
        print(f"Параметры: restaurant_name = {restaurant_name}")
        print(f"Описание ошибки: {e}")
        print(f"Полная ошибка: {e.args}")
        print(f"Тип ошибки: {type(e)}")
        print(f"SQLSTATE код ошибки: {e.args[0]}")  # Если ошибка имеет код, например, для SQLSTATE

    orders = [
        {
            'id': row[0],
            'telegram_id': row[1],
            'dishes': row[2].split(','),
            'total_amount': float(row[3]) if row[3] else 0.0,
            'receipt': row[4],
            'address': row[5],
            'phone_number': row[6],
            'restaurant_name': row[7],
            'status': row[8]
        }
        for row in cursor_orders.fetchall()
    ]
    conn_orders.close()

    # Получаем категории из базы данных
    categories = get_categories()

    # Получение меню для ресторана
    cursor_dishes = get_bot_database_db().cursor()
    cursor_dishes.execute("""
        SELECT m.dish_name, m.price, m.description, c.name AS category_name, m.status
        FROM menu m
        JOIN categories c ON m.category_id = c.id
        WHERE m.restaurant_id = ?
    """, (restaurant_id,))

    dishes = cursor_dishes.fetchall()  # Список блюд

    # Разделение блюд на обычные и те, что в стоп-листе
    normal_dishes = []
    stoplist_dishes = []

    for dish in dishes:
        if dish[4] and dish[4] == 'Stopping':  # Учитываем None и проверку на 'Stopping'
            stoplist_dishes.append(dish)
        else:
            normal_dishes.append(dish)

    # Отображение страницы с меню
    return render_template(
        'manager.html',
        orders=orders,
        dishes=dishes,
        restaurant_name=restaurant_name,
        restaurant_id=restaurant_id,  # Передача ID ресторана
        normal_dishes=normal_dishes,
        stoplist_dishes=stoplist_dishes,
        categories=categories  # Передача категорий
    )


def get_db():
    """Получить или создать соединение с базой данных для текущего потока."""
    if 'db' not in g:
        g.db = sqlite3.connect('bot_database.db', check_same_thread=False)
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Закрыть соединение с базой данных в конце запроса."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


# Настройка логирования
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])


@app.route('/add_dish', methods=['POST'])
def add_dish_route():
    try:
        # Извлечение данных из формы
        dish_name = request.form['dish_name']
        restaurant_id = request.form['restaurant_id']
        category_id = request.form['category_id']
        price = request.form['price']
        description = request.form['description']
        image = request.files['image']  # Получаем файл изображения

        # Логируем полученные данные
        logging.debug(
            f"Received data: {dish_name}, {restaurant_id}, {category_id}, {price}, {description}, {image.filename}")

        # Путь для сохранения изображения
        image_filename = image.filename
        image_path = f"static/images/{image_filename}"

        # Сохраняем изображение на сервере
        image.save(image_path)

        # Генерация URL для изображения
        image_url = f"/static/images/{image_filename}"

        # Вставка данных в таблицу menu
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO menu 
            (restaurant_id, category_id, dish_name, description, price, image_url, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (restaurant_id, category_id, dish_name, description, price, image_url, image_path))

        conn.commit()
        conn.close()

        logging.info(f"Dish '{dish_name}' successfully added to the menu.")
        flash(f"Блюдо '{dish_name}' успешно добавлено!", "success")

    except Exception as e:
        logging.error(f"Error adding dish: {str(e)}")
        flash(f"Ошибка: {str(e)}", "error")

    return redirect(url_for('admin_panel'))  # Или redirect на другую панель


@app.route('/add_dish_route2', methods=['POST'])
def add_dish_route2():
    try:
        # Извлечение данных из формы
        dish_name = request.form['dish_name']
        restaurant_id = request.form['restaurant_id']
        category_id = request.form['category_id']
        price = request.form['price']
        description = request.form['description']
        image = request.files['image']  # Получаем файл изображения

        # Логируем полученные данные
        logging.debug(
            f"Received data: {dish_name}, {restaurant_id}, {category_id}, {price}, {description}, {image.filename}")

        # Путь для сохранения изображения
        image_filename = image.filename
        image_path = f"static/images/{image_filename}"

        # Сохраняем изображение на сервере
        image.save(image_path)

        # Генерация URL для изображения
        image_url = f"/static/images/{image_filename}"

        # Вставка данных в таблицу menu
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO menu 
            (restaurant_id, category_id, dish_name, description, price, image_url, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (restaurant_id, category_id, dish_name, description, price, image_url, image_path))

        conn.commit()
        conn.close()

        logging.info(f"Dish '{dish_name}' successfully added to the menu.")
        flash(f"Блюдо '{dish_name}' успешно добавлено!", "success")

    except Exception as e:
        logging.error(f"Error adding dish: {str(e)}")
        flash(f"Ошибка: {str(e)}", "error")

    return redirect(url_for('manager_panel'))


@app.route('/get_dish_details/<dish_name>', methods=['GET'])
def get_dish_details(dish_name):
    try:
        # Получаем данные блюда из базы данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('''SELECT dish_name, restaurant_id, category_id, price, description, image_url
                          FROM menu WHERE dish_name = ?''', (dish_name,))
        dish = cursor.fetchone()

        conn.close()

        if dish:
            dish_details = {
                'dish_name': dish[0],
                'restaurant_id': dish[1],
                'category_id': dish[2],
                'price': dish[3],
                'description': dish[4],
                'image_url': dish[5]  # Если нужно, добавь логику для обработки изображения
            }
            return jsonify(dish_details)
        else:
            return jsonify({'error': 'Dish not found'}), 404
    except Exception as e:
        logging.error(f"Error fetching dish details: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/edit_dish/<dish_name>', methods=['POST'])
def edit_dish(dish_name):
    try:
        # Извлечение данных из формы
        dish_name_new = request.form['dish_name']
        restaurant_id = request.form['restaurant_id']
        category_id = request.form['category_id']
        price = request.form['price']
        description = request.form['description']
        image = request.files['image']  # Получаем файл изображения

        # Логируем полученные данные
        logging.debug(f"Received data: {dish_name_new}, {restaurant_id}, {category_id}, {price}, {description}, {image.filename}")

        # Путь для сохранения изображения
        image_filename = image.filename
        image_path = f"static/images/{image_filename}"

        # Сохраняем изображение на сервере
        image.save(image_path)

        # Генерация URL для изображения
        image_url = f"/static/images/{image_filename}"

        # Обновление данных блюда в базе данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        cursor.execute(''' 
            UPDATE menu 
            SET dish_name = ?, restaurant_id = ?, category_id = ?, price = ?, description = ?, image_url = ?, image_path = ?
            WHERE dish_name = ?
        ''', (dish_name_new, restaurant_id, category_id, price, description, image_url, image_path, dish_name))

        conn.commit()
        conn.close()

        logging.info(f"Dish '{dish_name_new}' successfully updated in the menu.")
        flash(f"Блюдо '{dish_name_new}' успешно обновлено!", "success")

        return jsonify({"success": True})  # Ответ с успехом

    except Exception as e:
        logging.error(f"Error updating dish: {str(e)}")
        flash(f"Ошибка: {str(e)}", "error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/remove_from_stoplist/<string:dish_name>', methods=['POST'])
def remove_from_stoplist(dish_name):
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Обновляем статус блюда
        cursor.execute("UPDATE menu SET status = NULL WHERE dish_name = ?", (dish_name,))
        conn.commit()

        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        print(f"Ошибка при удалении блюда из стоп-листа: {e}")
        return jsonify({'error': 'Ошибка при удалении'}), 500


@app.route('/edit_dish_route', methods=['POST'])
def edit_dish_route():
    dish_id = request.form['dish_id']
    dish_name = request.form['dish_name']
    category_id = request.form['category_id']
    price = request.form['price']
    description = request.form['description']
    file = request.files['image']  # Получаем файл из формы

    # Логируем данные
    app.logger.info(
        f"Received data:\nDish ID: {dish_id}\nDish Name: {dish_name}\nCategory ID: {category_id}\nPrice: {price}\nDescription: {description}\nFile: {file.filename if file else 'No file'}")

    # Проверка на наличие изображения
    image_url = None
    image_path = None
    if file and allowed_file(file.filename):
        # Генерируем безопасное имя файла
        filename = secure_filename(file.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(image_path)
        image_url = url_for('static', filename='images/' + filename)

    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Обновляем блюдо в базе данных
        cursor.execute('''
            UPDATE menu
            SET dish_name = ?, category_id = ?, price = ?, description = ?, image_url = ?, image_path = ?
            WHERE dish_name = ?
        ''', (dish_name, category_id, price, description, image_url, image_path, dish_id))

        # Проверим, сколько строк было обновлено
        rows_updated = cursor.rowcount
        app.logger.info(f"Rows updated: {rows_updated}")  # Логируем количество обновленных строк

        # Сохраняем изменения и закрываем соединение
        conn.commit()
        conn.close()

        # Проверим, обновилось ли блюдо
        if rows_updated > 0:
            flash(f"Блюдо '{dish_name}' успешно обновлено!", "success")
        else:
            flash(f"Ошибка: Блюдо с ID '{dish_id}' не найдено.", "error")

    except Exception as e:
        flash(f"Ошибка: {str(e)}", "error")
        app.logger.error(f"Error while updating dish: {str(e)}")
        conn.rollback()  # Откат транзакции в случае ошибки
        conn.close()

    return redirect(url_for('manager_panel'))


@app.route('/add_to_stoplist/<dish_name>', methods=['POST'])
@login_required
def add_to_stoplist(dish_name):
    try:
        app.logger.debug(f"Received request to add dish '{dish_name}' to stoplist.")

        # Подключаемся к базе данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Проверяем, существует ли блюдо в базе
        cursor.execute('SELECT dish_name FROM menu WHERE dish_name = ?', (dish_name,))
        result = cursor.fetchone()

        if result is None:
            app.logger.warning(f"Dish '{dish_name}' not found in the database.")
            flash(f"Ошибка: Блюдо '{dish_name}' не найдено.", "error")
            return redirect(url_for('manager_panel'))

        app.logger.debug(f"Dish '{dish_name}' found, updating status to 'Stopping'.")

        # Обновляем статус блюда на 'Stopping'
        cursor.execute('''
            UPDATE menu SET status = 'Stopping' WHERE dish_name = ?
        ''', (dish_name,))

        # Сохраняем изменения и закрываем соединение
        conn.commit()
        conn.close()

        app.logger.info(f"Dish '{dish_name}' successfully added to stoplist.")
        flash(f"Блюдо '{dish_name}' добавлено в стоп-лист.", "success")
    except Exception as e:
        app.logger.error(f"Error while adding dish to stoplist: {str(e)}")
        flash(f"Ошибка: {str(e)}", "error")

    return redirect(url_for('manager_panel'))


@app.route('/delete_dish_route/<dish_name>', methods=['POST'])
@login_required
def delete_dish_route(dish_name):
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Удаляем блюдо из таблицы меню по имени блюда
        cursor.execute('''
            DELETE FROM menu WHERE dish_name = ?
        ''', (dish_name,))

        # Проверяем, сколько строк было удалено
        rows_deleted = cursor.rowcount
        app.logger.info(f"Rows deleted: {rows_deleted}")  # Логируем количество удаленных строк

        # Сохраняем изменения и закрываем соединение
        conn.commit()
        conn.close()

        if rows_deleted > 0:
            flash(f"Блюдо '{dish_name}' успешно удалено!", "success")
        else:
            flash(f"Ошибка: Блюдо с названием '{dish_name}' не найдено.", "error")

    except Exception as e:
        flash(f"Ошибка: {str(e)}", "error")
        app.logger.error(f"Error while deleting dish: {str(e)}")

    return redirect(url_for('manager_panel'))


@app.route('/delete_dish_route2/<dish_name>', methods=['POST'])
@login_required
def delete_dish_route2(dish_name):
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Удаляем блюдо из таблицы меню по имени блюда
        cursor.execute('''
            DELETE FROM menu WHERE dish_name = ?
        ''', (dish_name,))

        # Проверяем, сколько строк было удалено
        rows_deleted = cursor.rowcount
        app.logger.info(f"Rows deleted: {rows_deleted}")  # Логируем количество удаленных строк

        # Сохраняем изменения и закрываем соединение
        conn.commit()
        conn.close()

        if rows_deleted > 0:
            flash(f"Блюдо '{dish_name}' успешно удалено!", "success")
        else:
            flash(f"Ошибка: Блюдо с названием '{dish_name}' не найдено.", "error")

    except Exception as e:
        flash(f"Ошибка: {str(e)}", "error")
        app.logger.error(f"Error while deleting dish: {str(e)}")

    return redirect(url_for('admin_panel'))


@app.route('/add_category', methods=['POST'])
def add_category_route():
    category_name = request.form['category_name']

    add_category(category_name)
    return redirect(url_for('admin_panel'))


@app.route('/add_city', methods=['POST'])
def add_city_route():
    city_name = request.form['city_name']
    add_city(city_name)
    return redirect(url_for('admin_panel'))


@app.route('/delete_data', methods=['POST'])
def delete_data_route():
    delete_type = request.form.get('delete_type')

    # Получаем соответствующий ID в зависимости от типа
    item_id = None
    if delete_type == 'city':
        item_id = request.form.get('city_id')
    elif delete_type == 'category':
        item_id = request.form.get('category_id')
    elif delete_type == 'dish':
        item_id = request.form.get('dish_id')
    elif delete_type == 'restaurant':
        item_id = request.form.get('restaurant_id')

    if not item_id:
        return jsonify({"error": "Не указан ID для удаления."}), 400

    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Удаляем данные в зависимости от типа
        if delete_type == 'city':
            cursor.execute('DELETE FROM cities WHERE id = ?', (item_id,))
        elif delete_type == 'category':
            cursor.execute('DELETE FROM categories WHERE id = ?', (item_id,))
        elif delete_type == 'dish':
            cursor.execute('DELETE FROM menu WHERE id = ?', (item_id,))
        elif delete_type == 'restaurant':
            cursor.execute('DELETE FROM restaurants WHERE id = ?', (item_id,))

        conn.commit()
        return jsonify({"message": f"Элемент с ID {item_id} успешно удален."}), 200
    except sqlite3.Error as e:
        return jsonify({"error": f"Ошибка базы данных: {str(e)}"}), 500
    finally:
        conn.close()
        return redirect(url_for('admin_panel'))


@app.route('/add_manager', methods=['POST'])
def add_manager_route():
    try:
        # Извлекаем данные формы
        username = request.form.get('login')
        password = request.form.get('password')
        city = request.form.get('city_id')
        restaurant = request.form.get('restaurant_id')

        # Проверяем, что все поля заполнены
        if not username or not password or not city or not restaurant:
            flash("Все поля (логин, пароль, город, ресторан) обязательны для заполнения.", "error")
            return redirect(url_for('admin_panel'))

        # Добавляем данные в базу
        with sqlite3.connect('bot_database.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, password, role, city, restaurant)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, password, 2, city, restaurant))

        flash(f"Менеджер '{username}' успешно добавлен!", "success")

    except sqlite3.IntegrityError:
        flash(f"Ошибка: Пользователь с логином '{username}' уже существует.", "error")
    except Exception as e:
        app.logger.error(f"Ошибка при добавлении менеджера: {e}")
        flash(f"Произошла непредвиденная ошибка: {e}", "error")

    return redirect(url_for('admin_panel'))


@app.route('/get_dishes_by_restaurant/<int:restaurant_id>', methods=['GET'])
def get_dishes_by_restaurant_route(restaurant_id):
    try:
        conn = sqlite3.connect('bot_database.db')  # Укажите правильный путь к базе данных
        cursor = conn.cursor()

        # Получаем блюда для указанного ресторана
        cursor.execute('''
            SELECT id, dish_name
            FROM menu
            WHERE restaurant_id = ?
        ''', (restaurant_id,))

        dishes = cursor.fetchall()
        conn.close()

        # Преобразуем данные в JSON-формат
        return jsonify([{"id": dish[0], "name": dish[1]} for dish in dishes])
    except Exception as e:
        return jsonify({"error": f"Ошибка базы данных: {str(e)}"}), 500


@app.route('/delete_manager/<int:manager_id>', methods=['POST'])
def delete_manager_route(manager_id):
    delete_manager(manager_id)
    return redirect(url_for('admin_panel'))


USERS_DATABASE = 'users_database.db'


def get_user_db_connection():
    return sqlite3.connect(USERS_DATABASE)


def init_user_db():
    # Создание таблицы users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Проверяем пользователя в базе данных
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]  # Сохраняем только ID пользователя в сессии

            # Проверяем роль напрямую из базы
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT role FROM users WHERE id = ?', (user[0],))
            role = cursor.fetchone()
            conn.close()

            if role and role[0] == 1:  # Если администратор
                return redirect(url_for('admin_panel'))
            elif role and role[0] == 2:  # Если менеджер
                return redirect(url_for('manager_panel'))
            else:
                flash("У вас нет доступа к панели.", "error")
                return redirect(url_for('login'))
        else:
            flash("Неправильный логин или пароль.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')  # HTML-страница для авторизации


@app.route('/get_orders', methods=['GET'])
def get_orders():
    try:
        # Проверяем, авторизован ли пользователь
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Пользователь не авторизован'}), 403

        # Подключаемся к базе данных
        conn = sqlite3.connect('payment_history.db')
        cursor = conn.cursor()

        # Получаем заказы из таблицы orders
        cursor.execute("SELECT * FROM orders")
        rows = cursor.fetchall()

        # Преобразуем данные в список словарей
        orders = [
            {
                'id': row[0],
                'telegram_id': row[1],
                'dishes': row[2].split(',') if row[2] else [],
                'total_amount': row[3],
                'receipt': row[4],
                'address': row[5],
                'phone_number': row[6],
                'restaurant_name': row[7],
                'status': row[8]
            }
            for row in rows
        ]

        logging.debug(f"Fetched orders: {orders}")
        return jsonify({'orders': orders})

    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({'error': f"Unexpected error: {str(e)}"}), 500
    finally:
        conn.close()


@app.route('/update_order_status/<int:order_id>/<string:status>', methods=['POST'])
def update_order_status(order_id, status):
    try:
        conn = sqlite3.connect('payment_history.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        conn.commit()
        return jsonify({'message': f'Order {order_id} status updated to {status}'})
    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    return redirect(url_for('login'))


def add_user(username, password, role):
    """
    Добавляет пользователя в базу данных пользователей.

    :param username: Имя пользователя (уникальное).
    :param password: Пароль пользователя.
    :param role: Роль пользователя (1 - админ, 2 - менеджер и т.д.).
    """

    try:
        # Вставляем нового пользователя в таблицу
        cursor.execute('''
            INSERT INTO users (username, password, role)
            VALUES (?, ?, ?)
        ''', (username, password, role))
        conn.commit()
        print(f"Пользователь '{username}' успешно добавлен.")
    except sqlite3.IntegrityError:
        # Ошибка уникальности имени пользователя
        print(f"Пользователь с именем '{username}' уже существует.")
    finally:
        conn.close()


def get_normal_and_stoplist_dishes(restaurant_id):
    # Подключение к базе данных
    conn = get_bot_database_db()  # Используйте вашу функцию для подключения к базе
    cursor = conn.cursor()

    # Выполняем запрос, чтобы получить все блюда из меню
    cursor.execute("SELECT dish_name, price, description, status FROM menu WHERE restaurant_id = ?", (restaurant_id,))
    dishes = cursor.fetchall()

    # Разделяем блюда на два списка
    normal_dishes = []
    stoplist_dishes = []

    for dish in dishes:
        if dish[3] == 'Stopping':  # Если статус блюда равен 'Stopping'
            stoplist_dishes.append(dish)
        else:
            normal_dishes.append(dish)

    # Закрываем соединение с базой данных
    conn.close()

    # Возвращаем два списка: обычные блюда и блюда из стоп-листа
    return normal_dishes, stoplist_dishes


@app.route('/apply_promo/<string:dish_name>', methods=['POST'])
def apply_promo(dish_name):
    data = request.get_json()

    new_price = data.get('newPrice')
    promo_end_date = data.get('promoEndDate')
    ongoing_promo = data.get('ongoingPromo')

    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Сохраняем старую цену в old_price перед обновлением
        cursor.execute("""
            SELECT price FROM menu WHERE dish_name = ?
        """, (dish_name,))
        old_price = cursor.fetchone()[0]

        # Если акция бесконечная, устанавливаем None для даты окончания
        if ongoing_promo:
            promo_end_date = None

        # Обновляем цену и дату окончания акции для блюда, а также сохраняем старую цену в old_price
        cursor.execute("""
            UPDATE menu
            SET price = ?, promo_end_date = ?, ongoing_promo = ?, old_price = ?
            WHERE dish_name = ?
        """, (new_price, promo_end_date, ongoing_promo, old_price, dish_name))

        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        print(f"Ошибка при применении акции: {e}")
        return jsonify({'error': 'Ошибка при применении акции'}), 500


@app.route('/remove_promo/<string:dish_name>', methods=['POST'])
def remove_promo(dish_name):
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Получаем старую цену из столбца old_price
        cursor.execute("""
            SELECT old_price FROM menu WHERE dish_name = ?
        """, (dish_name,))
        old_price = cursor.fetchone()[0]

        # Возвращаем цену к старой и удаляем столбец old_price
        cursor.execute("""
            UPDATE menu
            SET price = ?, old_price = NULL, promo_end_date = NULL, ongoing_promo = NULL
            WHERE dish_name = ?
        """, (old_price, dish_name))

        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        print(f"Ошибка при удалении акции: {e}")
        return jsonify({'error': 'Ошибка при удалении акции'}), 500


@app.route('/get_promo2_dishes', methods=['GET'])
def get_promo2_dishes():
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Получаем список блюд с активными промо2
        cursor.execute("""
            SELECT dish_name, price
            FROM menu
            WHERE ongoing_promo = 1
        """)

        dishes = cursor.fetchall()

        # Формируем список для передачи в ответ
        promo2_dishes = [
            {'dish_name': dish[0], 'price': dish[1]}
            for dish in dishes
        ]

        conn.close()

        return jsonify({'dishes': promo2_dishes})

    except Exception as e:
        print(f"Ошибка при получении блюд с промо2: {e}")
        return jsonify({'error': 'Ошибка при получении данных'}), 500


@app.route('/get_stoplist_dishes')
def get_stoplist_dishes():
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        # Получаем блюда с статусом "Stopping"
        cursor.execute("SELECT dish_name FROM menu WHERE status = 'Stopping'")
        stoplist_dishes = cursor.fetchall()

        conn.close()

        # Возвращаем данные в формате JSON
        return jsonify([{'dish_name': dish[0]} for dish in stoplist_dishes])
    except Exception as e:
        print(f"Ошибка при получении стоп-листовых блюд: {e}")
        return jsonify({'error': 'Ошибка при получении данных'}), 500


if __name__ == '__main__':
    def add_admin(username, password):
        try:
            # Подключаемся к базе данных
            conn = sqlite3.connect('bot_database.db')  # Укажите путь к вашей базе данных
            cursor = conn.cursor()

            # Добавляем нового менеджера
            cursor.execute('''
                INSERT INTO users (username, password, role)
                VALUES (?, ?, ?)
            ''', (username, password, 1))

            conn.commit()
            conn.close()
            print(f"Аккаунт Администратора успешно добавлен'.")
        except sqlite3.IntegrityError:
            print(f"Ошибка: Пользователь с логином '{username}' уже существует.")


    # Добавляем менеджера
    add_admin("admin", "admin")

    app.run(host="0.0.0.0", port=80)
