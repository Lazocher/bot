import logging
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from database import get_cities, get_categories, add_restaurant, add_dish, add_category, get_restaurants, add_city, \
    delete_item, add_manager, delete_manager, authenticate_user, delete_dish, get_all_dishes, get_connection, \
    update_stop_list, get_stop_list
from flask import session
import sqlite3import os
import sqlite3
import logging
from datetime import datetime

import pytz
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
TOKEN = '7753898475:AAGcfz7iTs7llLxr6jq_ude78Pp14ee53Bg'

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
    keyboard.row(KeyboardButton("🏙️ Все рестораны"))  # Новая кнопка для отображения всех ресторанов

    # Удаляем сообщение, вызвавшее callback, чтобы избежать путаницы
    await callback_query.message.delete()

    # Отправляем новое сообщение с обычной клавиатурой
    await bot.send_message(callback_query.from_user.id, "Добро пожаловать в главное меню:", reply_markup=keyboard)

    # Отвечаем на callback, чтобы Telegram не показывал "часики"
    await callback_query.answer()


@dp.message_handler(lambda message: message.text == "🏙️ Все рестораны")
async def show_all_restaurants(message: types.Message):
    """Отображаем все рестораны в городе пользователя через инлайн кнопки."""
    user_id = message.from_user.id

    # Получаем город пользователя
    cursor.execute("SELECT city_id FROM user_profiles WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result or not result[0]:
        await message.reply("Сначала выберите ваш город в профиле.")
        return

    city_id = result[0]

    # Получаем список ресторанов в городе с их категориями
    cursor.execute("""
        SELECT r.id, r.name, r.category_id 
        FROM restaurants r
        WHERE r.city_id = ?
    """, (city_id,))
    restaurants = cursor.fetchall()

    if not restaurants:
        await message.reply("В вашем городе нет ресторанов.")
        return

    # Создаем инлайн клавиатуру с ресторанами
    keyboard = InlineKeyboardMarkup(row_width=1)
    for rest_id, rest_name, category_id in restaurants:
        keyboard.add(InlineKeyboardButton(
            rest_name,
            callback_data=f"restaurant_{rest_id}_{category_id}"  # передаем restaurant_id и category_id
        ))

    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="main_menu"))  # Кнопка назад для возвращения в главное меню

    # Отправляем сообщение с инлайн кнопками для ресторанов
    await message.reply("Все рестораны в вашем городе:", reply_markup=keyboard)


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
            response += f"🍽️ *Блюда:*\n{dishes.replace(', ', '')}\n"
            response += f"💵 *Общая сумма:* {total_amount}₩\n"
            response += f"🏨 *Ресторан:* {restaurant_name}\n"
            response += f"📍 *Адрес доставки:* {address}\n"
            response += f"📞 *Телефон получателя:* {phone_number}\n"
            response += f"📄 *Статус заказа:* {status}\n"
            if receipt:
                fixed_receipt_url = receipt.replace("Admin_Panel/", "")
                response += f"📂 [Скачать чек](http://127.0.0.1/{fixed_receipt_url})\n"
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
        # Получаем ID первого блюда в корзине
        cursor_cart.execute("SELECT dish_id FROM cart WHERE user_id = ?", (user_id,))
        first_dish_id = cursor_cart.fetchone()

        if first_dish_id:
            cursor.execute('''
                SELECT restaurants.name, restaurants.account_number
                FROM menu
                JOIN restaurants ON menu.restaurant_id = restaurants.id
                WHERE menu.id = ?
            ''', (first_dish_id[0],))
            restaurant_data = cursor.fetchone()

            if restaurant_data:
                restaurant_name = restaurant_data[0]
                account_number = restaurant_data[1]  # Получаем номер счета ресторана
            else:
                restaurant_name = "Неизвестный ресторан"
                account_number = "Неизвестен"

            # Сохраняем название ресторана в FSM
            await state.update_data(restaurant_name=restaurant_name)
        else:
            restaurant_name = "Неизвестный ресторан"
            account_number = "Неизвестен"

        # Формируем сообщение с корзиной
        cart_message = f"🏦 *Ресторан:* {restaurant_name}\n\n"
        cart_message += "🛒 *Ваша корзина:*\n"
        for item in cart_items:
            cart_message += f"🍽️ *{item['dish_name']}* (x{item['quantity']}) - {item['total']}₩\n"

        cart_message += f"\n💵 *Общая сумма:* {total_sum}₩\n"
        cart_message += f"🏦 *Счет ресторана:* ```{account_number}```"

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
        message += f"🍽️ *{item['dish_name']}* (x{item['quantity']}) - {item['total']}₩\n"

    message += f"\nОбщая сумма: {total_sum}₩"
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
        message += f"🍽️ *{item['dish_name']}* (x{item['quantity']}) - {item['total']}₩\n"

    message += f"\nСумма: {total_sum}₩"
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

    # Извлекаем данные профиля из базы данных
    cursor.execute('''
        SELECT full_name, address, phone_number, cities.name
        FROM user_profiles
        LEFT JOIN cities ON user_profiles.city_id = cities.id
        WHERE user_profiles.user_id = ?
    ''', (user_id,))
    profile_data = cursor.fetchone()

    if profile_data:
        full_name, address, phone_number, city_name = profile_data
    else:
        full_name, address, phone_number, city_name = (None, None, None, None)

    # Формируем текст профиля
    profile_text = "👤 Ваш профиль:\n"
    profile_text += f"— ФИО: {full_name if full_name else 'Не заполнено'}\n"
    profile_text += f"— Адрес доставки: {address if address else 'Не заполнено'}\n"
    profile_text += f"— Номер телефона: {phone_number if phone_number else 'Не заполнено'}\n"
    profile_text += f"— Город: {city_name if city_name else 'Не выбрано'}\n"

    # Формируем кнопки
    profile_keyboard = InlineKeyboardMarkup(row_width=1)
    profile_keyboard.add(
        InlineKeyboardButton("Добавить/Изменить ФИО", callback_data="1"),
        InlineKeyboardButton("Добавить/Изменить адрес", callback_data="2"),
        InlineKeyboardButton("Добавить/Изменить номер телефона", callback_data="3"),
        InlineKeyboardButton("Изменить город", callback_data="4")
    )

    await message.answer(profile_text, reply_markup=profile_keyboard, parse_mode="Markdown")

    @dp.callback_query_handler(lambda c: c.data == "1")
    async def edit_full_name(callback_query: types.CallbackQuery):
        await callback_query.message.edit_text("Введите ваше полное имя (ФИО):")
        await EditProfileFSM.waiting_for_full_name.set()

    @dp.message_handler(state=EditProfileFSM.waiting_for_full_name)
    async def save_full_name(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        full_name = message.text

        # Сохраняем ФИО в базу данных
        cursor.execute('''
            INSERT INTO user_profiles (user_id, full_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET full_name = ?
        ''', (user_id, full_name, full_name))
        conn.commit()

        await state.finish()
        await show_profile(message)

    @dp.callback_query_handler(lambda c: c.data == "2")
    async def edit_address(callback_query: types.CallbackQuery):
        await callback_query.message.edit_text("Введите ваш адрес доставки:")
        await EditProfileFSM.waiting_for_address.set()

    @dp.message_handler(state=EditProfileFSM.waiting_for_address)
    async def save_address(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        address = message.text

        # Сохраняем адрес в базе данных без проверки города
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

        # Сначала получим текущие данные пользователя (ФИО, адрес, номер телефона)
        cursor.execute('''
            SELECT full_name, address, phone_number
            FROM user_profiles
            WHERE user_id = ?
        ''', (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            full_name, address, phone_number = user_data
        else:
            full_name, address, phone_number = (None, None, None)

        cursor.execute('''
            INSERT INTO user_profiles (user_id, city_id, full_name, address, phone_number)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET city_id = ?, address = NULL
        ''', (user_id, city_id, full_name, address, phone_number, city_id))
        conn.commit()

        await callback_query.message.edit_text("Город успешно обновлен! Адрес сброшен.")
        # Извлекаем данные профиля из базы данных
        cursor.execute('''
                SELECT full_name, address, phone_number, cities.name
                FROM user_profiles
                LEFT JOIN cities ON user_profiles.city_id = cities.id
                WHERE user_profiles.user_id = ?
            ''', (user_id,))
        profile_data = cursor.fetchone()

        if profile_data:
            full_name, address, phone_number, city_name = profile_data
        else:
            full_name, address, phone_number, city_name = (None, None, None, None)

        # Формируем текст профиля
        profile_text = "👤 Ваш профиль:\n"
        profile_text += f"— ФИО: {full_name if full_name else 'Не заполнено'}\n"
        profile_text += f"— Адрес доставки: {address if address else 'Не заполнено'}\n"
        profile_text += f"— Номер телефона: {phone_number if phone_number else 'Не заполнено'}\n"
        profile_text += f"— Город: {city_name if city_name else 'Не выбрано'}\n"

        # Формируем кнопки
        profile_keyboard = InlineKeyboardMarkup(row_width=1)
        profile_keyboard.add(
            InlineKeyboardButton("Добавить/Изменить ФИО", callback_data="1"),
            InlineKeyboardButton("Добавить/Изменить адрес", callback_data="2"),
            InlineKeyboardButton("Добавить/Изменить номер телефона", callback_data="3"),
            InlineKeyboardButton("Изменить город", callback_data="4")
        )

        await message.answer(profile_text, reply_markup=profile_keyboard, parse_mode="Markdown")


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
    Отображает список ресторанов для выбранной категории.
    """
    category_id = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id

    # Получаем ID города пользователя
    cursor.execute("SELECT city_id FROM user_profiles WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if not result or not result[0]:
        await bot.answer_callback_query(callback_query.id)
        await callback_query.message.answer("Сначала выберите ваш город в профиле.")
        return

    city_id = result[0]

    # Получаем список ресторанов
    cursor.execute('''
        SELECT id, name, weekdays_schedule, weekend_schedule, closed_days
        FROM restaurants WHERE city_id = ? AND category_id = ?
    ''', (city_id, category_id))
    restaurants = cursor.fetchall()

    if not restaurants:
        await bot.answer_callback_query(callback_query.id)
        await callback_query.message.answer("В выбранном городе нет ресторанов для этой категории.")
        return

    # Проверяем статус ресторанов
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    current_day = now.strftime('%A')
    current_time = now.strftime('%H:%M')

    def time_to_datetime(time_str):
        return datetime.strptime(time_str, "%H:%M")

    keyboard = InlineKeyboardMarkup(row_width=1)
    for rest_id, rest_name, weekdays_schedule, weekend_schedule, closed_days in restaurants:
        is_open = True
        if closed_days and current_day in closed_days.split(","):
            is_open = False

        if is_open:
            if current_day in ['Saturday', 'Sunday'] and weekend_schedule:
                start, end = weekend_schedule.split("-")
                if not (time_to_datetime(start) <= time_to_datetime(current_time) <= time_to_datetime(end)):
                    is_open = False
            elif weekdays_schedule:
                start, end = weekdays_schedule.split("-")
                if not (time_to_datetime(start) <= time_to_datetime(current_time) <= time_to_datetime(end)):
                    is_open = False

        display_name = rest_name + " (\u23f0 закрыт)" if not is_open else rest_name
        keyboard.add(InlineKeyboardButton(display_name, callback_data=f"restaurant_{rest_id}_{category_id}"))

    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"main_menu"))

    try:
        if callback_query.message.text:
            await callback_query.message.edit_text("Выберите ресторан:", reply_markup=keyboard)
        else:
            await callback_query.message.answer("Выберите ресторан:", reply_markup=keyboard)
    except (MessageNotModified, BadRequest):
        await callback_query.message.answer("Выберите ресторан:", reply_markup=keyboard)

    await bot.answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data.startswith("restaurant_"))
async def select_dishes(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    try:
        restaurant_id = int(data[1])
        category_id = int(data[2])
    except (ValueError, IndexError):
        await callback_query.answer("Некорректные данные. Попробуйте снова.", show_alert=True)
        return

    cursor.execute('''
        SELECT name, weekdays_schedule, weekend_schedule, closed_days
        FROM restaurants WHERE id = ?
    ''', (restaurant_id,))
    restaurant = cursor.fetchone()

    if not restaurant:
        await callback_query.message.answer("Ресторан не найден.")
        return

    restaurant_name, weekdays_schedule, weekend_schedule, closed_days = restaurant

    cursor.execute('''
        SELECT id, dish_name FROM menu WHERE restaurant_id = ? AND category_id = ?
    ''', (restaurant_id, category_id))
    dishes = cursor.fetchall()

    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    current_day = now.strftime('%A')
    current_time = now.strftime('%H:%M')

    def time_to_datetime(time_str):
        return datetime.strptime(time_str, "%H:%M")

    is_open = False
    if current_day in ['Saturday', 'Sunday'] and weekend_schedule:
        start, end = weekend_schedule.split("-")
        if time_to_datetime(start) <= time_to_datetime(current_time) <= time_to_datetime(end):
            is_open = True
    elif weekdays_schedule:
        start, end = weekdays_schedule.split("-")
        if time_to_datetime(start) <= time_to_datetime(current_time) <= time_to_datetime(end):
            is_open = True

    keyboard = InlineKeyboardMarkup(row_width=1)
    if is_open:
        for dish_id, dish_name in dishes:
            if "Stopping" in dish_name:
                await callback_query.answer("Упс... Данного блюда нет в наличии", show_alert=True)
                continue
            keyboard.add(InlineKeyboardButton(dish_name, callback_data=f"dish_{dish_id}_{restaurant_id}_{category_id}"))
    else:
        for dish_id, dish_name in dishes:
            keyboard.add(InlineKeyboardButton(f"{dish_name} (\u23f0 не добавляется в корзину)", callback_data="ignore"))

    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"category_{category_id}"))

    try:
        if callback_query.message.text:
            await callback_query.message.edit_text(f"Выберите блюдо в ресторане {restaurant_name}:",
                                                   reply_markup=keyboard)
        else:
            await callback_query.message.answer(f"Выберите блюдо в ресторане {restaurant_name}:", reply_markup=keyboard)
    except (MessageNotModified, BadRequest):
        await callback_query.message.answer(f"Выберите блюдо в ресторане {restaurant_name}:", reply_markup=keyboard)

    await bot.answer_callback_query(callback_query.id)


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
    text = f"🍽️ *Блюдо:* {dish_name}\n📜 *Описание:* {description}\n💰 *Цена:* {price}₩"

    # Create keyboard
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🛒 Добавить в корзину", callback_data=f"add_to_cart_{dish_id}"))
    keyboard.add(InlineKeyboardButton("📝 Отзывы", callback_data=f"feedback_{dish_id}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"category_{category_id}"))  # Back button

    if image_path:
        # Добавляем 'Admin_Panel' к относительному пути
        image_path = os.path.join('admin_panel', image_path)

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
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"category_{category_id}"))  # Back button

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

        # Retrieve restaurant's schedule to check if it's open
        cursor.execute('''SELECT weekdays_schedule, weekend_schedule, closed_days FROM restaurants WHERE id = ?''', (restaurant_id,))
        restaurant_schedule = cursor.fetchone()

        # Получаем текущее время в нужной временной зоне
        seoul_tz = pytz.timezone('Asia/Seoul')
        now = datetime.now(seoul_tz)  # Инициализируем переменную 'now'
        current_day = now.strftime('%A')  # Текущий день недели (например, 'Monday')
        current_time = now.strftime('%H:%M')  # Текущее время в формате 'HH:MM'

        if restaurant_schedule:
            weekdays_schedule, weekend_schedule, closed_days = restaurant_schedule
            is_open = False
            current_day = now.strftime('%A')  # Current day (e.g., 'Monday')
            current_time = now.strftime('%H:%M')  # Current time (HH:MM)

            # Check if the restaurant is closed on the current day
            if closed_days and current_day in closed_days.split(","):
                await callback_query.answer(f"Ресторан закрыт. Не рабочие дни: {closed_days}", show_alert=True)
                return

            # Check the operating schedule
            def time_to_datetime(time_str):
                return datetime.strptime(time_str, "%H:%M")

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

            if not is_open:
                await callback_query.answer("Ресторан сейчас закрыт. Попробуйте позже.", show_alert=True)
                return

        # The rest of the code for adding the dish to the cart remains unchanged
        cursor_cart.execute("SELECT id, quantity FROM cart WHERE user_id = ? AND dish_id = ?", (user_id, dish_id))
        existing_item = cursor_cart.fetchone()

        if existing_item:
            # Если блюдо уже есть, увеличиваем количество
            cursor_cart.execute("UPDATE cart SET quantity = quantity + 1 WHERE id = ?", (existing_item[0],))
            new_quantity = existing_item[1] + 1
        else:
            # Если блюда нет, добавляем его
            cursor_cart.execute("INSERT INTO cart (user_id, dish_id, quantity) VALUES (?, ?, ?)", (user_id, dish_id, 1))
            new_quantity = 1

        conn_cart.commit()

        logging.info(f"Добавлено в корзину: user_id={user_id}, dish_name={dish_name}, quantity={new_quantity}")
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


async def monitor_order_status():
    while True:
        try:
            # Обрабатываем заказы со статусом Approved или Rejected
            cursor_payment.execute('''
                SELECT id, telegram_id, dishes, status 
                FROM orders 
                WHERE (status = 'Approved' OR status = 'Rejected') 
                AND (notified_review IS NULL OR notified_review = 0)
            ''')
            orders = cursor_payment.fetchall()

            for order_id, telegram_id, dishes, status in orders:
                if status == 'Approved':
                    # Отправляем уведомление об одобрении заказа
                    await bot.send_message(
                        telegram_id,
                        "Ваш заказ одобрен! Ожидайте, при поступлении вопросов с вами свяжутся по номеру телефона."
                    )

                    # Проверяем, есть ли данные о блюдах
                    if not dishes:
                        logging.warning(f"У заказа {order_id} отсутствуют данные о блюдах.")
                        continue

                    # Отправляем запрос на отзыв через 1 час
                    await asyncio.sleep(3600)  # 1 час (3600 секунд)
                    first_dish = dishes.split(",")[0]  # Берём первый элемент списка блюд
                    dish_name = re.sub(r"x\d+$", "", first_dish).strip()  # Убираем количество (например, "x5")
                    await send_review_request(telegram_id, dish_name)

                elif status == 'Rejected':
                    # Отправляем уведомление об отклонении заказа
                    await bot.send_message(
                        telegram_id,
                        (
                            "Упс... Заказ отменен. Скорее всего у менеджера были основания на отклонение вашего заказа."
                            "Если это так, не тратьте наше время. В ином случае за возвратом средств обращайтесь "
                            "pabi1978@gmail.com"
                        )
                    )

                # Помечаем заказ как уведомлённый
                cursor_payment.execute('UPDATE orders SET notified_review = 1 WHERE id = ?', (order_id,))
                conn_payment.commit()

            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Ошибка при мониторинге статусов заказов: {e}")
            await asyncio.sleep(10)


async def send_review_request(user_id, dish_name):
    keyboard = InlineKeyboardMarkup(row_width=1)
    for rating in range(1, 6):
        keyboard.add(InlineKeyboardButton(f"{rating}⭐️", callback_data=f"rate_{rating}_{dish_name}"))

    await bot.send_message(
        user_id,
        f"Как вы оцениваете блюдо '{dish_name}'? Оставьте отзыв от 1 до 5 звёзд:",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data.startswith("rate_"))
async def handle_rating(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    try:
        rating = int(data[1])
        dish_name = "_".join(data[2:])  # На случай, если название блюда содержит символы "_"
        user_id = callback_query.from_user.id

        # Проверка, оставлял ли пользователь уже отзыв для этого блюда
        cursor.execute('SELECT reviews FROM menu WHERE dish_name = ?', (dish_name,))
        result = cursor.fetchone()
        reviews = json.loads(result[0]) if result and result[0] else []

        # Проверяем, оставлял ли пользователь уже отзыв
        if any(review["user_id"] == user_id for review in reviews):
            await callback_query.answer("Упс... К сожалению вы уже оставили отзыв для этого блюда :(", show_alert=True)
            return

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
