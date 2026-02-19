"""
Скрипт для повторной отправки фото модератора пользователю
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
from database.db import get_session
from database.queries import get_moderation_session_by_id, get_application_by_id
from sqlalchemy import select
from database.models import ModerationSession


async def resend_moderator_photo(application_id: int = None, session_id: int = None):
    """Повторно отправить фото модератора пользователю"""
    
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не установлен!")
        return
    
    bot = Bot(token=BOT_TOKEN)
    
    try:
        async for db_session in get_session():
            try:
                if application_id:
                    # Ищем по application_id
                    application = await get_application_by_id(db_session, application_id)
                    if not application:
                        print(f"❌ Заявка #{application_id} не найдена")
                        return
                    
                    # Ищем сессию по application_id
                    result = await db_session.execute(
                        select(ModerationSession).where(
                            ModerationSession.application_id == application_id
                        )
                    )
                    sessions = result.scalars().all()
                    
                    if not sessions:
                        print(f"❌ Сессия модерации для заявки #{application_id} не найдена")
                        return
                    
                    moderation_session = sessions[0]
                    
                elif session_id:
                    moderation_session = await get_moderation_session_by_id(db_session, session_id)
                    if not moderation_session:
                        print(f"❌ Сессия #{session_id} не найдена")
                        return
                    application_id = moderation_session.application_id
                else:
                    print("❌ Укажите application_id или session_id")
                    return
                
                await db_session.commit()
                
                user_id = moderation_session.user_id
                moderator_id = moderation_session.moderator_id
                
                print(f"\n📋 Информация о сессии:")
                print(f"   ID сессии: {moderation_session.id}")
                print(f"   Заявка: #{application_id}")
                print(f"   Пользователь: {user_id}")
                print(f"   Модератор: {moderator_id}")
                print(f"   Статус: {moderation_session.status}")
                
                if not moderation_session.moderator_photo_file_id:
                    print(f"\n❌ Фото модератора отсутствует в базе данных!")
                    print(f"   Модератор не отправлял фото для этой сессии.")
                    return
                
                file_id = moderation_session.moderator_photo_file_id
                print(f"\n📸 Фото модератора найдено в БД")
                print(f"   file_id: {file_id[:50]}...")
                
                # Пытаемся отправить фото
                print(f"\n🔄 Попытка отправить фото пользователю {user_id}...")
                
                try:
                    sent_message = await bot.send_photo(
                        chat_id=user_id,
                        photo=file_id,
                        caption=(
                            f"📸 Фото от модератора для подтверждения\n\n"
                            f"Заявка #{application_id}"
                        )
                    )
                    print(f"✅ Фото успешно отправлено пользователю!")
                    print(f"   Message ID: {sent_message.message_id}")
                    print(f"   Пользователь должен получить фото в чате с ботом.")
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Не удалось отправить фото: {error_msg}")
                    
                    if "chat not found" in error_msg.lower():
                        print(f"\n💡 Проблема: Пользователь не начал диалог с ботом")
                        print(f"   Решение: Пользователь должен написать боту /start")
                    elif "bot was blocked" in error_msg.lower():
                        print(f"\n💡 Проблема: Пользователь заблокировал бота")
                        print(f"   Решение: Пользователь должен разблокировать бота")
                    else:
                        print(f"\n💡 Неизвестная ошибка: {error_msg}")
                
            except Exception as e:
                await db_session.rollback()
                print(f"❌ Ошибка: {e}")
                import traceback
                traceback.print_exc()
    
    finally:
        await bot.session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python scripts/resend_moderator_photo.py --application <application_id>")
        print("  python scripts/resend_moderator_photo.py --session <session_id>")
        print("\nПримеры:")
        print("  python scripts/resend_moderator_photo.py --application 2")
        print("  python scripts/resend_moderator_photo.py --session 1")
        sys.exit(1)
    
    try:
        if sys.argv[1] == "--application" and len(sys.argv) == 3:
            application_id = int(sys.argv[2])
            asyncio.run(resend_moderator_photo(application_id=application_id))
        elif sys.argv[1] == "--session" and len(sys.argv) == 3:
            session_id = int(sys.argv[2])
            asyncio.run(resend_moderator_photo(session_id=session_id))
        else:
            print("❌ Неверные аргументы")
            print("Используйте --application <id> или --session <id>")
            sys.exit(1)
    except ValueError:
        print("❌ ID должен быть целым числом")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
