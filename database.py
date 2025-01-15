import sqlite3

from flask import g

# --- Константы для базы данных ---
BOT_DATABASE = 'bot_database.db'


# --- Универсальная функция подключения ---
def get_connection():
    """
    Возвращает подключение к базе данных.
    """
    return sqlite3.connect(BOT_DATABASE)


# --- Функции для городов ---
def get_cities():
    """
    Получает список всех городов.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM cities')
    cities = cursor.fetchall()
    conn.close()
    return cities


def add_city(city_name):
    """
    Добавляет новый город.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cities (name)
        VALUES (?)
    ''', (city_name,))
    conn.commit()
    conn.close()


def get_categories():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        # Извлекаем все категории
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        print("Извлеченные категории:", categories)  # Добавьте вывод для проверки
        return [{"id": row[0], "name": row[1]} for row in categories]
    except Exception as e:
        print(f"Ошибка при извлечении категорий: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def add_category(category_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        # Проверка, существует ли уже категория с таким именем
        cursor.execute("SELECT COUNT(*) FROM categories WHERE name = ?", (category_name,))
        if cursor.fetchone()[0] > 0:
            print(f"Категория '{category_name}' уже существует.")
            return  # Прерываем выполнение, если категория уже существует

        # Добавляем категорию в таблицу
        cursor.execute('INSERT INTO categories (name) VALUES (?)', (category_name,))
        conn.commit()  # Сохраняем изменения
        print(f"Категория '{category_name}' успешно добавлена.")
    except sqlite3.IntegrityError:
        # Если нарушение уникальности
        print(f"Ошибка: Категория с именем '{category_name}' уже существует.")
    except Exception as e:
        print(f"Неизвестная ошибка: {e}")
    finally:
        cursor.close()
        conn.close()


# --- Функции для ресторанов ---
def get_restaurants():
    """
    Получает список всех ресторанов.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM restaurants')
    restaurants = cursor.fetchall()
    conn.close()
    return restaurants


def add_restaurant(name, city_id, category_id, account_number):
    """
    Добавляет новый ресторан.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO restaurants (name, city_id, category_id, account_number)
        VALUES (?, ?, ?, ?)
    ''', (name, city_id, category_id, account_number))
    conn.commit()
    conn.close()


# --- Функции для блюд ---
def get_all_dishes():
    """
    Получает список всех блюд.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            menu.id, menu.dish_name, menu.price, menu.description,
            categories.name AS category_name, restaurants.name AS restaurant_name
        FROM menu
        LEFT JOIN categories ON menu.category_id = categories.id
        LEFT JOIN restaurants ON menu.restaurant_id = restaurants.id
    ''')
    dishes = cursor.fetchall()
    conn.close()
    return dishes


def add_dish(dish_name, restaurant_id, category_id, price, description=None):
    """
    Добавляет новое блюдо.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO menu (dish_name, restaurant_id, category_id, price, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (dish_name, restaurant_id, category_id, price, description))
    conn.commit()
    conn.close()


def delete_dish(dish_name, restaurant_name):
    """
    Удаляет блюдо из ресторана.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Получение ID ресторана
    cursor.execute('SELECT id FROM restaurants WHERE name = ?', (restaurant_name,))
    restaurant = cursor.fetchone()
    if not restaurant:
        raise ValueError(f"Ресторан '{restaurant_name}' не найден.")
    restaurant_id = restaurant[0]

    # Удаление блюда
    cursor.execute('DELETE FROM menu WHERE dish_name = ? AND restaurant_id = ?', (dish_name, restaurant_id))
    conn.commit()
    conn.close()


def get_dishes_by_restaurant(restaurant_name):
    """
    Получает список блюд по названию ресторана.
    """
    conn = get_connection()
    cursor = conn.cursor()
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

    dishes = cursor.fetchall()

    # Добавляем отладочную информацию
    print(f"Query result for restaurant '{restaurant_name}': {dishes}")

    conn.close()
    return dishes


# --- Функции для менеджеров ---
def add_manager(name, restaurant_id):
    """
    Добавляет менеджера в ресторан.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO managers (name, restaurant_id)
        VALUES (?, ?)
    ''', (name, restaurant_id))
    conn.commit()
    conn.close()


def delete_manager(manager_id):
    """
    Удаляет менеджера по ID.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM managers WHERE id = ?', (manager_id,))
    conn.commit()
    conn.close()


# --- Функции для стоп-листа ---
def update_stop_list(dish_id, status):
    """
    Обновляет статус блюда в стоп-листе.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE menu
        SET is_in_stop_list = ?
        WHERE id = ?
    ''', (1 if status else 0, dish_id))
    conn.commit()
    conn.close()


def get_stop_list():
    """
    Получает список блюд из стоп-листа.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            menu.id, menu.dish_name, menu.price, menu.description,
            categories.name AS category_name, restaurants.name AS restaurant_name
        FROM menu
        LEFT JOIN categories ON menu.category_id = categories.id
        LEFT JOIN restaurants ON menu.restaurant_id = restaurants.id
        WHERE menu.is_in_stop_list = 1
    ''')
    stop_list = cursor.fetchall()
    conn.close()
    return stop_list


# --- Удаление записей ---
def delete_item(table_name, item_id):
    """
    Удаляет запись из указанной таблицы по ID.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f'DELETE FROM {table_name} WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()


# --- Аутентификация ---
def authenticate_user(username, password):
    """
    Аутентифицирует пользователя.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, role
        FROM users
        WHERE username = ? AND password = ?
    ''', (username, password))
    user = cursor.fetchone()
    conn.close()
    return user


# --- Основной блок ---
if __name__ == '__main__':
    print("Это модуль базы данных. Импортируйте функции для работы с базой.")
