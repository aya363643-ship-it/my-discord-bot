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

# ─── Blackjack View ───
class BJView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=60.0)
        self.bet = bet
        self.user_id = user_id
        self.msg = msg
        self.p_hand = []
        self.d_hand = []
        self.can_double = True  # ダブルダウン判定用

    async def deal_cards(self):
        for _ in range(2):
            await self.msg.edit(content="🃏 カードを配っています...")
            await asyncio.sleep(0.5)
            self.p_hand.append(draw_card())
            self.d_hand.append(draw_card())
        
        await self.update_display("あなたのターンです", self)
        
    async def update_display(self, status, view=None):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = f"{card_to_str(self.d_hand[0])}, ❓" if "あなたのターン" in status else ", ".join([card_to_str(c) for c in self.d_hand])
        content = f"🃏 **Blackjack (賭け金:{self.bet})**\nディーラー: {d_str}\nあなた ({calc_score(self.p_hand)}点): {p_str}\n\n{status}"
        
        # ダブルダウンが可能な時だけボタンを有効化する制御
        if view:
            for item in view.children:
                if item.label == "Double":
                    item.disabled = not self.can_double
        
        await self.msg.edit(content=content, view=view)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, i: discord.Interaction, button: discord.ui.Button):
        await i.response.defer()
        self.can_double = False # 1枚でも引いたらダブルダウン不可
        self.p_hand.append(draw_card())
        if calc_score(self.p_hand) > 21:
            await self.finish_game("💀 バースト！負けました...", 0)
        else:
            await self.update_display("あなたのターンです", self)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success)
    async def double(self, i: discord.Interaction, button: discord.ui.Button):
        await i.response.defer()
        data = get_user_data(self.user_id)
        if data["points"] < self.bet:
            await i.followup.send("❌ 所持金不足でダブルダウンできません！", ephemeral=True)
            return
        
        data["points"] -= self.bet
        self.bet *= 2
        save_user_data(self.user_id, data)
        
        # カードを1枚引いて即座にディーラーターンへ
        self.p_hand.append(draw_card())
        if calc_score(self.p_hand) > 21:
            await self.finish_game("💀 バースト！負けました...", 0)
        else:
            await self.dealer_turn()

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, i: discord.Interaction, button: discord.ui.Button):
        await i.response.defer()
        await self.dealer_turn()

    async def dealer_turn(self):
        self.clear_items()
        while calc_score(self.d_hand) < 17:
            await self.msg.edit(content=f"🃏 ディーラーが引いています... ({calc_score(self.d_hand)}点)", view=None)
            await asyncio.sleep(1.2)
            self.d_hand.append(draw_card())
        
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = ", ".join([card_to_str(c) for c in self.d_hand])
        await self.msg.edit(content=f"🃏 **ディーラーのターン終了**\nディーラー: {d_str} ({calc_score(self.d_hand)}点)\nあなた: {p_str} ({calc_score(self.p_hand)}点)\n\n結果に移動します...", view=None)
        await asyncio.sleep(2.0)
        
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand)
        if d_sc > 21 or p_sc > d_sc: await self.finish_game(f"🎉 **あなたの勝ち！**\n💰 利益: +{self.bet}コイン", self.bet * 2)
        elif p_sc == d_sc: await self.finish_game(f"🤝 **引き分け**\n💰 収支: ±0コイン (返金)", self.bet)
        else: await self.finish_game(f"💀 **負けました...**\n📉 損失: -{self.bet}コイン", 0)

    async def finish_game(self, result_text, payout):
        self.clear_items()
        data = get_user_data(self.user_id)
        if payout > 0: data["points"] += payout
        save_user_data(self.user_id, data)
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = ", ".join([card_to_str(c) for c in self.d_hand])
        final_msg = f"{result_text}\n\nあなた: {p_str} ({calc_score(self.p_hand)}点)\nディーラー: {d_str} ({calc_score(self.d_hand)}点)\n💳 現在の所持金: {data['points']}コイン"
        await self.msg.edit(content=final_msg, view=None)
        self.stop()

class DiceView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet
        self.user_id = str(user_id)
        self.msg = msg
        self.dice_map = {1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅'}
        self.d_dice = []
        self.p_dice = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ これはあなたのゲームではありません！", ephemeral=True)
            return False
        return True

    # 演出中にボタンを維持するためのヘルパー
    async def update_message(self, status, show_button=False):
        self.clear_items()
        d_str = " ".join([self.dice_map[n] for n in self.d_dice])
        p_str = " ".join([self.dice_map[n] for n in self.p_dice])
        d_score = sum(self.d_dice)
        p_score = sum(self.p_dice)
        
        content = (f"🎲 **勝負！**\n"
                   f"ディーラー: {d_str} ({d_score}点)\n"
                   f"あなた: {p_str} ({p_score}点)\n\n"
                   f"【状態】: {status}")
        
        if show_button:
            count_p = len(self.p_dice) + 1
            btn = discord.ui.Button(label=f"{count_p}つ目を振る！", style=discord.ButtonStyle.success)
            btn.callback = self.roll
            self.add_item(btn)
            
        await self.msg.edit(content=content, view=self)

    async def roll_animation(self, label, is_dealer):
        # 演出中はボタンを消した状態で一時的に更新
        for _ in range(5):
            temp_n = random.randint(1, 6)
            # 現在の状態に一時的なダイスを加えて表示
            temp_d = self.d_dice + ([temp_n] if is_dealer else [])
            temp_p = self.p_dice + ([temp_n] if not is_dealer else [])
            
            d_str = " ".join([self.dice_map[n] for n in temp_d])
            p_str = " ".join([self.dice_map[n] for n in temp_p])
            
            await self.msg.edit(content=f"🎲 **勝負！**\nディーラー: {d_str}\nあなた: {p_str}\n\n🎲 **{label}**")
            await asyncio.sleep(0.3)
        return random.randint(1, 6)

    async def start_dice(self):
        self.d_dice.append(await self.roll_animation("ディーラー：1つ目...", True))
        self.d_dice.append(await self.roll_animation("ディーラー：2つ目...", True))
        await self.update_message("ディーラー確定！", show_button=True)

    async def roll(self, i: discord.Interaction):
        await i.response.defer()
        self.p_dice.append(await self.roll_animation("あなた：振っています...", False))
        
        if len(self.p_dice) == 2:
            d_sum, p_sum = sum(self.d_dice), sum(self.p_dice)
            data = get_user_data(self.user_id)
            
            # 結果に応じた処理とメッセージ作成
            if p_sum > d_sum:
                win_amount = self.bet * 2
                data["points"] += win_amount
                res = f"🎉 勝ち！ (+{win_amount}コイン)"
            elif p_sum < d_sum:
                res = f"💀 負け... (-{self.bet}コイン)"
            else:
                data["points"] += self.bet
                res = f"🤝 引き分け (+0コイン)"
            
            save_user_data(self.user_id, data)
            
            # 結果表示（所持金も追加）
            final_status = f"結果発表！ {res}\n💳 現在の所持金: {data['points']}コイン"
            await self.update_message(final_status)
            self.stop()
        else:
            await self.update_message("1つ目確定！", show_button=True)

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
async def blackjack(ctx):
    bet = await get_bet(ctx)
    if bet:
        msg = await ctx.send("🃏 ゲーム開始...")
        view = BJView(bet, ctx.author.id, msg)
        await msg.edit(view=view)
        # 演出を開始
        await view.deal_cards()

@bot.command()
async def slot(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎰 準備中..."); await msg.edit(view=SlotView(bet, ctx.author.id, msg))



@bot.command()
async def dice(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎲 準備中..."); v = DiceView(bet, ctx.author.id, msg); await msg.edit(view=v); await v.start_dice()
# ─── 権限者用コマンド ───
@bot.command()
@is_allowed_user() # 権限があるユーザーのみ実行可能
async def give_points(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ 正の数値を入力してください。")
        return
    
    data = get_user_data(member.id)
    data["points"] += amount
    save_user_data(member.id, data)
    
    await ctx.send(f"✅ {member.mention} に **{amount}コイン** を付与しました！\n現在の所持金: {data['points']}コイン")
bot.run(os.getenv('TOKEN'))
