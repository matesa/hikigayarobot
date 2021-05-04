import html
import random
import re
import time
from functools import partial

import SaitamaRobot.modules.sql.welcome_sql as sql
from SaitamaRobot import (DEV_USERS, LOGGER, OWNER_ID, DRAGONS, DEMONS, TIGERS,
                          WOLVES, sw, dispatcher, JOIN_LOGGER)
from SaitamaRobot.modules.helper_funcs.chat_status import (
    is_user_ban_protected,
    user_admin,
)
from SaitamaRobot.modules.helper_funcs.misc import build_keyboard, revert_buttons
from SaitamaRobot.modules.helper_funcs.msg_types import get_welcome_type
from SaitamaRobot.modules.helper_funcs.string_handling import (
    escape_invalid_curly_brackets,
    markdown_parser,
)
from SaitamaRobot.modules.log_channel import loggable
from SaitamaRobot.modules.sql.global_bans_sql import is_user_gbanned
from telegram import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
    run_async,
)
from telegram.utils.helpers import escape_markdown, mention_html, mention_markdown

VALID_WELCOME_FORMATTERS = [
    "first",
    "last",
    "fullname",
    "username",
    "id",
    "count",
    "chatname",
    "mention",
]

ENUM_FUNC_MAP = {
    sql.Types.TEXT.value: dispatcher.bot.send_message,
    sql.Types.BUTTON_TEXT.value: dispatcher.bot.send_message,
    sql.Types.STICKER.value: dispatcher.bot.send_sticker,
    sql.Types.DOCUMENT.value: dispatcher.bot.send_document,
    sql.Types.PHOTO.value: dispatcher.bot.send_photo,
    sql.Types.AUDIO.value: dispatcher.bot.send_audio,
    sql.Types.VOICE.value: dispatcher.bot.send_voice,
    sql.Types.VIDEO.value: dispatcher.bot.send_video,
}

VERIFIED_USER_WAITLIST = {}


# do not async
def send(update, message, keyboard, backup_message):
    chat = update.effective_chat
    cleanserv = sql.clean_service(chat.id)
    reply = update.message.message_id
    # Clean service welcome
    if cleanserv:
        try:
            dispatcher.bot.delete_message(chat.id, update.message.message_id)
        except BadRequest:
            pass
        reply = False
    try:
        msg = update.effective_message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
            reply_to_message_id=reply,
        )
    except BadRequest as excp:
        if excp.message == "Cevap mesajı bulunamadı":
            msg = update.effective_message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
                quote=False)
        elif excp.message == "Button_url_invalid":
            msg = update.effective_message.reply_text(
                markdown_parser(
                    backup_message +
                    "\nNote: mevcut iletinin geçersiz bir url'si var "
                    "düğmelerinden birinde. Lütfen güncelleyin."),
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=reply,
            )
        elif excp.message == "Desteklenmeyen url protokolü":
            msg = update.effective_message.reply_text(
                markdown_parser(backup_message +
                                "\nNote: mevcut mesajda "
                                "tarafından desteklenmeyen url protokollerini kullan "
                                "telegram ı Lütfen güncelleyin.."),
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=reply,
            )
        elif excp.message == "Yanlış url barındırıcısı":
            msg = update.effective_message.reply_text(
                markdown_parser(
                    backup_message +
                    "\nNote: Geçerli iletide bazı hatalı URL'ler var. "
                    "Lütfen güncelle."),
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=reply,
            )
            LOGGER.warning(message)
            LOGGER.warning(keyboard)
            LOGGER.exception("Ayrıştırılamadı! geçersiz url ana bilgisayar hataları aldı")
        elif excp.message == "Mesaj gönderme hakkınız yok":
            return
        else:
            msg = update.effective_message.reply_text(
                markdown_parser(backup_message +
                                "\nNote: Gönderirken bir hata oluştu "
                                "özel mesaj. Lütfen güncelleyin."),
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=reply,
            )
            LOGGER.exception()
    return msg


@run_async
@loggable
def new_member(update: Update, context: CallbackContext):
    bot, job_queue = context.bot, context.job_queue
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message

    should_welc, cust_welcome, cust_content, welc_type = sql.get_welc_pref(
        chat.id)
    welc_mutes = sql.welcome_mutes(chat.id)
    human_checks = sql.get_human_checks(user.id, chat.id)

    new_members = update.effective_message.new_chat_members

    for new_mem in new_members:

        welcome_log = None
        res = None
        sent = None
        should_mute = True
        welcome_bool = True
        media_wel = False

        if sw is not None:
            sw_ban = sw.get_ban(new_mem.id)
            if sw_ban:
                return

        if should_welc:

            reply = update.message.message_id
            cleanserv = sql.clean_service(chat.id)
            # Clean service welcome
            if cleanserv:
                try:
                    dispatcher.bot.delete_message(chat.id,
                                                  update.message.message_id)
                except BadRequest:
                    pass
                reply = False

            # Give the owner a special welcome
            if new_mem.id == OWNER_ID:
                update.effective_message.reply_text(
                    "Oh, Genos? Hadi bunu harekete geçirelim.",
                    reply_to_message_id=reply)
                welcome_log = (f"{html.escape(chat.title)}\n"
                               f"#USER_BİRLEŞTİRİLDİ\n"
                               f"Bot Sahibi sohbete yeni katıldı")
                continue

            # Welcome Devs
            elif new_mem.id in DEV_USERS:
                update.effective_message.reply_text(
                    "Vay be! Kahramanlar Derneği'nin bir üyesi az önce katıldı!",
                    reply_to_message_id=reply,
                )
                continue

            # Welcome Sudos
            elif new_mem.id in DRAGONS:
                update.effective_message.reply_text(
                    "Huh! Bir Dragon felaketi az önce katıldı! Dikkatli Kalın!",
                    reply_to_message_id=reply,
                )
                continue

            # Welcome Support
            elif new_mem.id in DEMONS:
                update.effective_message.reply_text(
                    "Huh! Demon felaket seviyesine sahip biri az önce katıldı!",
                    reply_to_message_id=reply,
                )
                continue

            # Welcome Whitelisted
            elif new_mem.id in TIGERS:
                update.effective_message.reply_text(
                    "Oof! Bir Kaplan felaketi yeni katıldı!",
                    reply_to_message_id=reply)
                continue

            # Welcome Tigers
            elif new_mem.id in WOLVES:
                update.effective_message.reply_text(
                    "Oof! Bir Kurt felaketi yeni katıldı!",
                    reply_to_message_id=reply)
                continue

            # Welcome yourself
            elif new_mem.id == bot.id:
                creator = None
                for x in bot.bot.get_chat_administrators(
                        update.effective_chat.id):
                    if x.status == 'creator':
                        creator = x.user
                        break
                if creator:
                    bot.send_message(
                        JOIN_LOGGER,
                        "#NEW_GROUP\n<b>Group name:</b> {}\n<b>ID:</b> <code>{}</code>\n<b>Creator:</b> <code>{}</code>"
                        .format(
                            html.escape(chat.title), chat.id,
                            html.escape(creator)),
                        parse_mode=ParseMode.HTML)
                else:
                    bot.send_message(
                        JOIN_LOGGER,
                        "#NEW_GROUP\n<b>Group name:</b> {}\n<b>ID:</b> <code>{}</code>"
                        .format(html.escape(chat.title), chat.id),
                        parse_mode=ParseMode.HTML)
                update.effective_message.reply_text(
                    "Watashi ga kita!", reply_to_message_id=reply)
                continue

            else:
                buttons = sql.get_welc_buttons(chat.id)
                keyb = build_keyboard(buttons)

                if welc_type not in (sql.Types.TEXT, sql.Types.BUTTON_TEXT):
                    media_wel = True

                first_name = (
                    new_mem.first_name or "PersonWithNoName"
                )  # edge case of empty name - occurs for some bugs.

                if cust_welcome:
                    if cust_welcome == sql.DEFAULT_WELCOME:
                        cust_welcome = random.choice(
                            sql.DEFAULT_WELCOME_MESSAGES).format(
                                first=escape_markdown(first_name))

                    if new_mem.last_name:
                        fullname = escape_markdown(
                            f"{first_name} {new_mem.last_name}")
                    else:
                        fullname = escape_markdown(first_name)
                    count = chat.get_members_count()
                    mention = mention_markdown(new_mem.id,
                                               escape_markdown(first_name))
                    if new_mem.username:
                        username = "@" + escape_markdown(new_mem.username)
                    else:
                        username = mention

                    valid_format = escape_invalid_curly_brackets(
                        cust_welcome, VALID_WELCOME_FORMATTERS)
                    res = valid_format.format(
                        first=escape_markdown(first_name),
                        last=escape_markdown(new_mem.last_name or first_name),
                        fullname=escape_markdown(fullname),
                        username=username,
                        mention=mention,
                        count=count,
                        chatname=escape_markdown(chat.title),
                        id=new_mem.id,
                    )

                else:
                    res = random.choice(sql.DEFAULT_WELCOME_MESSAGES).format(
                        first=escape_markdown(first_name))
                    keyb = []

                backup_message = random.choice(
                    sql.DEFAULT_WELCOME_MESSAGES).format(
                        first=escape_markdown(first_name))
                keyboard = InlineKeyboardMarkup(keyb)

        else:
            welcome_bool = False
            res = None
            keyboard = None
            backup_message = None
            reply = None

        # User exceptions from welcomemutes
        if (is_user_ban_protected(chat, new_mem.id, chat.get_member(new_mem.id))
                or human_checks):
            should_mute = False
        # Join welcome: soft mute
        if new_mem.is_bot:
            should_mute = False

        if user.id == new_mem.id:
            if should_mute:
                if welc_mutes == "soft":
                    bot.restrict_chat_member(
                        chat.id,
                        new_mem.id,
                        permissions=ChatPermissions(
                            can_send_messages=True,
                            can_send_media_messages=False,
                            can_send_other_messages=False,
                            can_invite_users=False,
                            can_pin_messages=False,
                            can_send_polls=False,
                            can_change_info=False,
                            can_add_web_page_previews=False,
                        ),
                        until_date=(int(time.time() + 24 * 60 * 60)),
                    )
                if welc_mutes == "strong":
                    welcome_bool = False
                    if not media_wel:
                        VERIFIED_USER_WAITLIST.update({
                            new_mem.id: {
                                "should_welc": should_welc,
                                "media_wel": False,
                                "status": False,
                                "update": update,
                                "res": res,
                                "keyboard": keyboard,
                                "backup_message": backup_message,
                            }
                        })
                    else:
                        VERIFIED_USER_WAITLIST.update({
                            new_mem.id: {
                                "should_welc": should_welc,
                                "chat_id": chat.id,
                                "status": False,
                                "media_wel": True,
                                "cust_content": cust_content,
                                "welc_type": welc_type,
                                "res": res,
                                "keyboard": keyboard,
                            }
                        })
                    new_join_mem = f'<a href="tg://user?id={user.id}">{html.escape(new_mem.first_name)}</a>'
                    message = msg.reply_text(
                        f"{new_join_mem}, insan olduğunuzu kanıtlamak için aşağıdaki düğmeyi tıklayın.\n120 saniyeniz var.",
                        reply_markup=InlineKeyboardMarkup([{
                            InlineKeyboardButton(
                                text="Evet, ben insanım.",
                                callback_data=f"user_join_({new_mem.id})",
                            )
                        }]),
                        parse_mode=ParseMode.HTML,
                        reply_to_message_id=reply,
                    )
                    bot.restrict_chat_member(
                        chat.id,
                        new_mem.id,
                        permissions=ChatPermissions(
                            can_send_messages=False,
                            can_invite_users=False,
                            can_pin_messages=False,
                            can_send_polls=False,
                            can_change_info=False,
                            can_send_media_messages=False,
                            can_send_other_messages=False,
                            can_add_web_page_previews=False,
                        ),
                    )
                    job_queue.run_once(
                        partial(check_not_bot, new_mem, chat.id,
                                message.message_id),
                        120,
                        name="welcomemute",
                    )

        if welcome_bool:
            if media_wel:
                sent = ENUM_FUNC_MAP[welc_type](
                    chat.id,
                    cust_content,
                    caption=res,
                    reply_markup=keyboard,
                    reply_to_message_id=reply,
                    parse_mode="markdown",
                )
            else:
                sent = send(update, res, keyboard, backup_message)
            prev_welc = sql.get_clean_pref(chat.id)
            if prev_welc:
                try:
                    bot.delete_message(chat.id, prev_welc)
                except BadRequest:
                    pass

                if sent:
                    sql.set_clean_welcome(chat.id, sent.message_id)

        if welcome_log:
            return welcome_log

        return (f"{html.escape(chat.title)}\n"
                f"#USER_JOINED\n"
                f"<b>User</b>: {mention_html(user.id, user.first_name)}\n"
                f"<b>ID</b>: <code>{user.id}</code>")

    return ""


def check_not_bot(member, chat_id, message_id, context):
    bot = context.bot
    member_dict = VERIFIED_USER_WAITLIST.pop(member.id)
    member_status = member_dict.get("status")
    if not member_status:
        try:
            bot.unban_chat_member(chat_id, member.id)
        except:
            pass

        try:
            bot.edit_message_text(
                "*kullanıcıyı atar*\nHer zaman yeniden katılabilir ve deneyebilirler.",
                chat_id=chat_id,
                message_id=message_id,
            )
        except:
            pass


@run_async
def left_member(update: Update, context: CallbackContext):
    bot = context.bot
    chat = update.effective_chat
    user = update.effective_user
    should_goodbye, cust_goodbye, goodbye_type = sql.get_gdbye_pref(chat.id)

    if user.id == bot.id:
        return

    if should_goodbye:
        reply = update.message.message_id
        cleanserv = sql.clean_service(chat.id)
        # Clean service welcome
        if cleanserv:
            try:
                dispatcher.bot.delete_message(chat.id,
                                              update.message.message_id)
            except BadRequest:
                pass
            reply = False

        left_mem = update.effective_message.left_chat_member
        if left_mem:

            # Thingy for spamwatched users
            if sw is not None:
                sw_ban = sw.get_ban(left_mem.id)
                if sw_ban:
                    return

            # Dont say goodbyes to gbanned users
            if is_user_gbanned(left_mem.id):
                return

            # Ignore bot being kicked
            if left_mem.id == bot.id:
                return

            # Give the owner a special goodbye
            if left_mem.id == OWNER_ID:
                update.effective_message.reply_text(
                    "Oi! Genos! Gitti ..", reply_to_message_id=reply)
                return

            # Give the devs a special goodbye
            elif left_mem.id in DEV_USERS:
                update.effective_message.reply_text(
                    "Daha sonra Kahramanlar Derneği'nde görüşürüz!",
                    reply_to_message_id=reply,
                )
                return

            # if media goodbye, use appropriate function for it
            if goodbye_type != sql.Types.TEXT and goodbye_type != sql.Types.BUTTON_TEXT:
                ENUM_FUNC_MAP[goodbye_type](chat.id, cust_goodbye)
                return

            first_name = (left_mem.first_name or "PersonWithNoName"
                         )  # edge case of empty name - occurs for some bugs.
            if cust_goodbye:
                if cust_goodbye == sql.DEFAULT_GOODBYE:
                    cust_goodbye = random.choice(
                        sql.DEFAULT_GOODBYE_MESSAGES).format(
                            first=escape_markdown(first_name))
                if left_mem.last_name:
                    fullname = escape_markdown(
                        f"{first_name} {left_mem.last_name}")
                else:
                    fullname = escape_markdown(first_name)
                count = chat.get_members_count()
                mention = mention_markdown(left_mem.id, first_name)
                if left_mem.username:
                    username = "@" + escape_markdown(left_mem.username)
                else:
                    username = mention

                valid_format = escape_invalid_curly_brackets(
                    cust_goodbye, VALID_WELCOME_FORMATTERS)
                res = valid_format.format(
                    first=escape_markdown(first_name),
                    last=escape_markdown(left_mem.last_name or first_name),
                    fullname=escape_markdown(fullname),
                    username=username,
                    mention=mention,
                    count=count,
                    chatname=escape_markdown(chat.title),
                    id=left_mem.id,
                )
                buttons = sql.get_gdbye_buttons(chat.id)
                keyb = build_keyboard(buttons)

            else:
                res = random.choice(
                    sql.DEFAULT_GOODBYE_MESSAGES).format(first=first_name)
                keyb = []

            keyboard = InlineKeyboardMarkup(keyb)

            send(
                update,
                res,
                keyboard,
                random.choice(
                    sql.DEFAULT_GOODBYE_MESSAGES).format(first=first_name),
            )


@run_async
@user_admin
def welcome(update: Update, context: CallbackContext):
    args = context.args
    chat = update.effective_chat
    # if no args, show current replies.
    if not args or args[0].lower() == "noformat":
        noformat = True
        pref, welcome_m, cust_content, welcome_type = sql.get_welc_pref(chat.id)
        update.effective_message.reply_text(
            f"Bu sohbetin hoş geldiniz ayarı şu şekilde ayarlanmıştır: `{pref}`.\n"
            f"*Hoş geldiniz mesajı ({{}} doldurulmadan) :*",
            parse_mode=ParseMode.MARKDOWN,
        )

        if welcome_type == sql.Types.BUTTON_TEXT or welcome_type == sql.Types.TEXT:
            buttons = sql.get_welc_buttons(chat.id)
            if noformat:
                welcome_m += revert_buttons(buttons)
                update.effective_message.reply_text(welcome_m)

            else:
                keyb = build_keyboard(buttons)
                keyboard = InlineKeyboardMarkup(keyb)

                send(update, welcome_m, keyboard, sql.DEFAULT_WELCOME)
        else:
            buttons = sql.get_welc_buttons(chat.id)
            if noformat:
                welcome_m += revert_buttons(buttons)
                ENUM_FUNC_MAP[welcome_type](
                    chat.id, cust_content, caption=welcome_m)

            else:
                keyb = build_keyboard(buttons)
                keyboard = InlineKeyboardMarkup(keyb)
                ENUM_FUNC_MAP[welcome_type](
                    chat.id,
                    cust_content,
                    caption=welcome_m,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )

    elif len(args) >= 1:
        if args[0].lower() in ("on", "yes"):
            sql.set_welc_preference(str(chat.id), True)
            update.effective_message.reply_text(
                "Tamam! Katıldıklarında üyeleri selamlayacağım.")

        elif args[0].lower() in ("off", "no"):
            sql.set_welc_preference(str(chat.id), False)
            update.effective_message.reply_text(
                "Etrafta dolanacağım ve o zaman kimseyi hoş karşılamayacağım.")

        else:
            update.effective_message.reply_text(
                "Sadece 'on/yes' or 'off/no' Anlıyorum!")


@run_async
@user_admin
def goodbye(update: Update, context: CallbackContext):
    args = context.args
    chat = update.effective_chat

    if not args or args[0] == "noformat":
        noformat = True
        pref, goodbye_m, goodbye_type = sql.get_gdbye_pref(chat.id)
        update.effective_message.reply_text(
            f"Bu sohbetin veda ayarı şu şekilde ayarlanmıştır: `{pref}`.\n"
            f"*Hoşçakal mesajı ({{}} doldurulmadan) :*",
            parse_mode=ParseMode.MARKDOWN,
        )

        if goodbye_type == sql.Types.BUTTON_TEXT:
            buttons = sql.get_gdbye_buttons(chat.id)
            if noformat:
                goodbye_m += revert_buttons(buttons)
                update.effective_message.reply_text(goodbye_m)

            else:
                keyb = build_keyboard(buttons)
                keyboard = InlineKeyboardMarkup(keyb)

                send(update, goodbye_m, keyboard, sql.DEFAULT_GOODBYE)

        else:
            if noformat:
                ENUM_FUNC_MAP[goodbye_type](chat.id, goodbye_m)

            else:
                ENUM_FUNC_MAP[goodbye_type](
                    chat.id, goodbye_m, parse_mode=ParseMode.MARKDOWN)

    elif len(args) >= 1:
        if args[0].lower() in ("on", "yes"):
            sql.set_gdbye_preference(str(chat.id), True)
            update.effective_message.reply_text("Ok!")

        elif args[0].lower() in ("off", "no"):
            sql.set_gdbye_preference(str(chat.id), False)
            update.effective_message.reply_text("Ok!")

        else:
            # idek what you're writing, say yes or no
            update.effective_message.reply_text(
                "Sadece 'on/yes' or 'off/no' Anlıyorum!")


@run_async
@user_admin
@loggable
def set_welcome(update: Update, context: CallbackContext) -> str:
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message

    text, data_type, content, buttons = get_welcome_type(msg)

    if data_type is None:
        msg.reply_text("Ne ile yanıt vereceğinizi belirtmediniz!")
        return ""

    sql.set_custom_welcome(chat.id, content, text, data_type, buttons)
    msg.reply_text("Özel karşılama mesajı başarıyla ayarlandı!")

    return (f"<b>{html.escape(chat.title)}:</b>\n"
            f"#SET_WELCOME\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
            f"Karşılama mesajını ayarlayın.")


@run_async
@user_admin
@loggable
def reset_welcome(update: Update, context: CallbackContext) -> str:
    chat = update.effective_chat
    user = update.effective_user

    sql.set_custom_welcome(chat.id, None, sql.DEFAULT_WELCOME, sql.Types.TEXT)
    update.effective_message.reply_text(
        "Hoş geldiniz mesajını başarıyla varsayılana sıfırlayın!")

    return (f"<b>{html.escape(chat.title)}:</b>\n"
            f"#RESET_WELCOME\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
            f"Hoş geldiniz mesajını varsayılana sıfırlayın.")


@run_async
@user_admin
@loggable
def set_goodbye(update: Update, context: CallbackContext) -> str:
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    text, data_type, content, buttons = get_welcome_type(msg)

    if data_type is None:
        msg.reply_text("Ne ile yanıt vereceğinizi belirtmediniz!")
        return ""

    sql.set_custom_gdbye(chat.id, content or text, data_type, buttons)
    msg.reply_text("Özel hoşçakal mesajı başarıyla ayarlandı!")
    return (f"<b>{html.escape(chat.title)}:</b>\n"
            f"#SET_GOODBYE\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
            f"Hoşçakal mesajını ayarlayın.")


@run_async
@user_admin
@loggable
def reset_goodbye(update: Update, context: CallbackContext) -> str:
    chat = update.effective_chat
    user = update.effective_user

    sql.set_custom_gdbye(chat.id, sql.DEFAULT_GOODBYE, sql.Types.TEXT)
    update.effective_message.reply_text(
        "Hoşçakal mesajını başarıyla varsayılana sıfırlayın!")

    return (f"<b>{html.escape(chat.title)}:</b>\n"
            f"#RESET_GOODBYE\n"
            f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
            f"Hoşçakal mesajını sıfırlayın.")


@run_async
@user_admin
@loggable
def welcomemute(update: Update, context: CallbackContext) -> str:
    args = context.args
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message

    if len(args) >= 1:
        if args[0].lower() in ("off", "no"):
            sql.set_welcome_mutes(chat.id, False)
            msg.reply_text("Artık katılımda kişilerin sesini kapatmayacağım!")
            return (
                f"<b>{html.escape(chat.title)}:</b>\n"
                f"#WELCOME_MUTE\n"
                f"<b>• Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"Hoş geldiniz sesini <b>OFF</b> olarak değiştirdi.")
        elif args[0].lower() in ["soft"]:
            sql.set_welcome_mutes(chat.id, "soft")
            msg.reply_text(
                "Kullanıcıların 24 saat boyunca medya gönderme iznini kısıtlayacağım.")
            return (
                f"<b>{html.escape(chat.title)}:</b>\n"
                f"#WELCOME_MUTE\n"
                f"<b>• Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"Hoş geldiniz sesini <b>SOFT</b> olarak değiştirdi.")
        elif args[0].lower() in ["strong"]:
            sql.set_welcome_mutes(chat.id, "strong")
            msg.reply_text(
                "Artık bot olmadıklarını kanıtlayana kadar katılanların sesini kapatacağım.\nAtılmadan önce 120 saniye sürecek."
            )
            return (
                f"<b>{html.escape(chat.title)}:</b>\n"
                f"#WELCOME_MUTE\n"
                f"<b>• Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"Hoş geldiniz sesini <b>STRONG</b> olarak değiştirdi.")
        else:
            msg.reply_text(
                "Lütfen <code>off</code>/<code>no</code>/<code>soft</code>/<code>strong</code>!",
                parse_mode=ParseMode.HTML,
            )
            return ""
    else:
        curr_setting = sql.welcome_mutes(chat.id)
        reply = (
            f"\n Bana bir ayar verin!\nAşağıdakilerden birini seçin: <code>off</code>/<code>no</code> or <code>soft</code> or <code>strong</code> Sadece! \n"
            f"Current setting: <code>{curr_setting}</code>")
        msg.reply_text(reply, parse_mode=ParseMode.HTML)
        return ""


@run_async
@user_admin
@loggable
def clean_welcome(update: Update, context: CallbackContext) -> str:
    args = context.args
    chat = update.effective_chat
    user = update.effective_user

    if not args:
        clean_pref = sql.get_clean_pref(chat.id)
        if clean_pref:
            update.effective_message.reply_text(
                "İki günlük hoş geldiniz mesajlarını silmeliyim.")
        else:
            update.effective_message.reply_text(
                "Şu anda eski karşılama mesajlarını silmiyorum!")
        return ""

    if args[0].lower() in ("on", "yes"):
        sql.set_clean_welcome(str(chat.id), True)
        update.effective_message.reply_text(
            "Eski hoş geldiniz mesajlarını silmeye çalışacağım!")
        return (f"<b>{html.escape(chat.title)}:</b>\n"
                f"#CLEAN_WELCOME\n"
                f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"Temiz karşılamalar <code>ON</code> olarak değiştirildi.")
    elif args[0].lower() in ("off", "no"):
        sql.set_clean_welcome(str(chat.id), False)
        update.effective_message.reply_text(
            "Eski karşılama mesajlarını silmeyeceğim.")
        return (f"<b>{html.escape(chat.title)}:</b>\n"
                f"#CLEAN_WELCOME\n"
                f"<b>Admin:</b> {mention_html(user.id, user.first_name)}\n"
                f"Temiz karşılamalar <code>OFF</code> olarak değiştirildi.")
    else:
        update.effective_message.reply_text(
            "Sadece 'on/yes' or 'off/no' Anlıyorum!")
        return ""


@run_async
@user_admin
def cleanservice(update: Update, context: CallbackContext) -> str:
    args = context.args
    chat = update.effective_chat  # type: Optional[Chat]
    if chat.type != chat.PRIVATE:
        if len(args) >= 1:
            var = args[0]
            if var in ("no", "off"):
                sql.set_clean_service(chat.id, False)
                update.effective_message.reply_text(
                    "Karşılama temizliği hizmeti : off")
            elif var in ("yes", "on"):
                sql.set_clean_service(chat.id, True)
                update.effective_message.reply_text(
                    "Karşılama temizliği hizmeti : on")
            else:
                update.effective_message.reply_text(
                    "Geçersiz seçenek", parse_mode=ParseMode.HTML)
        else:
            update.effective_message.reply_text(
                "Kullanım <code>on</code>/<code>yes</code> or <code>off</code>/<code>no</code>",
                parse_mode=ParseMode.HTML)
    else:
        curr = sql.clean_service(chat.id)
        if curr:
            update.effective_message.reply_text(
                "Hoş geldiniz temiz hizmeti : <code>on</code>",
                parse_mode=ParseMode.HTML)
        else:
            update.effective_message.reply_text(
                "Hoş geldiniz temiz hizmeti : <code>off</code>",
                parse_mode=ParseMode.HTML)


@run_async
def user_button(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    query = update.callback_query
    bot = context.bot
    match = re.match(r"user_join_\((.+?)\)", query.data)
    message = update.effective_message
    join_user = int(match.group(1))

    if join_user == user.id:
        sql.set_human_checks(user.id, chat.id)
        member_dict = VERIFIED_USER_WAITLIST.pop(user.id)
        member_dict["status"] = True
        VERIFIED_USER_WAITLIST.update({user.id: member_dict})
        query.answer(text="Evet! Sen bir insansın, yok sayılmamış!")
        bot.restrict_chat_member(
            chat.id,
            user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_invite_users=True,
                can_pin_messages=True,
                can_send_polls=True,
                can_change_info=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        try:
            bot.deleteMessage(chat.id, message.message_id)
        except:
            pass
        if member_dict["should_welc"]:
            if member_dict["media_wel"]:
                sent = ENUM_FUNC_MAP[member_dict["welc_type"]](
                    member_dict["chat_id"],
                    member_dict["cust_content"],
                    caption=member_dict["res"],
                    reply_markup=member_dict["keyboard"],
                    parse_mode="markdown",
                )
            else:
                sent = send(
                    member_dict["update"],
                    member_dict["res"],
                    member_dict["keyboard"],
                    member_dict["backup_message"],
                )

            prev_welc = sql.get_clean_pref(chat.id)
            if prev_welc:
                try:
                    bot.delete_message(chat.id, prev_welc)
                except BadRequest:
                    pass

                if sent:
                    sql.set_clean_welcome(chat.id, sent.message_id)

    else:
        query.answer(text="You're not allowed to do this!")


WELC_HELP_TXT = (
    "Grubunuzun welcome/goodbye mesajları birçok şekilde kişiselleştirilebilir. Mesajları istiyorsanız"
    " tek tek oluşturulmak üzere, varsayılan karşılama mesajı gibi *these* değişkenleri kullanabilirsiniz:\n"
    " • `{first}`*:* bu, kullanıcının  *adını* temsil eder\n"
    " • `{last}`*:* bu, kullanıcının *soyadını* temsil eder.Kullanıcının adı yoksa *ad* varsayılanıdır "
    "last name.\n"
    " • `{fullname}`*:* bu, kullanıcının *tam* adını temsil eder. Kullanıcının *tam* adını temsil eder. Kullanıcının adı yoksa ilk adı olarak belirlenir "
    "last name.\n"
    " • `{username}`*:* bu, kullanıcının *kullanıcı adını*. temsil eder. Varsayılan olarak, kullanıcının *sözünden* bahsedilir "
    "first adı yoksa username.\n"
    " • `{mention}`*:* bu sadece bir kullanıcıdan *bahseder* - onu adlarıyla etiketler first name.\n"
    " • `{id}`*:* bu, kullanıcının *id* temsil eder\n"
    " • `{count}`*:* bu, kullanıcının *üye numarasını* temsil eder.\n"
    " • `{chatname}`*:* bu *mevcut sohbet adını* temsil eder.\n"
    "\nHer değişken, değiştirilmek için `{}` ile çevrelenmelidir ZORUNLU.\n"
    "Karşılama mesajları aynı zamanda işaretlemeyi de destekler, böylece herhangi bir öğeyi bold/italic/code/links yapabilirsiniz. "
    "Karşılama mesajları aynı zamanda işaretlemeyi de destekler, böylece herhangi bir öğeyi "
    "buttons.\n"
    f"Kurallarınıza bağlanan bir düğme oluşturmak için şunu kullanın: `[Rules](buttonurl://t.me/{dispatcher.bot.username}?start=group_id)`. "
    "Basitçe` group_id` yerine /id, aracılığıyla elde edilebilen grubunuzun kimliğini değiştirin ve bunu yapmakta fayda var "
    "git. Grup kimliklerinden önce genellikle `-` işareti bulunduğunu unutmayın; bu gereklidir, bu nedenle lütfen yapmayın "
    "remove it.\n"
    "images/gifs/videos/voice mesajları karşılama mesajı olarak bile ayarlayabilirsiniz "
    "istenen medyayı yanıtla `/setwelcome` komutunu kullan.")

WELC_MUTE_HELP_TXT = (
    "Botun, grubunuza katılan yeni kişilerin sesini kapatmasını sağlayabilir ve böylece spam'lerin grubunuzu doldurmasını önleyebilirsiniz. "
    "Aşağıdaki seçenekler mümkündür:\n"
    "• `/welcomemute soft`*:* yeni üyelerin 24 saat boyunca medya göndermesini kısıtlar.\n"
    "• `/welcomemute strong`*:* bir düğmeye dokunana kadar yeni üyelerin sesini kapatır ve böylece insan olduklarını doğrular.\n"
    "• `/welcomemute off`*:* karşılama mesajını kapatır.\n"
    "*Not:* Güçlü mod, kullanıcıyı 120 saniye içinde doğrulama yapmazsa sohbetten çıkarır. Yine de her zaman yeniden katılabilirler."
)


@run_async
@user_admin
def welcome_help(update: Update, context: CallbackContext):
    update.effective_message.reply_text(
        WELC_HELP_TXT, parse_mode=ParseMode.MARKDOWN)


@run_async
@user_admin
def welcome_mute_help(update: Update, context: CallbackContext):
    update.effective_message.reply_text(
        WELC_MUTE_HELP_TXT, parse_mode=ParseMode.MARKDOWN)


# TODO: get welcome data from group butler snap
# def __import_data__(chat_id, data):
#     welcome = data.get('info', {}).get('rules')
#     welcome = welcome.replace('$username', '{username}')
#     welcome = welcome.replace('$name', '{fullname}')
#     welcome = welcome.replace('$id', '{id}')
#     welcome = welcome.replace('$title', '{chatname}')
#     welcome = welcome.replace('$surname', '{lastname}')
#     welcome = welcome.replace('$rules', '{rules}')
#     sql.set_custom_welcome(chat_id, welcome, sql.Types.TEXT)


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    welcome_pref = sql.get_welc_pref(chat_id)[0]
    goodbye_pref = sql.get_gdbye_pref(chat_id)[0]
    return ("Bu sohbetin hoş geldiniz tercihi `{}` olarak ayarlanmış.\n"
            "Hoşçakal tercihi `{}`.".format(welcome_pref,
                                                      goodbye_pref))


__help__ = """
*Yalnızca yöneticiler:*
 • `/welcome <on/off>`*:* karşılama mesajlarını etkinleştir / devre dışı bırak.
 • `/welcome`*:* mevcut karşılama ayarlarını gösterir.
 • `/welcome noformat`*:* biçimlendirme olmadan geçerli karşılama ayarlarını gösterir - hoş geldiniz mesajlarınızı geri dönüştürmek için kullanışlıdır!
 • `/goodbye`*:* `/welcome` ile aynı kullanım ve argümanlar.
 • `/setwelcome <sometext>`*:* özel bir karşılama mesajı ayarlayın. Medyaya yanıt olarak kullanılırsa, o medyayı kullanır.
 • `/setgoodbye <sometext>`*:* özel bir veda mesajı ayarlayın. Medyaya yanıt olarak kullanılırsa, o medyayı kullanır.
 • `/resetwelcome`*:* varsayılan karşılama mesajına sıfırlayın.
 • `/resetgoodbye`*:* varsayılan hoşçakal mesajına sıfırlayın.
 • `/cleanwelcome <on/off>`*:* Yeni üyede, sohbete spam göndermekten kaçınmak için önceki hoş geldiniz mesajını silmeyi deneyin.
 • `/welcomemutehelp`*:* hoş geldiniz sesini kapatmalar hakkında bilgi verir.
 • `/cleanservice <on/off>`*:* karşılama / bırakılan servis mesajlarını siler. 
 *Misal:*
kullanıcı sohbete katıldı, kullanıcı sohbeti terk etti.

*Welcome markdown:* 
 • `/welcomehelp`*:* özel hoş geldiniz / hoşçakal mesajları için daha fazla biçimlendirme bilgisi görüntüleyin.
"""

NEW_MEM_HANDLER = MessageHandler(Filters.status_update.new_chat_members,
                                 new_member)
LEFT_MEM_HANDLER = MessageHandler(Filters.status_update.left_chat_member,
                                  left_member)
WELC_PREF_HANDLER = CommandHandler("welcome", welcome, filters=Filters.group)
GOODBYE_PREF_HANDLER = CommandHandler("goodbye", goodbye, filters=Filters.group)
SET_WELCOME = CommandHandler("setwelcome", set_welcome, filters=Filters.group)
SET_GOODBYE = CommandHandler("setgoodbye", set_goodbye, filters=Filters.group)
RESET_WELCOME = CommandHandler(
    "resetwelcome", reset_welcome, filters=Filters.group)
RESET_GOODBYE = CommandHandler(
    "resetgoodbye", reset_goodbye, filters=Filters.group)
WELCOMEMUTE_HANDLER = CommandHandler(
    "welcomemute", welcomemute, filters=Filters.group)
CLEAN_SERVICE_HANDLER = CommandHandler(
    "cleanservice", cleanservice, filters=Filters.group)
CLEAN_WELCOME = CommandHandler(
    "cleanwelcome", clean_welcome, filters=Filters.group)
WELCOME_HELP = CommandHandler("welcomehelp", welcome_help)
WELCOME_MUTE_HELP = CommandHandler("welcomemutehelp", welcome_mute_help)
BUTTON_VERIFY_HANDLER = CallbackQueryHandler(user_button, pattern=r"user_join_")

dispatcher.add_handler(NEW_MEM_HANDLER)
dispatcher.add_handler(LEFT_MEM_HANDLER)
dispatcher.add_handler(WELC_PREF_HANDLER)
dispatcher.add_handler(GOODBYE_PREF_HANDLER)
dispatcher.add_handler(SET_WELCOME)
dispatcher.add_handler(SET_GOODBYE)
dispatcher.add_handler(RESET_WELCOME)
dispatcher.add_handler(RESET_GOODBYE)
dispatcher.add_handler(CLEAN_WELCOME)
dispatcher.add_handler(WELCOME_HELP)
dispatcher.add_handler(WELCOMEMUTE_HANDLER)
dispatcher.add_handler(CLEAN_SERVICE_HANDLER)
dispatcher.add_handler(BUTTON_VERIFY_HANDLER)
dispatcher.add_handler(WELCOME_MUTE_HELP)

__mod_name__ = "Greetings"
__command_list__ = []
__handlers__ = [
    NEW_MEM_HANDLER,
    LEFT_MEM_HANDLER,
    WELC_PREF_HANDLER,
    GOODBYE_PREF_HANDLER,
    SET_WELCOME,
    SET_GOODBYE,
    RESET_WELCOME,
    RESET_GOODBYE,
    CLEAN_WELCOME,
    WELCOME_HELP,
    WELCOMEMUTE_HANDLER,
    CLEAN_SERVICE_HANDLER,
    BUTTON_VERIFY_HANDLER,
    WELCOME_MUTE_HELP,
]
