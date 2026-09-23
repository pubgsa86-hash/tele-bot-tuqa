import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.constants import HELP_TEXT, MSG_ENDED, WELCOME_TEXT, main_menu_kb
from bot.services import nav
from bot.services.pending import drop_user
from bot.services.sessions import purge_sessions

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    nav.reset(message.from_user.id)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    nav.reset(message.from_user.id)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=main_menu_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    """/cancel explicitly ends the current session (media + conversions + history).

    A new file resets everything anyway, but this gives users a clear way out.
    """
    user_id = message.from_user.id
    drop_user(user_id)
    await purge_sessions(user_id)
    nav.drop(user_id)
    await message.answer(MSG_ENDED, reply_markup=main_menu_kb())


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    nav.reset(message.from_user.id)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.message(Command("convert"))
async def cmd_convert(message: Message):
    nav.reset(message.from_user.id)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())