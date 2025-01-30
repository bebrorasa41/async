import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message

# 🔹 Укажите свой токен от BotFather
TOKEN = "7523023045:AAHue_1jPpvGD-q4mNwskVKFbgaXA00fcIE"

# 🔹 Укажите API-токен UsersBox
USERSBOX_API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkX2F0IjoxNzM4MjMwMDczLCJhcHBfaWQiOjE3MzgyMzAwNzN9.tMcpZxg94S9kYvwi8LsWoGxGjmEH0O2qFjhY-wlgIKg"

# 🔹 Базовый URL API UsersBox
USERSBOX_API_URL = "https://api.usersbox.ru/v1/search"

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# 🔍 Доступные параметры поиска в UsersBox
SEARCH_PARAMETERS = """
🔍 *Бот может искать по следующим данным:*
- 📞 *Телефон:* `+79279663494`
- 🏠 *Адрес:* `Москва, Шипиловская улица, 28А`
- 👤 *ФИО:* `Андрей Михайлович Иванов 25.11.1990`
- 🔗 *Username:* `elonmusk`
- 📧 *Email:* `ceo@vkontakte.ru`
- 🌍 *IP-адрес:* `77.88.0.10`
- 🔗 *Ссылка на профиль VK:* `https://vk.com/id13141150`

💡 _Отправьте один из этих типов данных, и я попробую найти всю доступную информацию!_
"""

@dp.message(Command("start", "help"))
async def start_command(message: Message):
    """Обработчик команды /start и /help"""
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я могу искать информацию по различным параметрам.\n"
        "Просто отправьте данные (например, телефон, email или IP), и я попробую найти результат!\n\n"
        "📌 *Вот список того, что я могу искать:*",
        parse_mode="Markdown"
    )
    await message.answer(SEARCH_PARAMETERS, parse_mode="Markdown")

async def search_usersbox(query: str) -> str:
    """Функция поиска информации в UsersBox"""
    headers = {
        "Authorization": USERSBOX_API_TOKEN
    }
    params = {"q": query}

    try:
        response = requests.get(USERSBOX_API_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("data"):
            return "❌ Ничего не найдено по этому запросу."

        # 🔍 Формируем ответ с найденной информацией
        result = "✅ *Найденная информация:*\n\n"
        for entry in data["data"]:
            for key, value in entry.items():
                result += f"• *{key.capitalize()}*: `{value}`\n"
            result += "\n"

        return result
    except requests.exceptions.RequestException as e:
        return f"🚨 Ошибка при запросе к API: {str(e)}"

@dp.message()
async def handle_query(message: Message):
    """Обработчик текстовых сообщений для поиска в UsersBox"""
    query = message.text.strip()
    
    if len(query) < 3:
        await message.answer("❗ Запрос слишком короткий. Введите минимум 3 символа.")
        return

    await message.answer("🔎 Выполняю поиск... Это может занять несколько секунд ⏳")
    
    result = await search_usersbox(query)
    
    await message.answer(result, parse_mode="Markdown")

async def main():
    """Запуск бота"""
    print("🤖 Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
