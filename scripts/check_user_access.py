"""
Скрипт для проверки возможности отправки сообщений пользователю
"""
import asyncio
import sys
from pathlib import Path

# Настройка кодировки для Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot
from config import BOT_TOKEN


async def check_user_access(user_id: int):
    """Проверить, может ли бот отправить сообщение пользователю"""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не установлен!")
        return
    
    bot = Bot(token=BOT_TOKEN)
    
    try:
        print(f"🔄 Проверка доступа к пользователю {user_id}...")
        
        # Пытаемся получить информацию о чате
        try:
            chat = await bot.get_chat(user_id)
            print(f"✅ Чат найден: {chat.type}")
            print(f"   Имя: {chat.first_name or 'Не указано'}")
            print(f"   Username: @{chat.username or 'Не указан'}")
        except Exception as e:
            print(f"❌ Не удалось получить информацию о чате: {e}")
            return
        
        # Пытаемся отправить тестовое сообщение
        try:
            test_message = await bot.send_message(
                chat_id=user_id,
                text="🧪 Тестовое сообщение от бота"
            )
            print(f"✅ Тестовое сообщение отправлено успешно!")
            print(f"   Message ID: {test_message.message_id}")
            
            # Удаляем тестовое сообщение
            try:
                await bot.delete_message(chat_id=user_id, message_id=test_message.message_id)
                print("✅ Тестовое сообщение удалено")
            except:
                pass
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Не удалось отправить сообщение: {error_msg}")
            
            if "chat not found" in error_msg.lower():
                print("\n💡 Проблема: Пользователь не начал диалог с ботом")
                print("   Решение: Пользователь должен написать боту /start")
            elif "bot was blocked" in error_msg.lower():
                print("\n💡 Проблема: Пользователь заблокировал бота")
                print("   Решение: Пользователь должен разблокировать бота")
            elif "forbidden" in error_msg.lower():
                print("\n💡 Проблема: Бот заблокирован пользователем или нет прав")
            else:
                print(f"\n💡 Неизвестная ошибка: {error_msg}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование: python scripts/check_user_access.py <user_id>")
        print("Пример: python scripts/check_user_access.py 8070278708")
        sys.exit(1)
    
    try:
        user_id = int(sys.argv[1])
        asyncio.run(check_user_access(user_id))
    except ValueError:
        print("❌ user_id должен быть целым числом")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
