"""
Обработчики для платежей через Telegram Stars
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery

from database.db import get_session
from database.queries import get_or_create_user
from utils.balance import deposit_stars
from utils.user_messages import update_user_main_message
from keyboards.user_keyboards import get_back_to_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Обработка запроса перед оплатой (проверка доступности товара)"""
    logger.info(
        f"Pre-checkout query от пользователя {pre_checkout_query.from_user.id}: "
        f"payload={pre_checkout_query.invoice_payload}, amount={pre_checkout_query.total_amount}"
    )
    
    # Для Stars всегда подтверждаем оплату
    # В будущем здесь можно добавить проверку наличия товара, лимитов и т.д.
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Обработка успешной оплаты через Telegram Stars"""
    payment = message.successful_payment
    
    logger.info(
        f"Успешная оплата от пользователя {message.from_user.id}: "
        f"amount={payment.total_amount} Stars, payload={payment.invoice_payload}"
    )
    
    # Извлекаем количество звёзд из payload
    # Формат payload: "deposit_{user_id}_{amount}_{timestamp}"
    try:
        payload_parts = payment.invoice_payload.split("_")
        if len(payload_parts) >= 3 and payload_parts[0] == "deposit":
            amount = int(payload_parts[2])
        else:
            # Если формат неожиданный, используем сумму из платежа
            # Для Stars сумма уже в Stars (не в центах)
            amount = payment.total_amount
            logger.warning(f"Неожиданный формат payload: {payment.invoice_payload}, используем amount={amount}")
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка парсинга payload: {e}, используем сумму из платежа")
        # Для Stars сумма уже в Stars (не в центах)
        amount = payment.total_amount
    
    async for session in get_session():
        try:
            # Пополняем баланс пользователя
            new_balance = await deposit_stars(
                session=session,
                user_id=message.from_user.id,
                amount=amount,
                transaction_id=payment.telegram_payment_charge_id,
            )
            
            await session.commit()
            
            success_text = (
                "✅ Оплата успешно обработана!\n\n"
                f"💰 Получено: {amount}⭐\n"
                f"🆔 ID транзакции: {payment.telegram_payment_charge_id}\n"
                f"📊 Ваш баланс: {new_balance}⭐"
            )
            
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=success_text,
                reply_markup=get_back_to_menu_keyboard()
            )
            
            # Пытаемся удалить сообщение с инвойсом (после оплаты оно стало сообщением о платеже)
            # Это опционально - если не удастся удалить (системное сообщение), просто игнорируем ошибку
            try:
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=message.message_id
                )
                logger.info(
                    f"Сообщение с инвойсом (message_id={message.message_id}) удалено после успешной оплаты"
                )
            except Exception as e:
                # Игнорируем ошибку - возможно, это системное сообщение, которое нельзя удалить
                logger.debug(
                    f"Не удалось удалить сообщение с инвойсом (message_id={message.message_id}): {e}. "
                    f"Это нормально, если сообщение стало системным после оплаты."
                )
            
            logger.info(
                f"Баланс пользователя {message.from_user.id} пополнен на {amount}⭐. "
                f"Новый баланс: {new_balance}⭐"
            )
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при обработке платежа: {e}", exc_info=True)
            error_text = (
                "❌ Произошла ошибка при обработке платежа. "
                "Пожалуйста, свяжитесь с администратором."
            )
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=error_text,
                reply_markup=get_back_to_menu_keyboard()
            )
