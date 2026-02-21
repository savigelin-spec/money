"""
FSM состояния для бота
"""
from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    """Состояния пользователя"""
    waiting_for_payment_amount = State()  # Ожидание суммы пополнения


class ModeratorStates(StatesGroup):
    """Состояния модератора"""
    moderating_session = State()  # Активная сессия модерации


class AdminStates(StatesGroup):
    """Состояния админа (ввод user_id, выбор роли)"""
    waiting_user_id = State()
    waiting_role = State()
