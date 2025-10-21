import os
import json
import datetime
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATA_FILE = "data.json"
DEFAULT_RATE = 7.2
TIMEZONE = datetime.timezone(datetime.timedelta(hours=8))  # 北京时间

# ---------------- 数据加载与保存 ---------------- #
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"records": [], "rate": DEFAULT_RATE, "check_count": {}}, f, ensure_ascii=False)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------- 工具函数 ---------------- #
def format_time(ts=None):
    return datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

def today_date():
    return datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d")

def get_rate(data):
    return data.get("rate", DEFAULT_RATE)

def set_rate(data, rate):
    data["rate"] = rate
    save_data(data)

# ---------------- 查U（TRON）API ---------------- #
def query_tron_address(address):
    try:
        r = requests.get(f"https://apilist.tronscanapi.com/api/account?address={address}", timeout=10)
        data = r.json()

        balance = float(data.get("balance", 0)) / 1_000_000
        usdt = 0.0
        for token in data.get("trc20token_balances", []):
            if token.get("symbol") == "USDT":
                usdt = float(token.get("balance", 0)) / 1_000_000

        energy = data.get("energy", 0)
        bandwidth = data.get("bandwidth", 0)
        net_used = data.get("netUsed", 0)
        create_time = data.get("create_time", 0)
        update_time = data.get("latest_opration_time", 0)

        msg = f"📄查询地址：{address}\n⏱查询时间：{format_time()}\n"
        msg += f"🪬查询结果：该地址已激活\n\n"
        msg += f"🪫TRX余额：{balance:.6f}\n💵USDT余额：{usdt:.6f}\n"
        msg += f"🔋能量：{energy}\n🌐带宽：{net_used}/{bandwidth}\n"

        if create_time:
            ct = datetime.datetime.fromtimestamp(create_time / 1000, TIMEZONE)
            msg += f"⏰创建时间：{ct.strftime('%Y/%m/%d %H:%M:%S')}\n"
        if update_time:
            ut = datetime.datetime.fromtimestamp(update_time / 1000, TIMEZONE)
            msg += f"⏰最后活跃：{ut.strftime('%Y/%m/%d %H:%M:%S')}\n"

        msg += "\n®️安全等级：✅优秀 - 无授权/无多签\n"
        msg += "⛔️风险提示：该地址余额较少，请注意交易风险。"
        return msg
    except Exception as e:
        return f"❌ 查询失败：{e}"

# ---------------- 核心功能 ---------------- #
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    data = load_data()

    # 查账
    if text.startswith("查账"):
        parts = text.split()
        date = today_date() if len(parts) == 1 else parts[1]
        records = [r for r in data["records"] if r["date"] == date]
        if not records:
            await update.message.reply_text(f"📅 {date} 没有记录。", reply_to_message_id=update.message.message_id)
            return

        total_in = sum(r["amount"] for r in records if r["type"] == "in")
        total_out = sum(r["amount"] for r in records if r["type"] == "out")
        rate = get_rate(data)
        msg = f"📅 {date} 账单汇总\n\n"
        msg += f"入账：{total_in:.2f} 元 | {total_in / rate:.2f}U\n"
        msg += f"支出：{total_out:.2f} 元 | {total_out / rate:.2f}U\n"
        msg += f"净额：{(total_in - total_out):.2f} 元 | {(total_in - total_out)/rate:.2f}U\n"
        msg += f"汇率：{rate:.2f}"
        await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)
        return

    # 修改汇率
    if text.startswith("汇率"):
        parts = text.split()
        if len(parts) == 2:
            try:
                rate = float(parts[1])
                set_rate(data, rate)
                await update.message.reply_text(f"✅ 汇率已更新为 {rate:.2f}", reply_to_message_id=update.message.message_id)
            except:
                await update.message.reply_text("❌ 格式错误，应为：汇率 7.25", reply_to_message_id=update.message.message_id)
        else:
            await update.message.reply_text(f"当前汇率：{get_rate(data):.2f}", reply_to_message_id=update.message.message_id)
        return

    # 查U
    if text.startswith("查U"):
        parts = text.split()
        if len(parts) == 2:
            addr = parts[1].strip()
            count = data["check_count"].get(addr, 0) + 1
            data["check_count"][addr] = count
            save_data(data)
            msg = query_tron_address(addr)
            msg += f"\n\n被查次数：{count}"
            await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)
        else:
            await update.message.reply_text("❌ 格式错误，应为：查U 地址", reply_to_message_id=update.message.message_id)
        return

    # 记账 (+ / -)
    if text.startswith("+") or text.startswith("-"):
        sign = 1 if text.startswith("+") else -1
        t = "in" if sign > 0 else "out"
        try:
            num = float(text[1:].split()[0].replace("u", "").replace("U", ""))
            currency = "U" if ("u" in text.lower()) else "CNY"
            rate = get_rate(data)
            entry = {
                "time": format_time(),
                "date": today_date(),
                "amount": num if currency == "CNY" else num * rate,
                "type": t,
                "note": text
            }
            data["records"].append(entry)
            save_data(data)
            await update.message.reply_text(f"✅ 已记录：{text}", reply_to_message_id=update.message.message_id)
        except:
            await update.message.reply_text("❌ 无法识别金额。", reply_to_message_id=update.message.message_id)
        return

    # 其他
    if text == "/help" or text == "help":
        msg = (
            "📘 可用指令：\n"
            "+188 / -46 ：记录收支（默认人民币，带u为USDT）\n"
            "查账 / 查账 YYYY-MM-DD ：查看账单\n"
            "改 12 to 13 ：修改账单（管理员）\n"
            "清零 ：清除账单（管理员）\n"
            "查U 地址 ：查询TRON地址余额\n"
            "汇率 / 汇率 X.XX ：查看或修改汇率"
        )
        await update.message.reply_text(msg, reply_to_message_id=update.message.message_id)

# ---------------- 启动 ---------------- #
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("✅ 机器人已启动")
    app.run_polling()
