import asyncio
import os
import tempfile
import zipfile
import py7zr
import rarfile
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument
import logging
import re
import time

# Constantsg
API_ID = "26519168"
API_HASH = "16cc9deec2d8f31d01389e3f2eea3574"
BOT_TOKEN = "8087322831:AAGu112QSLy4C5kEdmSRlP4lP5cXYPwf-KU"
SESSION_FILE = "МистерРобот.session"

# Directories for files
TEMP_DIR = "temp_files"
PROCESSED_DIR = "processed_files"

# Create directories
for directory in [TEMP_DIR, PROCESSED_DIR]:
    os.makedirs(directory, exist_ok=True)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# File processing constants
MAX_FILE_SIZE = 2 * 1024 * 1024  # 20 MB for filtering
MAX_TXT_SIZE = 2 * 1024 * 1024  # 20 MB for .txt files
BLOCKED_EXTENSIONS = ('.xls', '.xlsx', '.csv', '.sql')

class UserState:
    def __init__(self):
        self.client = None
        self.progress_message = None
        self.last_progress_update = 0

user_states = {}

async def parse_message_link(link: str) -> tuple:
    pattern = r"https?://t\.me/([^/]+)/(\d+)"
    match = re.match(pattern, link)
    if not match:
        raise ValueError("Неверный формат ссылки")
    return match.group(1), int(match.group(2))

async def progress_callback(current, total, user_state, message):
    now = time.time()
    if now - user_state.last_progress_update < 1:
        return
    
    user_state.last_progress_update = now
    progress = current / total * 100
    try:
        if user_state.progress_message:
            await user_state.progress_message.edit_text(f"Загрузка: {progress:.1f}%")
        else:
            user_state.progress_message = await message.answer(f"Загрузка: {progress:.1f}%")
    except Exception as e:
        logger.error(f"Ошибка при обновлении прогресса: {e}")

async def process_archive(input_path: str) -> tuple[str, list]:
    try:
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(PROCESSED_DIR, 'processed.zip')
        removed_files = []
        
        # Extract archive
        if input_path.endswith('.zip'):
            with zipfile.ZipFile(input_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        elif input_path.endswith('.7z'):
            with py7zr.SevenZipFile(input_path, 'r') as sz_ref:
                sz_ref.extractall(temp_dir)
        elif input_path.endswith('.rar'):
            with rarfile.RarFile(input_path, 'r') as rar_ref:
                rar_ref.extractall(temp_dir)
        
        # Create new filtered zip archive
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, temp_dir)
                    file_size = os.path.getsize(file_path)
                    
                    should_remove = False
                    reason = ""
                    
                    if file.lower().endswith('.txt'):
                        if file_size > MAX_TXT_SIZE:
                            should_remove = True
                            reason = "большой .txt файл"
                    else:
                        if file_size > MAX_FILE_SIZE:
                            should_remove = True
                            reason = "превышен размер"
                        elif any(file.lower().endswith(ext) for ext in BLOCKED_EXTENSIONS):
                            should_remove = True
                            reason = "запрещенное расширение"
                    
                    if should_remove:
                        removed_files.append(f"{rel_path} ({round(file_size/1024/1024, 2)} MB) - {reason}")
                        continue
                    
                    zip_out.write(file_path, rel_path)
        
        # Cleanup
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(temp_dir)
        
        return output_path, removed_files
    except Exception as e:
        raise Exception(f"Ошибка при обработке архива: {str(e)}")

async def download_file_from_message(client: TelegramClient, channel: str, message_id: int, user_state, message) -> str:
    try:
        telegram_message = await client.get_messages(channel, ids=message_id)
        if not telegram_message or not telegram_message.media:
            raise ValueError("Сообщение не содержит файла")

        if isinstance(telegram_message.media, MessageMediaDocument):
            file_name = telegram_message.file.name or f"file_{message_id}"
            if not file_name.endswith(('.zip', '.rar', '.7z')):
                raise ValueError("Файл не является архивом (.zip, .rar, .7z)")
            
            path = os.path.join(TEMP_DIR, file_name)
            
            await client.download_media(
                telegram_message,
                path,
                progress_callback=lambda current, total: progress_callback(
                    current, total, user_state, message
                )
            )
            
            if user_state.progress_message:
                await user_state.progress_message.delete()
                user_state.progress_message = None
            
            return path
        else:
            raise ValueError("Сообщение не содержит документа")
    except Exception as e:
        if user_state.progress_message:
            await user_state.progress_message.delete()
            user_state.progress_message = None
        raise Exception(f"Ошибка при скачивании файла: {str(e)}")

async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я бот для обработки архивов из Telegram.\n"
        "Просто отправьте мне ссылку на сообщение с архивом в формате:\n"
        "https://t.me/channel/123\n\n"
        "Я автоматически:\n"
        "1. Конвертирую архив в ZIP\n"
        "2. Удалю файлы больше 20 MB (кроме .txt)\n"
        "3. Удалю .txt файлы больше 20 MB\n"
        "4. Удалю файлы: xls, xlsx, csv, sql"
    )

async def handle_message(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_states:
        user_states[user_id] = UserState()
        user_states[user_id].client = TelegramClient(
            SESSION_FILE,
            API_ID,
            API_HASH,
            system_version="4.16.30-vxCUSTOM"
        )
        await user_states[user_id].client.connect()

    try:
        channel, message_id = await parse_message_link(message.text)
        await message.answer("Начинаю скачивание архива...")
        
        input_path = await download_file_from_message(
            user_states[user_id].client,
            channel,
            message_id,
            user_states[user_id],
            message
        )
        
        await message.answer("Архив скачан, начинаю обработку...")
        output_path, removed_files = await process_archive(input_path)
        
        report = "Обработка завершена!\n\n"
        if removed_files:
            report += "Удалены следующие файлы:\n"
            for file in removed_files:
                report += f"❌ {file}\n"
        else:
            report += "Файлы для удаления не найдены.\n"
        
        await message.answer_document(types.FSInputFile(output_path))
        await message.answer(report)
        
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
            
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.message.register(start_handler, Command(commands=['start']))
    dp.message.register(handle_message, lambda msg: msg.text and msg.text.startswith('http'))
    
    try:
        print("Бот запущен...")
        await dp.start_polling(bot)
    finally:
        for user_state in user_states.values():
            if user_state.client:
                await user_state.client.disconnect()
        await bot.session.close()
        
        for directory in [TEMP_DIR, PROCESSED_DIR]:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)

if __name__ == '__main__':
    asyncio.run(main())
