import os
import sqlite3
import logging
from aiogram.dispatcher.filters import Text
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import MessageNotModified
import asyncio
import json
import re

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Укажите свой токен
TOKEN = '6255243124:AAGxhPPVQqYnTYZrR1pZf3WOdrAmYQMC3mw'

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class EditProfileFSM(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_address = State()
    waiting_for_phone = State()
    waiting_for_city = State()


class AddDish(StatesGroup):
    waiting_for_price = State()
    waiting_for_description = State()
    waiting_for_image = State()
    waiting_for_restaurant = State()  # Состояние для ввода названия ресторана
    waiting_for_category = State()  # Состояние для ввода категории блюда
    waiting_for_dish_name = State()  # Состояние для ввода названия блюда
    waiting_for_dish_description = State()  # Состояние для ввода описания блюда
    waiting_for_dish_price = State()  # Состояние для ввода цены блюда
    waiting_for_dish_image = State()  # Состояние для ввода изображения блюда


class AddCategory(StatesGroup):
    waiting_for_category_name = State()


class AddRestaurant(StatesGroup):
    waiting_for_restaurant_name = State()
    waiting_for_account_number = State()
    waiting_for_manager_username = State()
    waiting_for_city = State()
    waiting_for_category = State()
    waiting_for_weekdays_schedule = State()
    waiting_for_weekend_schedule = State()
    waiting_for_closed_days = State()
    waiting_for_finished = State()


class PaymentStates(StatesGroup):
    waiting_for_receipt = State()


class AddCity(StatesGroup):
    waiting_for_city_name = State()


# Подключения к базам данных
conn = sqlite3.connect('admin_panel/bot_database.db', check_same_thread=False)
cursor = conn.cursor()

conn_cart = sqlite3.connect('admin_panel/cart_database.db', check_same_thread=False)
cursor_cart = conn_cart.cursor()

conn_payment = sqlite3.connect('admin_panel/payment_history.db', check_same_thread=False)
cursor_payment = conn_payment.cursor()


def initialize_database():
    """
    Универсальная функция для инициализации базы данных.
    Создает таблицы, если они отсутствуют, и добавляет колонки, если они ещё не существуют.
    """

    def add_column_if_not_exists(cursor, table_name, column_name, column_definition):
        """
        Добавляет колонку в таблицу, если её нет.
        """
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = [row[1] for row in cursor.fetchall()]
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition};")
            logging.info(f"Колонка {column_name} добавлена в таблицу {table_name}.")

    try:
        # Таблица user_profiles
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            address TEXT,
            phone_number TEXT,
            city_id INTEGER,
            FOREIGN KEY (city_id) REFERENCES cities(id)
        )''')
        logging.info("Таблица user_profiles успешно создана.")

        # Таблица cities
        cursor.execute('''CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )''')
        logging.info("Таблица cities успешно создана.")

        # Таблица categories
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )''')
        logging.info("Таблица categories успешно создана.")

        # Таблица restaurants
        cursor.execute('''CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            city_id INTEGER NOT NULL,
            account_number TEXT,
            category_id INTEGER,
            FOREIGN KEY (city_id) REFERENCES cities(id)
        )''')
        logging.info("Таблица restaurants успешно создана.")

        # Добавляем колонки для графика работы ресторанов
        add_column_if_not_exists(cursor, "restaurants", "weekdays_schedule", "TEXT")
        add_column_if_not_exists(cursor, "restaurants", "weekend_schedule", "TEXT")
        add_column_if_not_exists(cursor, "restaurants", "closed_days", "TEXT")

        # Таблица restaurant_schedule
        cursor.execute('''CREATE TABLE IF NOT EXISTS restaurant_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER,
            weekdays_schedule TEXT,
            weekend_schedule TEXT,
            closed_days TEXT,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
        )''')
        logging.info("Таблица restaurant_schedule успешно создана.")

        # Таблица menu
        cursor.execute('''CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            dish_name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            image_url TEXT,
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )''')
        logging.info("Таблица menu успешно создана.")

        # Добавляем дополнительные колонки в menu
        add_column_if_not_exists(cursor, "menu", "restaurant_account_number", "TEXT")
        add_column_if_not_exists(cursor, "menu", "image_path", "TEXT")

        # Таблица user_city_data
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_city_data (
            user_id INTEGER PRIMARY KEY,
            city_id INTEGER,
            FOREIGN KEY (city_id) REFERENCES cities(id)
        )''')
        logging.info("Таблица user_city_data успешно создана.")

        # Таблица cart
        cursor_cart.execute('''CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            dish_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dish_id) REFERENCES menu(id)
        )''')
        logging.info("Таблица cart успешно создана.")

        # Таблица orders
        cursor_payment.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            dishes TEXT,
            total_amount REAL,
            receipt TEXT,
            address TEXT,
            phone_number TEXT,
            restaurant_name TEXT,
            status TEXT
        )''')
        logging.info("Таблица orders успешно создана.")

        # Применяем изменения
        conn.commit()
        conn_cart.commit()
        conn_payment.commit()

        logging.info("Инициализация базы данных успешно завершена.")
    except Exception as e:
        logging.error(f"Ошибка при инициализации базы данных: {e}", exc_info=True)


# Инициализация базы данных
initialize_database()


# Создание таблицы для истории платежей
def initialize_payment_history():
    cursor_payment.execute('''
        CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,                  -- ID пользователя Telegram
    dishes TEXT,                          -- Список блюд
    total_amount REAL,                    -- Сумма оплаты
    receipt TEXT,                         -- Путь к чеку
    address TEXT,                         -- Адрес доставки
    phone_number TEXT,                    -- Номер телефона
    restaurant_name TEXT,                 -- Название ресторана
    status TEXT                           -- Статус заказа
        )
    ''')
    conn_payment.commit()


initialize_payment_history()


# Главная страница
@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    cursor.execute("SELECT id, name FROM cities")
    cities = cursor.fetchall()
    for city_id, name in cities:
        keyboard.insert(InlineKeyboardButton(f"{name}", callback_data=f"city_{city_id}"))
    await message.answer("Выберите ваш город:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("city_"))
async def city_selected(callback_query: types.CallbackQuery):
    city_id = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id

    # Обновляем город в профиле пользователя
    cursor.execute('''
        INSERT INTO user_profiles (user_id, city_id)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET city_id = ?
    ''', (user_id, city_id, city_id))
    conn.commit()

    await callback_query.message.edit_text("Город успешно установлен!")
    await show_main_menu(callback_query)


@dp.callback_query_handler(lambda c: c.data == "main_menu")
async def show_main_menu(callback_query: types.CallbackQuery):
    """Возврат в главное меню."""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("🍽️ Меню"), KeyboardButton("🛒 Корзина"))
    keyboard.row(KeyboardButton("📦 Мои заказы"), KeyboardButton("👤 Профиль"))

    # Удаляем сообщение, вызвавшее callback, чтобы избежать путаницы
    await callback_query.message.delete()

    # Отправляем новое сообщение с обычной клавиатурой
    await bot.send_message(callback_query.from_user.id, "Добро пожаловать в главное меню:", reply_markup=keyboard)

    # Отвечаем на callback, чтобы Telegram не показывал "часики"
    await callback_query.answer()


@dp.message_handler(lambda message: message.text == "📦 Мои заказы")
async def show_orders(message: types.Message):
    user_id = message.from_user.id

    # Fetch orders for the user from the conn_payment database
    try:
        cursor_payment.execute('''
            SELECT id, dishes, total_amount, receipt, address, phone_number, restaurant_name, status
            FROM orders
            WHERE telegram_id = ?
            ORDER BY id DESC
        ''', (user_id,))
        orders = cursor_payment.fetchall()

        if not orders:
            await message.answer("У вас пока нет заказов.")
            return

        # Build the response message
        response = "📦 *Ваши заказы:*\n\n"
        for order in orders:
            order_id, dishes, total_amount, receipt, address, phone_number, restaurant_name, status = order
            response += f"➖➖➖➖➖➖➖➖➖\n"
            response += f"📌 *Заказ {order_id}*\n"
            response += f"🍽️ *Блюда:*\n```{dishes.replace(', ', '')}```\n"
            response += f"💵 *Общая сумма:* {total_amount}₽\n"
            response += f"🏨 *Ресторан:* {restaurant_name}\n"
            response += f"📍 *Адрес доставки:* {address}\n"
            response += f"📞 *Телефон получателя:* {phone_number}\n"
            response += f"📄 *Статус заказа:* {status}\n"
            response += f"📂 [Скачать чек](tg://file?file_id={receipt})\n" if receipt else ""
            response += f"➖➖➖➖➖➖➖➖➖\n\n"

        await message.answer(response, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка при получении заказов пользователя: {e}")
        await message.answer("Произошла ошибка при загрузке ваших заказов. Попробуйте позже.")


# Функция для получения товаров из корзины пользователя
def get_cart(user_id):
    try:
        logging.info(f"Запрашиваю корзину для user_id={user_id}")

        # Получаем все товары из корзины пользователя
        cursor_cart.execute("SELECT dish_id, quantity FROM cart WHERE user_id = ?", (user_id,))
        cart_items = cursor_cart.fetchall()

        cart_details = []
        total_sum = 0
        account_number = None

        for dish_id, quantity in cart_items:
            # Запросить название и цену блюда по dish_id
            cursor.execute("SELECT dish_name, price, restaurant_account_number FROM menu WHERE id = ?", (dish_id,))
            dish = cursor.fetchone()

            if dish:
                dish_name, price, account_number = dish
                total_price = price * quantity
                cart_details.append({
                    'dish_name': dish_name,
                    'quantity': quantity,
                    'price': price,
                    'total': total_price
                })
                total_sum += total_price

        # Если не найден номер счета, присваиваем None
        if account_number is None:
            account_number = "Не указан"  # Это можно изменить на что-то более подходящее

        logging.info(f"Корзина для user_id={user_id}: {cart_details}")
        return cart_details, total_sum, account_number
    except Exception as e:
        logging.error(f"Ошибка при получении корзины: {e}")
        return [], 0, "Не указан"  # Возвращаем строку для account_number, если ошибка


@dp.message_handler(lambda message: message.text == "🛒 Корзина")
async def show_cart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cart_items, total_sum, account_number = get_cart(user_id)

    if cart_items:
        # Получаем название ресторана по первому блюду
        cursor_cart.execute("SELECT dish_id FROM cart WHERE user_id = ?", (user_id,))
        first_dish_id = cursor_cart.fetchone()
        if first_dish_id:
            cursor.execute('''
                SELECT restaurants.name
                FROM menu
                JOIN restaurants ON menu.restaurant_id = restaurants.id
                WHERE menu.id = ?
            ''', (first_dish_id[0],))
            restaurant_name = cursor.fetchone()
            restaurant_name = restaurant_name[0] if restaurant_name else "Неизвестный ресторан"

            # Сохраняем название ресторана в FSM
            await state.update_data(restaurant_name=restaurant_name)
        else:
            restaurant_name = "Неизвестный ресторан"

        cart_message = f"🏦 *Ресторан:* {restaurant_name}\n\n"
        cart_message += "🛒 *Ваша корзина:*\n"
        for item in cart_items:
            cart_message += f"🍽️ *{item['dish_name']}* (x{item['quantity']}) - {item['total']}₽\n"

        cart_message += f"\n💵 *Общая сумма:* {total_sum}₽\n"
        cart_message += f"🏦 *Счет ресторана:* {account_number}"

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("💳 Оплатить", callback_data="pay_cart"),
            InlineKeyboardButton("✏️ Редактировать", callback_data="edit_cart")
        )

        await message.answer(cart_message, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await message.answer("Ваша корзина пуста.")


class PaymentFSM(StatesGroup):
    waiting_for_receipt = State()


@dp.callback_query_handler(lambda c: c.data == 'pay_cart')
async def process_payment(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    cart_items, total_sum, account_number = get_cart(user_id)

    if not cart_items:
        await callback_query.answer("Ваша корзина пуста!")
        return

    message = "Ваш заказ:\n"
    for item in cart_items:
        message += f"🍽️ *{item['dish_name']}* (x{item['quantity']}) - {item['total']}₽\n"

    message += f"\nОбщая сумма: {total_sum}₽"
    message += f"\nНомер счета ресторана: {account_number}"

    # Кнопки для оплаты и возврата в корзину
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Оплачено! ✅", callback_data='payment_done'),
        InlineKeyboardButton("Назад 🔙", callback_data='back_to_cart')
    )

    await callback_query.message.edit_text(message, reply_markup=keyboard, parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data == "back_to_cart")
async def back_to_cart(callback_query: types.CallbackQuery):
    """Возврат в корзину."""
    user_id = callback_query.from_user.id
    # Здесь предполагается, что функция get_cart() уже определена.
    cart_items, total_sum, account_number = get_cart(user_id)

    if not cart_items:
        await callback_query.message.edit_text("Ваша корзина пуста.")
        return

    message = "Ваши товары в корзине:\n"
    for item in cart_items:
        message += f"🍽️ *{item['dish_name']}* (x{item['quantity']}) - {item['total']}₽\n"

    message += f"\nСумма: {total_sum}₽"
    message += f"\nНомер счета ресторана: {account_number}"

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💳 Оплатить", callback_data="pay_cart"),
        InlineKeyboardButton("✏️ Редактировать", callback_data="edit_cart")
    )

    await callback_query.message.edit_text(message, reply_markup=keyboard, parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data == 'payment_done', state="*")
async def payment_done(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    # Получаем корзину пользователя
    cart_items, total_sum, _ = get_cart(user_id)

    if not cart_items:
        await callback_query.message.edit_text("Ваша корзина пуста! Вы не можете оформить заказ.")
        return

    # Проверяем, есть ли профиль пользователя
    cursor.execute('SELECT address, phone_number FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = cursor.fetchone()

    if not profile or not profile[0] or not profile[1]:
        await callback_query.message.edit_text("Заполните адрес доставки и номер телефона в профиле перед оформлением "
                                               "заказа.")
        return

    # Сохраняем данные в состоянии FSM
    await state.update_data(cart_items=cart_items, total_sum=total_sum, address=profile[0], phone_number=profile[1])

    # Клавиатура с кнопкой "Назад"
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Назад 🔙", callback_data='cancel_receipt')
    )

    await callback_query.message.edit_text(
        "Пожалуйста, отправьте чек в формате изображения или документа.", reply_markup=keyboard)
    await PaymentFSM.waiting_for_receipt.set()


@dp.callback_query_handler(Text(equals='cancel_receipt'), state="*")
async def cancel_receipt_process(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Назад 🔙".
    Завершает текущее состояние и уведомляет пользователя.
    """
    await state.finish()
    await callback_query.message.edit_text("Операция отменена. Если потребуется помощь, начните заново!")


@dp.message_handler(content_types=['document', 'photo'], state=PaymentFSM.waiting_for_receipt)
async def handle_receipt(message: types.Message, state: FSMContext):
    try:
        user_id = message.from_user.id

        # Получаем файл
        if message.photo:
            file_id = message.photo[-1].file_id
            file_name = f'check_{user_id}_{int(message.date.timestamp())}.jpg'  # Для фото сохраняем как .jpg
        elif message.document:
            file_id = message.document.file_id
            file_name = message.document.file_name.lower()  # Сохраняем исходное название файла

            # Проверяем разрешенные расширения
            allowed_extensions = {"jpg", "webp", "png", "pdf"}
            if not any(file_name.endswith(f".{ext}") for ext in allowed_extensions):
                await message.answer("Файл имеет неподдерживаемый формат. Допустимые форматы: jpg, webp, png, pdf.")
                return

        # Путь для сохранения чека на сервере
        file_path = f'Admin_Panel/Check/{file_name}'  # Сохраняем файл с оригинальным именем

        # Скачиваем файл
        file = await bot.get_file(file_id)
        await file.download(file_path)

        # Получаем данные из состояния FSM
        data = await state.get_data()
        cart_items = data.get('cart_items', [])
        total_sum = data.get('total_sum', 0)
        address = data.get('address', "Неизвестный адрес")
        phone_number = data.get('phone_number', "Неизвестный номер")
        restaurant_name = data.get('restaurant_name', "Неизвестный ресторан")

        # Преобразуем список блюд в текстовый формат
        dishes = [f"{item['dish_name']} x{item['quantity']}" for item in cart_items]

        # Сохраняем заказ в базе данных
        cursor_payment.execute('''
            INSERT INTO orders (telegram_id, dishes, total_amount, receipt, address, phone_number, restaurant_name, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, ", ".join(dishes), total_sum, file_path,
            address, phone_number, restaurant_name, "На проверке"
        ))
        conn_payment.commit()

        # Уведомляем пользователя
        await message.answer("Ваш заказ принят и находится на проверке. Мы свяжемся с вами после подтверждения!")

        # Завершаем процесс
        await state.finish()

    except Exception as e:
        logging.error(f"Ошибка в процессе обработки чека: {e}")
        await message.answer("Произошла ошибка при обработке вашего чека. Попробуйте позже.")


def get_dish_id_by_name(dish_name: str):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT dish_id FROM menu WHERE dish_name = ?", (dish_name,))
        result = cursor.fetchone()
        if result:
            return result[0]  # Возвращаем dish_id
        else:
            return None  # Если блюдо не найдено
    except Exception as e:
        print(f"Ошибка при получении dish_id для {dish_name}: {e}")
        return None


def get_restaurant_name_by_dish(dish_id):
    cursor.execute('''
        SELECT restaurants.name
        FROM menu
        JOIN restaurants ON menu.restaurant_id = restaurants.id
        WHERE menu.id = ?
    ''', (dish_id,))
    result = cursor.fetchone()
    return result[0] if result else "Неизвестный ресторан"


# Проверка наличия адреса и телефона в профиле
def check_user_profile(user_id):
    cursor.execute('SELECT address, phone_number FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = cursor.fetchone()
    return profile if profile else None


# Обработчик кнопки "confirm_payment" (подтверждение оплаты)
@dp.callback_query_handler(lambda c: c.data.startswith('confirm_payment_'))
async def confirm_payment(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split('_')[2])  # Получаем user_id из callback_data

    # Удаление товаров из корзины
    cursor_cart.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    conn.commit()

    await bot.send_message(user_id, "Оплата подтверждена, заказ принят. Спасибо!")
    await bot.send_message(callback_query.from_user.id, "Оплата подтверждена, корзина очищена.")


# Обработчик кнопки "contact_user" (связаться с покупателем)
@dp.callback_query_handler(lambda c: c.data.startswith('contact_user_'))
async def contact_user(callback_query: types.CallbackQuery):
    user_id = int(callback_query.data.split('_')[2])  # Получаем user_id из callback_data

    # Отправка контактных данных менеджера пользователю
    await bot.send_message(user_id, "Менеджер ресторана: @manager_username")


@dp.callback_query_handler(lambda callback_query: callback_query.data == "edit_cart")
async def edit_cart(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    logging.info(f"ID пользователя: {user_id}")

    # Получаем корзину
    cart_items, total_sum, account_number = get_cart(user_id)
    logging.info(f"Данные корзины: {cart_items}")

    if cart_items:
        keyboard = InlineKeyboardMarkup(row_width=2)
        for item in cart_items:
            dish_name = item['dish_name']
            quantity = item['quantity']
            item_id = cart_items.index(item)
            logging.info(f"Добавляем кнопку для: {dish_name}, ID: {item_id}, Количество: {quantity}")
            keyboard.add(
                InlineKeyboardButton(f"➕ {dish_name} (x{quantity})", callback_data=f"edit_{item_id}")
            )

        keyboard.add(InlineKeyboardButton("❌ Удалить все товары", callback_data="remove_all"))
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_cart"))
        await callback_query.message.edit_text("Выберите товар для редактирования:", reply_markup=keyboard)
    else:
        logging.warning("Корзина пуста.")
        await callback_query.answer("Ваша корзина пуста, нечего редактировать.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data == "remove_all")
async def remove_all_cart(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    logging.info(f"Обработка запроса на удаление всех товаров из корзины для user_id={user_id}")

    try:
        # Выполним удаление товаров
        cursor_cart.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn_cart.commit()

        # Уведомление о выполненной операции
        await callback_query.answer("Все товары удалены из корзины.")
        await callback_query.message.edit_text("Ваша корзина пуста.")
    except Exception as e:
        logging.error(f"Ошибка при удалении товаров из корзины: {e}")
        await callback_query.answer("Произошла ошибка при удалении товаров. Попробуйте позже.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("edit_"))
async def edit_item(callback_query: types.CallbackQuery):
    try:
        user_id = callback_query.from_user.id
        item_id = int(callback_query.data.split("_")[1])

        cart_items, total_sum, _ = get_cart(user_id)

        if item_id >= len(cart_items):
            await callback_query.answer("Неверный выбор товара.", show_alert=True)
            return

        item = cart_items[item_id]

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("➕ Увеличить количество", callback_data=f"increase_{item_id}"),
            InlineKeyboardButton("➖ Уменьшить количество", callback_data=f"decrease_{item_id}"),
            InlineKeyboardButton("❌ Удалить товар", callback_data=f"remove_{item_id}")
        )

        await callback_query.message.edit_text(f"Редактирование товара: {item['dish_name']} (x{item['quantity']})",
                                               reply_markup=keyboard)
    except Exception as e:
        await callback_query.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("increase_"))
async def increase_item(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    item_id = int(callback_query.data.split("_")[1])

    cursor_cart.execute("SELECT dish_id, quantity FROM cart WHERE user_id = ?", (user_id,))
    cart_items = cursor_cart.fetchall()

    dish_id, quantity = cart_items[item_id]
    new_quantity = quantity + 1

    # Обновляем количество в базе данных
    cursor_cart.execute("UPDATE cart SET quantity = ? WHERE user_id = ? AND dish_id = ?",
                        (new_quantity, user_id, dish_id))
    conn_cart.commit()

    # Обновляем клавиатуру с актуальными данными
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(f"➕ Увеличить количество (x{new_quantity})", callback_data=f"increase_{item_id}"),
        InlineKeyboardButton(f"➖ Уменьшить количество (x{new_quantity})", callback_data=f"decrease_{item_id}"),
        InlineKeyboardButton(f"❌ Удалить товар", callback_data=f"remove_{item_id}")
    )

    # Обновляем сообщение с новым количеством товара
    await callback_query.message.edit_text(f"Количество товара {dish_id} теперь: {new_quantity}.",
                                           reply_markup=keyboard)
    await callback_query.answer()


@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("decrease_"))
async def decrease_item(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    item_id = int(callback_query.data.split("_")[1])

    cursor_cart.execute("SELECT dish_id, quantity FROM cart WHERE user_id = ?", (user_id,))
    cart_items = cursor_cart.fetchall()

    dish_id, quantity = cart_items[item_id]
    new_quantity = max(1, quantity - 1)  # Не позволяет уменьшить количество до нуля

    # Обновляем количество в базе данных
    cursor_cart.execute("UPDATE cart SET quantity = ? WHERE user_id = ? AND dish_id = ?",
                        (new_quantity, user_id, dish_id))
    conn_cart.commit()

    # Обновляем клавиатуру с актуальными данными
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(f"➕ Увеличить количество (x{new_quantity})", callback_data=f"increase_{item_id}"),
        InlineKeyboardButton(f"➖ Уменьшить количество (x{new_quantity})", callback_data=f"decrease_{item_id}"),
        InlineKeyboardButton(f"❌ Удалить товар", callback_data=f"remove_{item_id}")
    )

    # Обновляем сообщение с новым количеством товара
    await callback_query.message.edit_text(f"Количество товара {dish_id} теперь: {new_quantity}.",
                                           reply_markup=keyboard)
    await callback_query.answer()  # Подтверждаем обработку запроса без отображения alert


# Обработчик для удаления товара из корзины
@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("remove_"))
async def remove_item(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    item_id = int(callback_query.data.split("_")[1])

    cursor_cart.execute("SELECT dish_id FROM cart WHERE user_id = ?", (user_id,))
    cart_items = cursor_cart.fetchall()

    dish_id = cart_items[item_id][0]  # Извлекаем dish_id

    cursor_cart.execute("DELETE FROM cart WHERE user_id = ? AND dish_id = ?", (user_id, dish_id))
    conn_cart.commit()

    await callback_query.answer(f"Товар {dish_id} удалён из корзины.")
    await callback_query.message.edit_text(f"Товар {dish_id} удалён из вашей корзины.")


# Отображение профиля
@dp.message_handler(lambda message: message.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user_id = message.from_user.id

    # Получение профиля пользователя
    cursor.execute('''
        SELECT full_name, address, phone_number, city_id
        FROM user_profiles
        WHERE user_id = ?
    ''', (user_id,))
    profile = cursor.fetchone()

    # Если данных профиля нет, устанавливаем значения "Не заполнено"
    full_name = profile[0] if profile and profile[0] else "Не заполнено"
    address = profile[1] if profile and profile[1] else "Не заполнено"
    phone_number = profile[2] if profile and profile[2] else "Не заполнено"

    # Получаем название города по city_id
    city_name = "Не выбрано"
    if profile and profile[3]:
        cursor.execute("SELECT name FROM cities WHERE id = ?", (profile[3],))
        city = cursor.fetchone()
        if city:
            city_name = city[0]

    # Формируем сообщение профиля
    profile_text = (
        f"👤 *Ваш профиль:*\n"
        f"— ФИО: {full_name}\n"
        f"— Адрес доставки: {address}\n"
        f"— Номер телефона: {phone_number}\n"
        f"— Город: {city_name}"
    )

    # Формируем кнопки
    profile_keyboard = InlineKeyboardMarkup(row_width=1)
    profile_keyboard.add(
        InlineKeyboardButton("Добавить/Изменить ФИО", callback_data="1"),
        InlineKeyboardButton("Добавить/Изменить адрес", callback_data="2"),
        InlineKeyboardButton("Добавить/Изменить номер телефона", callback_data="3"),
        InlineKeyboardButton("Изменить город", callback_data="4")
    )

    await message.answer(profile_text, reply_markup=profile_keyboard, parse_mode="Markdown")


def verify_address_with_city(address, city_id):
    cursor.execute("SELECT name FROM cities WHERE id = ?", (city_id,))
    city = cursor.fetchone()

    if not city:
        return False  # Если город не найден, адрес считается несоответствующим

    city_name = city[0].lower()
    return city_name in address.lower()


@dp.callback_query_handler(lambda c: c.data == "1")
async def edit_full_name(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("Введите ваше имя:")
    await EditProfileFSM.waiting_for_address.set()


@dp.message_handler(state=EditProfileFSM.waiting_for_full_name)
async def save_full_name(message: types.Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        full_name = message.text

        logging.info(f"Получены данные ФИО: {full_name}")
        cursor.execute('''  
            INSERT INTO user_profiles (user_id, full_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET full_name = ? 
        ''', (user_id, full_name, full_name))
        conn.commit()

        await state.finish()
        logging.info("Данные успешно сохранены.")
        await show_profile(message)
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных: {str(e)}")
        await message.answer("Произошла ошибка при сохранении данных. Попробуйте позже.")


@dp.callback_query_handler(lambda c: c.data == "2")
async def edit_address(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("Введите ваш адрес доставки:")
    await EditProfileFSM.waiting_for_address.set()


@dp.message_handler(state=EditProfileFSM.waiting_for_address)
async def save_address(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    address = message.text

    # Получаем city_id пользователя из базы данных
    cursor.execute("SELECT city_id FROM user_profiles WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result or not result[0]:
        await message.answer("Пожалуйста, сначала выберите город в профиле.")
        return

    city_id = result[0]  # Берем city_id из базы данных

    # Проверяем, соответствует ли адрес выбранному городу
    if not verify_address_with_city(address, city_id):
        await message.answer("Ваш адрес не совпадает с выбранным городом. Пожалуйста, проверьте данные.")
        return

    # Сохраняем адрес в базе данных
    cursor.execute('''
        INSERT INTO user_profiles (user_id, address)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET address = ?
    ''', (user_id, address, address))
    conn.commit()

    await state.finish()
    await show_profile(message)


@dp.callback_query_handler(lambda c: c.data == "3")
async def edit_phone(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("Введите ваш номер телефона:")
    await EditProfileFSM.waiting_for_phone.set()


@dp.message_handler(state=EditProfileFSM.waiting_for_phone)
async def save_phone(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    phone_number = message.text

    cursor.execute('''
        INSERT INTO user_profiles (user_id, phone_number)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET phone_number = ?
    ''', (user_id, phone_number, phone_number))
    conn.commit()

    await state.finish()
    await show_profile(message)


@dp.callback_query_handler(lambda c: c.data == "4")
async def edit_city(callback_query: types.CallbackQuery):
    # Формируем список городов из базы
    keyboard = InlineKeyboardMarkup(row_width=2)
    cursor.execute("SELECT id, name FROM cities")
    cities = cursor.fetchall()
    for city_id, name in cities:
        keyboard.add(InlineKeyboardButton(name, callback_data=f"set_city_{city_id}"))

    await callback_query.message.edit_text("Выберите ваш город:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("set_city_"))
async def set_city(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    city_id = int(callback_query.data.split("_")[2])

    cursor.execute('''
        INSERT INTO user_profiles (user_id, city_id)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET city_id = ?
    ''', (user_id, city_id, city_id))
    conn.commit()

    await callback_query.message.edit_text("Город успешно обновлен!")
    await show_profile(callback_query.message)


@dp.message_handler(lambda message: message.text == "🍽️ Меню")
async def show_menu(message: types.Message):
    """
    Display the categories of dishes available.
    """
    keyboard = InlineKeyboardMarkup(row_width=2)
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    for cat_id, name in categories:
        keyboard.insert(InlineKeyboardButton(f"{name}", callback_data=f"category_{cat_id}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))
    await message.answer("Выберите категорию:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("category_"))
async def select_restaurant(callback_query: types.CallbackQuery):
    """
    Display the list of restaurants for the selected category.
    """
    category_id = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id

    # Retrieve user's city from their profile
    cursor.execute("SELECT city_id FROM user_profiles WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result or not result[0]:
        await bot.answer_callback_query(callback_query.id)
        await callback_query.message.edit_text("Сначала выберите ваш город в профиле.")
        return

    city_id = result[0]

    # Get restaurants in the selected city and category
    cursor.execute("SELECT id, name FROM restaurants WHERE city_id = ? AND category_id = ?", (city_id, category_id))
    restaurants = cursor.fetchall()

    if not restaurants:
        await bot.answer_callback_query(callback_query.id)
        await callback_query.message.edit_text("В выбранном городе нет ресторанов для этой категории.")
        return

    # Create a keyboard with the list of restaurants
    keyboard = InlineKeyboardMarkup(row_width=1)
    for rest_id, rest_name in restaurants:
        keyboard.add(InlineKeyboardButton(rest_name, callback_data=f"restaurant_{rest_id}_{category_id}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"main_menu"))  # Back button

    try:
        await callback_query.message.edit_text("Выберите ресторан:", reply_markup=keyboard)
    except MessageNotModified:
        pass

    await bot.answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data.startswith("restaurant_"))
async def select_dishes(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    try:
        restaurant_id = int(data[1])  # Parse restaurant ID
        category_id = int(data[2])  # Parse category ID
    except (ValueError, IndexError):
        await callback_query.answer("Некорректные данные. Попробуйте снова.", show_alert=True)
        return

    # Debug: Print selected restaurant
    print(f"Выбранный ресторан ID: {restaurant_id}")

    # Retrieve restaurant details
    cursor.execute('''
        SELECT name, weekdays_schedule, weekend_schedule, closed_days
        FROM restaurants
        WHERE id = ?
    ''', (restaurant_id,))
    restaurant = cursor.fetchone()

    if not restaurant:
        await callback_query.message.edit_text("Ресторан не найден.")
        return

    # Unpack restaurant details
    restaurant_name, weekdays_schedule, weekend_schedule, closed_days = restaurant
    print(f"Название ресторана: {restaurant_name}")
    print(f"График работы: будни - {weekdays_schedule}, выходные - {weekend_schedule}, нерабочие дни - {closed_days}")

    # Retrieve dishes for the selected restaurant and category
    cursor.execute('''
        SELECT id, dish_name FROM menu
        WHERE restaurant_id = ? AND category_id = ?
    ''', (restaurant_id, category_id))
    dishes = cursor.fetchall()

    # Check if the restaurant is currently open
    import pytz
    from datetime import datetime
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    current_day = now.strftime('%A')  # Current day (e.g., 'Monday')
    current_time = now.strftime('%H:%M')  # Current time (HH:MM)

    # Check if the restaurant is closed on the current day
    if closed_days and current_day in closed_days.split(","):
        await callback_query.answer(
            f"Ресторан сейчас закрыт. Не рабочие дни: {closed_days}",
            show_alert=True
        )
        return

    # Check the operating schedule
    def time_to_datetime(time_str):
        return datetime.strptime(time_str, "%H:%M")

    is_open = False
    if current_day in ['Saturday', 'Sunday']:  # Weekend schedule
        if weekend_schedule:
            start, end = weekend_schedule.split("-")
            if time_to_datetime(start) <= time_to_datetime(current_time) <= time_to_datetime(end):
                is_open = True
    else:  # Weekday schedule
        if weekdays_schedule:
            start, end = weekdays_schedule.split("-")
            if time_to_datetime(start) <= time_to_datetime(current_time) <= time_to_datetime(end):
                is_open = True

    # If the restaurant is open, display the dishes
    if is_open:
        if dishes:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for dish_id, dish_name in dishes:
                # Include restaurant_id and category_id in the callback data
                keyboard.add(
                    InlineKeyboardButton(dish_name, callback_data=f"dish_{dish_id}_{restaurant_id}_{category_id}"))
            keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"category_{category_id}"))  # Back button

            await callback_query.message.edit_text("Выберите блюдо:", reply_markup=keyboard)
        else:
            await callback_query.message.edit_text("В данном ресторане нет доступных блюд.")
        await bot.answer_callback_query(callback_query.id)
    else:
        # Construct a message explaining why the restaurant is closed
        closed_days_text = f"Не рабочие дни: {', '.join(closed_days.split(','))}" if closed_days else ""
        weekdays_text = f"График работы по будням: {weekdays_schedule}" if weekdays_schedule else ""
        weekend_text = f"График работы по выходным: {weekend_schedule}" if weekend_schedule else ""

        full_message = "\n".join(filter(None, [weekdays_text, weekend_text, closed_days_text]))

        await callback_query.answer(
            f"В данный момент ресторан не работает.\n{full_message}",
            show_alert=True
        )


def normalize_path(path):
    """
    Убирает двойные слеши (// или \\) и приводит путь к единому формату.
    """
    cleaned_path = re.sub(r'[\\/]+', '/', path)
    return cleaned_path


@dp.callback_query_handler(lambda c: c.data.startswith("dish_"))
async def show_dish_info(callback_query: types.CallbackQuery):
    """
    Display detailed information about the selected dish.
    """
    data = callback_query.data.split("_")
    try:
        dish_id = int(data[1])  # ID of the dish
        restaurant_id = int(data[2])  # ID of the restaurant
        category_id = int(data[3])  # ID of the category
    except (ValueError, IndexError):
        await callback_query.answer("Некорректные данные. Попробуйте снова.", show_alert=True)
        return

    # Retrieve dish details
    cursor.execute('''
        SELECT dish_name, description, price, image_path
        FROM menu
        WHERE id = ?
    ''', (dish_id,))
    dish = cursor.fetchone()

    if not dish:
        await callback_query.message.edit_text("Информация о блюде недоступна.")
        return

    dish_name, description, price, image_path = dish
    text = f"🍽️ *Блюдо:* {dish_name}\n📜 *Описание:* {description}\n💰 *Цена:* {price}₽"

    # Create keyboard
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🛒 Добавить в корзину", callback_data=f"add_to_cart_{dish_id}"))
    keyboard.add(InlineKeyboardButton("📝 Отзывы", callback_data=f"feedback_{dish_id}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"restaurant_{restaurant_id}_{category_id}"))

    if image_path:
        # Добавляем 'Admin_Panel' к относительному пути
        image_path = os.path.join('Admin_Panel', image_path)

    # Нормализуем путь для корректной работы
    normalized_path = normalize_path(image_path)
    print(normalized_path)

    try:
        # Открываем файл по относительному пути
        with open(normalized_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=callback_query.from_user.id,
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
    except FileNotFoundError:
        await bot.send_message(callback_query.from_user.id, "Изображение не найдено. Проверьте настройки.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, f"Ошибка при отправке изображения: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith("feedback_"))
async def feedback(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    try:
        dish_id = int(data[1])  # ID of the dish
    except (ValueError, IndexError):
        await callback_query.answer("Некорректные данные. Попробуйте снова.", show_alert=True)
        return

    # Retrieve restaurant and category ID from the database based on dish_id
    cursor.execute('''SELECT restaurant_id, category_id, reviews FROM menu WHERE id = ?''', (dish_id,))
    dish_info = cursor.fetchone()

    if not dish_info:
        await callback_query.answer("Информация о блюде недоступна.", show_alert=True)
        return

    restaurant_id, category_id, reviews_json = dish_info

    # Parse reviews JSON and calculate the average rating
    reviews = json.loads(reviews_json) if reviews_json else []
    if reviews:
        average_rating = sum(review['rating'] for review in reviews) / len(reviews)
        reviews_text = "\n".join([f"— {review['rating']}⭐️" for review in reviews])
        text = (
            f"Средний рейтинг: {average_rating:.1f}⭐️\n\n"
            f"Отзывы:\n{reviews_text}"
        )
    else:
        text = "Отзывов пока что нет."

    # Create the "Back" button to return to the dish details
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"dish_{dish_id}_{restaurant_id}_{category_id}"))

    await bot.send_message(callback_query.from_user.id, text, reply_markup=keyboard, parse_mode='Markdown')


@dp.callback_query_handler(lambda c: c.data.startswith("add_to_cart_"))
async def add_to_cart(callback_query: types.CallbackQuery):
    try:
        logging.info(f"Получен callback_data: {callback_query.data}")
        dish_id = int(callback_query.data[len("add_to_cart_"):])  # Извлекаем dish_id из callback_data
        user_id = callback_query.from_user.id

        # Получение информации о блюде по dish_id
        cursor.execute("SELECT dish_name, restaurant_id FROM menu WHERE id = ?", (dish_id,))
        dish = cursor.fetchone()

        if not dish:
            raise ValueError(f"Блюдо с ID '{dish_id}' не найдено в базе данных.")

        dish_name, restaurant_id = dish
        logging.info(f"Ресторан блюда: {restaurant_id}, Название блюда: {dish_name}")

        # Получение всех товаров в корзине
        cursor_cart.execute("SELECT dish_id FROM cart WHERE user_id = ?", (user_id,))
        cart_items = cursor_cart.fetchall()
        logging.info(f"ID товаров в корзине для user_id={user_id}: {cart_items}")

        # Проверка ресторанов в корзине
        if cart_items:
            dish_ids = [item[0] for item in cart_items]
            cursor.execute(
                "SELECT DISTINCT restaurant_id FROM menu WHERE id IN ({})".format(
                    ",".join("?" * len(dish_ids))
                ), dish_ids
            )
            cart_restaurants = cursor.fetchall()
            logging.info(f"Рестораны в корзине: {cart_restaurants}")

            # Проверка совпадения ресторанов
            cart_restaurant_ids = {row[0] for row in cart_restaurants}
            if len(cart_restaurant_ids) > 1 or restaurant_id not in cart_restaurant_ids:
                await callback_query.answer(
                    "В корзине уже есть блюда из другого ресторана. Очистите корзину, чтобы добавить блюда из этого "
                    "ресторана.",
                    show_alert=True
                )
                logging.warning("Добавление заблокировано: конфликт ресторанов.")
                return

        # Добавление блюда в корзину
        cursor_cart.execute(
            "SELECT id, quantity FROM cart WHERE user_id = ? AND dish_id = ?", (user_id, dish_id)
        )
        existing_item = cursor_cart.fetchone()

        if existing_item:
            # Если блюдо уже есть, увеличиваем количество
            cursor_cart.execute(
                "UPDATE cart SET quantity = quantity + 1 WHERE id = ?", (existing_item[0],)
            )
            new_quantity = existing_item[1] + 1
        else:
            # Если блюда нет, добавляем его
            cursor_cart.execute(
                "INSERT INTO cart (user_id, dish_id, quantity) VALUES (?, ?, ?)",
                (user_id, dish_id, 1)
            )
            new_quantity = 1

        conn_cart.commit()

        logging.info(
            f"Добавлено в корзину: user_id={user_id}, dish_name={dish_name}, quantity={new_quantity}"
        )
        await callback_query.answer(f"Блюдо '{dish_name}' добавлено в корзину!")
    except ValueError as e:
        logging.error(f"Ошибка: {e}")
        await callback_query.answer("Произошла ошибка: некорректные данные.")
    except Exception as e:
        logging.error(f"Ошибка при добавлении в корзину: {e}")
        await callback_query.answer("Произошла ошибка при добавлении блюда.")


async def notify_user(order_id, status):
    try:
        # Получаем информацию о заказе
        cursor_payment.execute('SELECT telegram_id FROM orders WHERE id = ?', (order_id,))
        result = cursor_payment.fetchone()

        if not result:
            logging.warning(f"Заказ с ID {order_id} не найден.")
            return

        user_id = result[0]

        if status == "Approved":
            message = ("Ваш заказ одобрен. Ожидайте. При поступлении вопросов с вами свяжется менеджер. "
                       "Также вы можете связаться с техподдержкой: help@eda.ru")
        elif status == "Rejected":
            message = ("Упс.. Ваш заказ отклонён. Если менеджер отклонил заказ, на то есть причина. "
                       "Если оплата не была произведена, не тратьте своё и наше время. "
                       "В ином случае свяжитесь с нами для возврата средств: help@eda.ru")
        else:
            logging.warning(f"Неизвестный статус: {status}")
            return

        # Отправляем сообщение пользователю
        await bot.send_message(user_id, message)
        logging.info(f"Пользователь {user_id} уведомлён о статусе заказа {order_id}.")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления для заказа {order_id}: {e}")


async def send_review_request(user_id, dish_name):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for rating in range(1, 6):
        keyboard.add(InlineKeyboardButton(f"{rating}⭐️", callback_data=f"rate_{rating}_{dish_name}"))
        await asyncio.sleep(3600)
    await bot.send_message(
        user_id,
        f"Как вы оцениваете блюдо '{dish_name}'? Оставьте отзыв от 1 до 5 звёзд:",
        reply_markup=keyboard
    )


async def monitor_order_status():
    while True:
        try:
            cursor_payment.execute('''
                SELECT id, telegram_id, dishes, status 
                FROM orders 
                WHERE status = 'Approved' AND (notified_review IS NULL OR notified_review = 0)
            ''')
            orders = cursor_payment.fetchall()

            for order_id, telegram_id, dishes, status in orders:
                # Проверяем, есть ли данные о блюдах
                if not dishes:
                    logging.warning(f"У заказа {order_id} отсутствуют данные о блюдах.")
                    continue

                # Извлекаем название первого блюда
                first_dish = dishes.split(",")[0]  # Берём первый элемент списка блюд
                dish_name = re.sub(r"x\d+$", "", first_dish).strip()  # Убираем количество (например, "x5")

                # Отправляем запрос на отзыв
                await asyncio.create_task(send_review_request(telegram_id, dish_name))

                # Помечаем заказ как уведомлённый о необходимости оставить отзыв
                cursor_payment.execute('UPDATE orders SET notified_review = 1 WHERE id = ?', (order_id,))
                conn_payment.commit()

            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Ошибка при мониторинге статусов заказов: {e}")
            await asyncio.sleep(10)


@dp.callback_query_handler(lambda c: c.data.startswith("rate_"))
async def handle_rating(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    try:
        rating = int(data[1])
        dish_name = "_".join(data[2:])  # На случай, если название блюда содержит символы "_"
        user_id = callback_query.from_user.id

        # Получение текущих отзывов
        cursor.execute('SELECT reviews FROM menu WHERE dish_name = ?', (dish_name,))
        result = cursor.fetchone()
        reviews = json.loads(result[0]) if result and result[0] else []

        # Добавляем новый отзыв
        reviews.append({"user_id": user_id, "rating": rating})
        cursor.execute('UPDATE menu SET reviews = ? WHERE dish_name = ?', (json.dumps(reviews), dish_name))
        conn.commit()

        await callback_query.answer(f"Спасибо за вашу оценку {rating}⭐️ для блюда '{dish_name}'!")
    except Exception as e:
        logging.error(f"Ошибка обработки рейтинга: {e}")
        await callback_query.answer("Произошла ошибка при обработке вашего рейтинга.")


# Интеграция с ботом
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_order_status())  # Постоянный мониторинг заказов
    executor.start_polling(dp, skip_updates=True)
