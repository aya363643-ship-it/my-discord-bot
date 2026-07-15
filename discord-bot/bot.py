import discord
from discord.ext import commands, tasks
import random
import asyncio
import os
from flask import Flask
from threading import Thread
from datetime import datetime
from pymongo import MongoClient
import pymongo
import time
from mcrcon import MCRcon

# ─── MongoDB設定 ───
MONGO_URI = "mongodb+srv://baketan373_db_user:15351348650Ad@cluster0.misxalm.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client["my_discord_bot"]
collection = db["user_data"]

# ─── マイクラRCON設定 ───
RCON_HOST = "127.0.0.1"
RCON_PORT = 25575
RCON_PASSWORD = "あなたのパスワード" 

def get_user_data(user_id):
    user_id_str = str(user_id)
    data = collection.find_one({"_id": user_id_str})
    if data: return data
    return {"_id": user_id_str, "points": 1000, "last_daily": None, "mc_name": None}

def save_user_data(user_id, data):
    collection.update_one({"_id": str(user_id)}, {"$set": data}, upsert=True)

# ─── マイクラ同期関数 ───
def sync_to_minecraft(user_id, amount_change):
    data = get_user_data(user_id)
    if not data.get("mc_name"): return False
    mc_name = data["mc_name"]
    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as rcon:
            if amount_change > 0: rcon.command(f"eco give {mc_name} {amount_change}")
            elif amount_change < 0: rcon.command(f"eco take {mc_name} {abs(amount_change)}")
            return True
    except: return False

# ─── 24時間稼働サーバー ───
app = Flask('')
@app.route('/')
def home(): return "I am alive"
def run(): app.run(host='0.0.0.0', port=8080)
Thread(target=run).start()

# ─── ボット設定 ───
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

ANNOUNCEMENT_CHANNEL_ID = 1526095284357173358
ALLOWED_USERS = [825679340209438820, 872839459740192768]

def is_allowed_user():
    async def predicate(ctx):
        if ctx.author.id in ALLOWED_USERS: return True
        await ctx.send("❌ このコマンドを実行する権限がありません！")
        return False
    return commands.check(predicate)

vc_durations = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    if not check_vc_rewards.is_running(): check_vc_rewards.start()

@tasks.loop(minutes=1)
async def check_vc_rewards():
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                if member.bot: continue
                user_id = member.id
                if user_id not in vc_durations: vc_durations[user_id] = 0
                vc_durations[user_id] += 1
                if vc_durations[user_id] >= 30:
                    vc_durations[user_id] = 0
                    try:
                        data = get_user_data(user_id)
                        data["points"] += 50
                        save_user_data(user_id, data)
                        sync_to_minecraft(user_id, 50) # ★追加
                        channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
                        if channel: await channel.send(f"🎙️ {member.mention} がボイスチャンネルに30分滞在したため、💰 **50コイン** を獲得しました！")
                    except Exception as e: print(f"VCエラー: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    if before.channel and not after.channel:
        if member.id in vc_durations: del vc_durations[member.id]

# ─── ゲーム用ヘルパー ───
def draw_card(): return {'num': random.randint(1, 13), 'suit': random.choice(['♠️', '♥️', '♣️', '♦️'])}
def card_to_str(c):
    names = {1: 'A', 11: 'J', 12: 'Q', 13: 'K'}
    return f"{c['suit']}{names.get(c['num'], c['num'])}"

def calc_score(hand):
    score, aces = 0, 0
    for card in hand:
        if card['num'] == 1: aces += 1; score += 11
        elif card['num'] >= 11: score += 10
        else: score += card['num']
    while score > 21 and aces > 0: score -= 10; aces -= 1
    return score

slot_data = {}

# ─── 各ゲームクラス ───
class SlotView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet
        self.user_id = str(user_id)
        self.msg = msg
        if self.user_id not in slot_data: slot_data[self.user_id] = {"jackpot_until": 0}
        self.is_jackpot = time.time() < slot_data[self.user_id]["jackpot_until"]
        self.icons = ['🎰', '💎', '🔔', '🍒', '🍋', '🍇', '✨', '🍀']
        self.final_grid = self.generate_result()
        self.btn_spin = discord.ui.Button(label="レバーを叩く！", style=discord.ButtonStyle.success, emoji="🕹️")
        self.btn_spin.callback = self.start_spin
        self.add_item(self.btn_spin)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ これはあなたのゲームではありません！", ephemeral=True)
            return False
        return True

    def generate_result(self):
        r = random.random() * 100
        if self.is_jackpot:
            if r < 15: return [[val]*3 for val in ['🎰']*3]
            if r < 50: return [[val]*3 for val in ['💎']*3]
            return [[val]*3 for val in ['🔔']*3]
        else:
            if r < 1: return [[val]*3 for val in ['🎰']*3]
            if r < 2: return [[val]*3 for val in ['💎']*3]
            if r < 5: return [[val]*3 for val in ['✨']*3]
            if r < 10: return [[val]*3 for val in ['🍇']*3]
            if r < 20: return [[val]*3 for val in ['🍒']*3]
            return [[random.choice(self.icons) for _ in range(3)] for _ in range(3)]

    async def start_spin(self, interaction: discord.Interaction):
        self.btn_spin.disabled = True
        await interaction.response.edit_message(view=self)
        current_grid = [["❓", "❓", "❓"], ["❓", "❓", "❓"], ["❓", "❓", "❓"]]
        for col in range(3):
            for _ in range(3): 
                for row in range(3): current_grid[row][col] = random.choice(self.icons)
                grid_str = "\n".join([" | ".join(row) for row in current_grid])
                await self.msg.edit(embed=discord.Embed(title="🎰 スロット回転中...", description=f"{grid_str}", color=0x3498db))
                await asyncio.sleep(0.3)
            for row in range(3): current_grid[row][col] = self.final_grid[row][col]
        await asyncio.sleep(0.5); await self.show_result()

    async def show_result(self):
        lines = self.check_win(self.final_grid)
        mult = 1.0
        if '🎰' in lines: mult = 7.0
        elif '💎' in lines: mult = 3.0
        elif '✨' in lines: mult = 2.0
        elif '🍇' in lines: mult = 1.5
        elif '🍒' in lines: mult = 1.2
        data = get_user_data(self.user_id)
        if mult > 1.0:
            win = int(self.bet * mult); data["points"] += win; save_user_data(self.user_id, data)
            sync_to_minecraft(self.user_id, win) # ★追加
            res_msg = f"🎉 **大当り！ {mult}倍！**\n💰 獲得: +{win}コイン"
        else: res_msg = f"💀 **残念！はずれ！**\n📉 損失: -{self.bet}コイン"
        grid_str = "\n".join([" | ".join(row) for row in self.final_grid])
        await self.msg.edit(embed=discord.Embed(title="🎰 結果発表", description=f"{grid_str}\n\n{res_msg}\n💳 現在の所持金: {data['points']}コイン", color=0xf1c40f if mult > 1.0 else 0x95a5a6), view=None)

    def check_win(self, grid):
        lines = []
        for r in range(3):
            if grid[r][0] == grid[r][1] == grid[r][2]: lines.append(grid[r][0])
        if grid[0][0] == grid[1][1] == grid[2][2]: lines.append(grid[0][0])
        if grid[0][2] == grid[1][1] == grid[2][0]: lines.append(grid[0][2])
        return lines

# ─── コマンド用 ───
async def get_bet(ctx):
    await ctx.send("💸 **賭け金を入力してね！**")
    try:
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content); data = get_user_data(ctx.author.id)
        if bet <= 0 or data["points"] < bet: await ctx.send("❌ 不正な額か、所持金不足！"); return None
        data["points"] -= bet; save_user_data(ctx.author.id, data)
        sync_to_minecraft(ctx.author.id, -bet) # ★追加
        return bet
    except: await ctx.send("❌ 無効な入力か時間切れです。"); return None

@bot.command()
async def blackjack(ctx):
    bet = await get_bet(ctx)
    if bet:
        msg = await ctx.send("🃏 ゲーム開始...")
        view = BJView(bet, ctx.author.id, msg)
        await msg.edit(view=view); await view.deal_cards()

@bot.command()
async def slot(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎰 準備中..."); await msg.edit(view=SlotView(bet, ctx.author.id, msg))

@bot.command()
async def dice(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎲 準備中..."); v = DiceView(bet, ctx.author.id, msg); await msg.edit(view=v); await v.start_dice()

@bot.command()
async def register(ctx, mc_name: str):
    data = get_user_data(ctx.author.id)
    data["mc_name"] = mc_name
    save_user_data(ctx.author.id, data)
    await ctx.send(f"✅ マイクラIDを **{mc_name}** に設定しました！")

@bot.command()
@is_allowed_user()
async def give_points(ctx, member: discord.Member, amount: int):
    data = get_user_data(member.id)
    data["points"] += amount; save_user_data(member.id, data)
    sync_to_minecraft(member.id, amount) # ★追加
    await ctx.send(f"✅ {member.mention} に {amount} コイン付与しました！")

bot.run(os.getenv('TOKEN'))
