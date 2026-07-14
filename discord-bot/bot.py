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

# ─── MongoDB設定 ───
MONGO_URI = "mongodb+srv://baketan373_db_user:15351348650Ad@cluster0.misxalm.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client["my_discord_bot"]
collection = db["user_data"]

def get_user_data(user_id):
    user_id_str = str(user_id)
    data = collection.find_one({"_id": user_id_str})
    if data: return data
    return {"_id": user_id_str, "points": 1000, "last_daily": None}

def save_user_data(user_id, data):
    collection.update_one({"_id": str(user_id)}, {"$set": data}, upsert=True)

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
            res_msg = f"🎉 **大当り！ {mult}倍！**\n💰 獲得: +{win}コイン"
            if mult == 7.0 and not self.is_jackpot: slot_data[self.user_id]["jackpot_until"] = time.time() + 10; res_msg += "\n🚨 **JACKPOTモード突入！**"
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

class BJView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet
        self.user_id = str(user_id)
        self.msg = msg
        self.p_hand = []
        self.d_hand = []
        self.can_double = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ これはあなたのゲームではありません！", ephemeral=True)
            return False
        return True

    async def start_game(self):
        await self.msg.edit(content=f"🃏 **Blackjack (賭け金:{self.bet})**\nカードを配っています...", view=None)
        for i in range(2):
            await asyncio.sleep(0.8)
            self.p_hand.append(draw_card())
            self.d_hand.append(draw_card())
        await self.update("あなたのターンです！")

    async def update(self, status=""):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = f"{card_to_str(self.d_hand[0])} , ❓"
        
        self.clear_items()
        
        # ボタンを作成し、その場でcallbackを割り当てる
        hit_btn = discord.ui.Button(label="Hit", style=discord.ButtonStyle.primary, custom_id="hit")
        hit_btn.callback = self.hit
        self.add_item(hit_btn)
        
        stand_btn = discord.ui.Button(label="Stand", style=discord.ButtonStyle.secondary, custom_id="stand")
        stand_btn.callback = self.stand
        self.add_item(stand_btn)
        
        if self.can_double:
            double_btn = discord.ui.Button(label="Double", style=discord.ButtonStyle.success, custom_id="double")
            double_btn.callback = self.double
            self.add_item(double_btn)
        
        await self.msg.edit(content=f"🃏 **Blackjack**\nディーラー: {d_str}\nあなた ({calc_score(self.p_hand)}点): {p_str}\n\n{status}", view=self)

    # --- 以下は変更なし ---
    async def hit(self, i: discord.Interaction):
        self.can_double = False; card = draw_card(); self.p_hand.append(card); await i.response.defer()
        if calc_score(self.p_hand) > 21: await i.edit_original_response(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)", view=None); self.stop()
        else: await self.update()

    async def stand(self, i: discord.Interaction): await i.response.defer(); await self.stop_game(i)

    async def double(self, i: discord.Interaction):
        data = get_user_data(self.user_id)
        if data["points"] < self.bet: await i.response.send_message("❌ 所持金不足！", ephemeral=True); return
        data["points"] -= self.bet; save_user_data(self.user_id, data); self.bet *= 2; card = draw_card(); self.p_hand.append(card)
        if calc_score(self.p_hand) > 21: await i.response.edit_message(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)", view=None); self.stop()
        else: await self.stop_game(i)

    async def stop_game(self, i: discord.Interaction):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        while calc_score(self.d_hand) < 17: self.d_hand.append(draw_card())
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand); d_str_final = ", ".join([card_to_str(c) for c in self.d_hand])
        data = get_user_data(self.user_id)
        if d_sc > 21 or p_sc > d_sc: data["points"] += (self.bet * 2); res = "🎉 勝ち！"
        elif p_sc == d_sc: data["points"] += self.bet; res = "🤝 引き分け"
        else: res = "💀 負け..."
        save_user_data(self.user_id, data)
        await i.edit_original_response(content=f"結果: {res}\nあなた: {p_str} ({p_sc}点)\nディーラー: {d_str_final} ({d_sc}点)\n所持金: {data['points']}コイン", view=None); self.stop()

class DiceView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet; self.user_id = str(user_id); self.msg = msg; self.dice_map = {1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅'}; self.d_dice = []; self.p_dice = []
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id: await interaction.response.send_message("❌ これはあなたのゲームではありません！", ephemeral=True); return False
        return True
    async def roll_animation(self, label, is_dealer):
        self.clear_items()
        for _ in range(5):
            temp_n = random.randint(1, 6); d_str = " ".join([self.dice_map[n] for n in self.d_dice]); p_str = " ".join([self.dice_map[n] for n in self.p_dice])
            await self.msg.edit(content=f"🎲 **勝負！**\nディーラー: {d_str} {'🎲' if is_dealer else ''}\nあなた: {p_str} {'🎲' if not is_dealer else ''}\n\n🎲 **{label}**", view=self); await asyncio.sleep(0.3)
        return random.randint(1, 6)
    async def start_dice(self):
        self.d_dice.append(await self.roll_animation("ディーラー：1つ目...", True)); self.d_dice.append(await self.roll_animation("ディーラー：2つ目...", True))
        await self.update_view("ディーラー確定！")
    async def update_view(self, status):
        count_p = len(self.p_dice) + 1
        self.clear_items(); self.add_item(discord.ui.Button(label=f"{count_p}つ目を振る！", style=discord.ButtonStyle.success)).callback = self.roll
        await self.msg.edit(content=f"🎲 **勝負！**\nディーラー: {' '.join([self.dice_map[n] for n in self.d_dice])}\nあなた: {' '.join([self.dice_map[n] for n in self.p_dice])}\n\n【状態】: {status}", view=self)
    async def roll(self, i: discord.Interaction):
        await i.response.defer(); self.p_dice.append(await self.roll_animation("あなた：振っています...", False))
        if len(self.p_dice) == 2:
            d_sum, p_sum = sum(self.d_dice), sum(self.p_dice); data = get_user_data(self.user_id)
            if p_sum > d_sum: data["points"] += (self.bet * 2); res = "🎉 勝ち！"
            elif p_sum < d_sum: res = "💀 負け..."
            else: data["points"] += self.bet; res = "🤝 引き分け"
            save_user_data(self.user_id, data)
            await i.edit_original_response(content=f"🎲 **結果！**\nディーラー: {sum(self.d_dice)}点\nあなた: {sum(self.p_dice)}点\n\n{res}", view=None); self.stop()
        else: await self.update_view("1つ目確定！")

# ─── コマンド ───
async def get_bet(ctx):
    await ctx.send("💸 **賭け金を入力してね！**")
    try:
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content); data = get_user_data(ctx.author.id)
        if bet <= 0 or data["points"] < bet: await ctx.send("❌ 不正な額か、所持金不足！"); return None
        data["points"] -= bet; save_user_data(ctx.author.id, data); return bet
    except: await ctx.send("❌ 無効な入力か時間切れです。"); return None

@bot.command()
async def slot(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎰 準備中..."); await msg.edit(view=SlotView(bet, ctx.author.id, msg))

@bot.command()
async def blackjack(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🃏 準備中..."); v = BJView(bet, ctx.author.id, msg); await msg.edit(view=v); await v.start_game()

@bot.command()
async def dice(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎲 準備中..."); v = DiceView(bet, ctx.author.id, msg); await msg.edit(view=v); await v.start_dice()

bot.run(os.getenv('TOKEN'))
