"""Обработчик /update_cookies — обновление cookies аккаунта Reddit
Только для админов: отправляют файл cookies.txt → бот проверяет и сохраняет.

Без входа в аккаунт Reddit отвечает "blocked by network security" на любой IP,
поэтому боту нужны cookies отдельного (не личного) аккаунта.
"""
import logging
import os
import shutil
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.config import settings
from bot.emojis import E
from bot.services.reddit import COOKIES_DIR, COOKIES_PATH, reddit_cookies_status

logger = logging.getLogger(__name__)
router = Router()


class CookiesStates(StatesGroup):
    """FSM для загрузки cookies"""
    waiting_file = State()


@router.message(F.text == "/update_cookies")
async def cmd_update_cookies(message: Message, state: FSMContext) -> None:
    """Команда /update_cookies — начинаем процесс обновления"""
    if message.from_user.id not in settings.admin_id_list:
        await message.answer(f"{E['ban']} Только администратор может обновить cookies.")
        return

    await state.set_state(CookiesStates.waiting_file)
    await message.answer(
        f"{E['folder']} <b>Отправьте файл cookies.txt</b>\n\n"
        "Как получить:\n"
        "1. Заведите <b>отдельный</b> аккаунт Reddit для бота (не личный)\n"
        "2. Откройте браузер в <b>приватном</b> режиме\n"
        '3. Войдите в этот аккаунт на <a href="https://www.reddit.com">reddit.com</a>\n'
        '4. Расширением "Get cookies.txt LOCALLY" экспортируйте cookies с reddit.com\n'
        "5. Отправьте файл сюда\n"
        "6. Закройте приватное окно, <b>не нажимая «Выйти»</b> — выход убивает сессию\n\n"
        "Отмена: /cancel",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(CookiesStates.waiting_file, F.text.startswith("/cancel"))
async def cancel_cookies(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(f"{E['cross']} Обновление cookies отменено.")


@router.message(CookiesStates.waiting_file, F.document)
async def process_cookies_file(message: Message, state: FSMContext) -> None:
    """Получили файл — проверяем и сохраняем как cookies.txt"""
    doc = message.document
    if doc.file_size and doc.file_size > 1_000_000:  # 1 МБ макс
        await message.answer(f"{E['cross']} Файл слишком большой. cookies.txt обычно < 100 КБ")
        return

    tmp_path = os.path.join(COOKIES_DIR, "cookies.txt.new")
    try:
        os.makedirs(COOKIES_DIR, exist_ok=True)

        # с Local Bot API файл уже на диске → просто копируем
        file = await message.bot.get_file(doc.file_id)
        if os.path.isfile(file.file_path):
            shutil.copyfile(file.file_path, tmp_path)
        else:
            # обычный Bot API — скачиваем
            await message.bot.download_file(file.file_path, tmp_path)

        # проверяем ДО замены: битый файл не должен затереть рабочие cookies
        status = reddit_cookies_status(tmp_path)
        if not status.valid:
            os.remove(tmp_path)
            await message.answer(
                f"{E['warning']} В файле нет живой сессии Reddit (кука <code>reddit_session</code>).\n"
                "Войдите в аккаунт на reddit.com и экспортируйте cookies заново. "
                "Старые cookies оставлены без изменений.",
                parse_mode="HTML",
            )
            return

        # атомарная замена — yt-dlp и JSON-запросы не увидят полузаписанный файл
        os.replace(tmp_path, COOKIES_PATH)
        if status.expires_at:
            until = time.strftime("%d.%m.%Y", time.localtime(status.expires_at))
            expiry = f"Сессия действует до {until}."
        else:
            expiry = "Срок сессии в файле не указан."
        await message.answer(
            f"{E['check']} <b>Cookies Reddit обновлены!</b>\n\n{expiry}",
            parse_mode="HTML",
        )
        logger.info("Cookies Reddit обновлены пользователем %s", message.from_user.id)

    except Exception as e:
        logger.error("Ошибка сохранения cookies: %s", e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        await message.answer(f"{E['cross']} Ошибка при сохранении cookies. Попробуйте ещё раз.")
    finally:
        await state.clear()


@router.message(CookiesStates.waiting_file)
async def process_cookies_not_file(message: Message) -> None:
    """Юзер отправил не файл"""
    await message.answer(f"{E['folder']} Отправьте именно <b>файл</b> cookies.txt", parse_mode="HTML")
