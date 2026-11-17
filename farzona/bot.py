"""
Lug'at yodlash va test boti (aiogram 3.x)

Imkoniyatlar:
  📚 Lug'at   - kartochkalar: so'z -> tarjimasini ko'rish -> "Bildim / Bilmadim"
  📝 Test     - 10 ta savol, 4 ta variant, oxirida natija va xatolar tahlili
  🔁 Xatolarim - faqat "bilmadim" va xato qilingan so'zlar ustida mashq
  📊 Natijam  - eng yaxshi natija, testlar soni, qiyin so'zlar soni
  /add so'z - tarjima   (har qatorda bittadan, bir nechta qator mumkin)
"""
import asyncio
import json
import logging
import os
import random
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

TOKEN = os.getenv("BOT_TOKEN", "9021632997:AAGHb1DyEfw4aQO4RRh7Qt_V_LDn8ATqOzg")
BASE = Path(__file__).parent
WORDS_FILE = BASE / "words.json"
ADMIN_ID = int(os.getenv("ADMIN_ID", "5803974935"))
STATS_FILE = BASE / "stats.json"
TEST_SIZE = 10

router = Router()

# ---------------------------------------------------------------- ma'lumotlar
WORDS: list[dict] = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
STATS: dict = (
    json.loads(STATS_FILE.read_text(encoding="utf-8")) if STATS_FILE.exists() else {}
)
SESSIONS: dict[str, dict] = {}  # faol testlar (xotirada)


def save_stats() -> None:
    STATS_FILE.write_text(json.dumps(STATS, ensure_ascii=False), encoding="utf-8")


def save_words() -> None:
    WORDS_FILE.write_text(
        json.dumps(WORDS, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def user(uid: str) -> dict:
    return STATS.setdefault(uid, {"unknown": [], "best": 0, "tests": 0})


# ------------------------------------------------------------------ tugmalar
MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📚 Lug'at"), KeyboardButton(text="📝 Test")],
        [KeyboardButton(text="🔁 Xatolarim"), KeyboardButton(text="📊 Natijam")],
    ],
    resize_keyboard=True,
)


def kb_front(mode: str, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👀 Tarjimasini ko'rish", callback_data=f"fc:{mode}:show:{idx}"
                )
            ]
        ]
    )


def kb_back(mode: str, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Bildim", callback_data=f"fc:{mode}:known:{idx}"),
                InlineKeyboardButton(text="❌ Bilmadim", callback_data=f"fc:{mode}:unk:{idx}"),
            ]
        ]
    )


def kb_options(qi: int, opts: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=o, callback_data=f"t:{qi}:{n}")]
            for n, o in enumerate(opts)
        ]
    )


# ------------------------------------------------------------------ kartochka
def pick(uid: str, mode: str, exclude: int | None = None) -> int | None:
    if mode == "m":  # faqat xatolar
        bad = set(user(uid)["unknown"])
        pool = [i for i, w in enumerate(WORDS) if w["w"] in bad]
    else:
        pool = list(range(len(WORDS)))
    if exclude is not None and len(pool) > 1:
        pool = [i for i in pool if i != exclude]
    return random.choice(pool) if pool else None


def card_text(idx: int) -> str:
    return f"🔤 <b>{WORDS[idx]['w']}</b>\n\nTarjimasini eslab ko'ring, so'ng tugmani bosing."


async def start_cards(message: Message, mode: str) -> None:
    uid = str(message.from_user.id)
    idx = pick(uid, mode)
    if idx is None:
        await message.answer(
            "🎉 Xatolar ro'yxati bo'sh! Avval 📚 Lug'at yoki 📝 Test bilan mashq qiling."
        )
        return
    await message.answer(card_text(idx), reply_markup=kb_front(mode, idx))


@router.callback_query(F.data.startswith("fc:"))
async def on_card(cb: CallbackQuery) -> None:
    _, mode, action, idx_s = cb.data.split(":")
    idx = int(idx_s)
    uid = str(cb.from_user.id)
    w = WORDS[idx]

    if action == "show":
        await cb.message.edit_text(
            f"🔤 <b>{w['w']}</b>\n💬 <b>{w['t']}</b>\n\nBildingizmi?",
            reply_markup=kb_back(mode, idx),
        )
        await cb.answer()
        return

    u = user(uid)
    if action == "known":
        if w["w"] in u["unknown"]:
            u["unknown"].remove(w["w"])
    elif w["w"] not in u["unknown"]:
        u["unknown"].append(w["w"])
    save_stats()

    nxt = pick(uid, mode, exclude=idx)
    if nxt is None:
        await cb.message.edit_text("🎉 Barakalla! Xatolar ro'yxati tugadi.")
    else:
        await cb.message.edit_text(card_text(nxt), reply_markup=kb_front(mode, nxt))
    await cb.answer()


# ----------------------------------------------------------------------- test
def build_test() -> list[dict]:
    idxs = random.sample(range(len(WORDS)), min(TEST_SIZE, len(WORDS)))
    qs = []
    for i in idxs:
        correct = WORDS[i]["t"]
        others = list({w["t"] for j, w in enumerate(WORDS) if j != i and w["t"] != correct})
        opts = random.sample(others, 3) + [correct]
        random.shuffle(opts)
        qs.append({"i": i, "opts": opts, "ans": opts.index(correct)})
    return qs


def q_text(s: dict, prefix: str = "") -> str:
    q = s["qs"][s["n"]]
    return (
        f"{prefix}"
        f"<b>Savol {s['n'] + 1}/{len(s['qs'])}</b>\n\n"
        f"🔤 <b>{WORDS[q['i']]['w']}</b> — tarjimasi qaysi?"
    )


@router.message(F.text == "📝 Test")
async def start_test(message: Message) -> None:
    if len(WORDS) < 4:
        await message.answer("Testga kamida 4 ta so'z kerak.")
        return
    uid = str(message.from_user.id)
    SESSIONS[uid] = {"qs": build_test(), "n": 0, "score": 0, "wrong": []}
    s = SESSIONS[uid]
    q = s["qs"][0]
    await message.answer(q_text(s), reply_markup=kb_options(0, q["opts"]))


@router.callback_query(F.data.startswith("t:"))
async def on_answer(cb: CallbackQuery) -> None:
    _, qi_s, ch_s = cb.data.split(":")
    qi, ch = int(qi_s), int(ch_s)
    uid = str(cb.from_user.id)
    s = SESSIONS.get(uid)
    if not s or qi != s["n"]:
        await cb.answer("Bu savol allaqachon javoblangan.")
        return

    q = s["qs"][qi]
    w = WORDS[q["i"]]
    if ch == q["ans"]:
        s["score"] += 1
        feedback = "✅ To'g'ri!\n\n"
    else:
        s["wrong"].append(q["i"])
        feedback = f"❌ Noto'g'ri. To'g'ri javob: <b>{w['t']}</b>\n\n"

    s["n"] += 1
    if s["n"] < len(s["qs"]):
        nq = s["qs"][s["n"]]
        await cb.message.edit_text(
            q_text(s, feedback), reply_markup=kb_options(s["n"], nq["opts"])
        )
    else:
        await finish_test(cb, uid, s, feedback)
    await cb.answer()


async def finish_test(cb: CallbackQuery, uid: str, s: dict, feedback: str) -> None:
    total = len(s["qs"])
    score = s["score"]
    pct = round(score * 100 / total)
    u = user(uid)
    u["tests"] += 1
    u["best"] = max(u["best"], score)
    for i in s["wrong"]:
        if WORDS[i]["w"] not in u["unknown"]:
            u["unknown"].append(WORDS[i]["w"])
    save_stats()

    if pct == 100:
        praise = "🏆 Ajoyib! Mukammal natija!"
    elif pct >= 70:
        praise = "👏 Juda yaxshi, oz qoldi!"
    else:
        praise = "💪 Xatolar ustida ishlang, keyingi safar yaxshiroq bo'ladi!"

    text = f"{feedback}🏁 <b>Test tugadi</b>\nNatija: <b>{score}/{total}</b> ({pct}%)\n{praise}"
    if s["wrong"]:
        text += "\n\n<b>Xato qilingan so'zlar:</b>\n"
        text += "\n".join(f"• {WORDS[i]['w']} — {WORDS[i]['t']}" for i in s["wrong"])
        text += "\n\n🔁 Xatolarim bo'limida ularni takrorlang."
    await cb.message.edit_text(text)
    SESSIONS.pop(uid, None)


# ------------------------------------------------------------- boshqa buyruqlar
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Salom, {message.from_user.first_name}! 👋\n"
        f"Men lug'at yodlash va test botiman. Lug'atda hozir <b>{len(WORDS)}</b> ta so'z bor.\n\n"
        "📚 Lug'at — kartochkalar bilan o'rganish\n"
        "📝 Test — o'zingizni sinab ko'ring\n"
        "🔁 Xatolarim — qiyin so'zlarni takrorlash\n"
        "📊 Natijam — statistika",
        reply_markup=MENU,
    )


@router.message(F.text == "📚 Lug'at")
async def menu_cards(message: Message) -> None:
    await start_cards(message, "a")


@router.message(F.text == "🔁 Xatolarim")
async def menu_mistakes(message: Message) -> None:
    await start_cards(message, "m")


@router.message(F.text == "📊 Natijam")
async def menu_stats(message: Message) -> None:
    u = user(str(message.from_user.id))
    await message.answer(
        "📊 <b>Natijangiz</b>\n"
        f"Topshirilgan testlar: <b>{u['tests']}</b>\n"
        f"Eng yaxshi natija: <b>{u['best']}/{min(TEST_SIZE, len(WORDS))}</b>\n"
        f"Qiyin so'zlar: <b>{len(u['unknown'])}</b>"
    )


@router.message(Command("add"))
async def cmd_add(message: Message) -> None:
    body = message.text.partition(" ")[2].strip()
    added = 0
    for line in body.splitlines():
        if "-" not in line:
            continue
        w, _, t = line.partition("-")
        w, t = w.strip(), t.strip()
        if w and t and all(x["w"].lower() != w.lower() for x in WORDS):
            WORDS.append({"w": w, "t": t})
            added += 1
    if added:
        save_words()
        await message.answer(f"✅ {added} ta so'z qo'shildi. Jami: {len(WORDS)}")
    else:
        await message.answer(
            "Format:\n<code>/add apple - olma\nbook - kitob</code>\n(har qatorda bitta so'z)"
        )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
