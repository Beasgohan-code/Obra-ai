"""Telegram Stars premium payments."""
from __future__ import annotations

import logging
from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice,
    PreCheckoutQuery, SuccessfulPayment,
)

from config.settings import settings
from services.db import db

logger = logging.getLogger("obra.payments")
router = Router(name="payments")


async def send_premium_invoice(bot: Bot, chat_id: int):
    price = int(getattr(settings, "PREMIUM_STARS_PRICE", 50) or 50)
    title = getattr(settings, "PREMIUM_TITLE", "Obra Premium")
    desc = getattr(settings, "PREMIUM_DESC", "30 days higher limits")
    await bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=desc,
        payload="obra_premium_30d",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label="Premium 30d", amount=price)],
        provider_token="",  # empty for Stars
    )


@router.callback_query(F.data == "premium:show")
async def cb_premium_show(cq: CallbackQuery, bot: Bot):
    await cq.answer()
    price = int(getattr(settings, "PREMIUM_STARS_PRICE", 50) or 50)
    days = int(getattr(settings, "PREMIUM_DAYS", 30) or 30)
    await cq.message.answer(
        f"⭐ <b>Obra Premium</b> — {days} days\n\n"
        f"• Higher daily & monthly limits\n"
        f"• Full coding power\n"
        f"• Priority agent mode\n\n"
        f"Price: <b>{price} Stars</b>",
        parse_mode="HTML",
    )
    try:
        await send_premium_invoice(bot, cq.message.chat.id)
    except Exception as e:
        await cq.message.answer(f"Invoice error: {e}")


@router.callback_query(F.data == "premium:usage")
async def cb_usage(cq: CallbackQuery):
    await cq.answer()
    uid = cq.from_user.id
    d_u, d_l = await db.usage_today(uid)
    m_u, m_l = await db.usage_month(uid)
    prem = await db.is_premium(uid)
    await cq.message.answer(
        f"<b>Usage</b>\n"
        f"Plan: {'⭐ Premium' if prem else 'Free'}\n"
        f"Today: <code>{d_u}/{d_l}</code>\n"
        f"Month: <code>{m_u}/{m_l}</code>\n\n"
        f"Say <i>upgrade</i> for Stars premium.",
        parse_mode="HTML",
    )


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(query.id, ok=True)


@router.message(F.successful_payment)
async def on_success(message: Message, bot: Bot):
    sp: SuccessfulPayment = message.successful_payment
    uid = message.from_user.id if message.from_user else 0

    # --- Validate everything about the payment; never trust client data ---
    if not sp or sp.invoice_payload != "obra_premium_30d":
        logger.warning("payment with unexpected payload=%r from %s", getattr(sp, "invoice_payload", None), uid)
        return
    if (sp.currency or "").upper() != "XTR":
        logger.warning("payment with bad currency=%r from %s", sp.currency, uid)
        return
    expected = int(getattr(settings, "PREMIUM_STARS_PRICE", 50) or 50)
    if int(sp.total_amount or 0) < expected:
        logger.warning("payment amount too low (%s < %s) from %s", sp.total_amount, expected, uid)
        return
    charge_id = getattr(sp, "telegram_payment_charge_id", "") or ""
    if not charge_id or await db.is_payment_processed(charge_id):
        logger.info("duplicate/already-processed charge %s from %s — skipping grant", charge_id, uid)
        return

    days = int(getattr(settings, "PREMIUM_DAYS", 30) or 30)
    recorded = await db.record_processed_payment(charge_id, uid, payload=sp.invoice_payload, amount=int(sp.total_amount or 0))
    if not recorded:
        return  # lost a race — already processed
    until = await db.grant_premium(uid, days=days, stars=int(sp.total_amount or 0))
    await message.answer(
        f"✅ <b>Premium activated</b> until <code>{until[:10]}</code>\n"
        f"Stars paid: {sp.total_amount}",
        parse_mode="HTML",
    )
    await db.log_event(uid, message.chat.id, "premium_purchase", {"stars": sp.total_amount, "charge_id": charge_id[:16]})
