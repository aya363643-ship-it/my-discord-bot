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

RCON_HOST = "127.0.0.1"
RCON_PORT = 25575
RCON_PASSWORD = "MySecretPassword123"

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
            if amount_change > 0: response = rcon.command(f"eco give {mc_name} {amount_change}")
            elif amount_change < 0: response = rcon.command(f"eco take {mc_name} {abs(amount_change)}")
            print(f"マイクラへの送信結果: {response}") # ログに結果が出る
            return True
    except Exception as e:
        print(f"マイクラ同期エラー: {e}") # ここでなぜ失敗したか分かる
        return False

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
                        sync_to_minecraft(user_id, 50)
                        channel = bot.get_channel(1447850881688010819)
                        if channel: await channel.send(f"🎙️ {member.mention} がボイスチャンネルに30分滞在したため、💰 **50コイン** を獲得しました！")
                    except Exception as e: print(f"VCエラー: {e}")

# ─── マイクラ残高の自動反映タスク ───
@tasks.loop(seconds=30)
async def auto_sync_from_mc():
    all_users = collection.find({"mc_name": {"$ne": None}})
    channel = bot.get_channel(1526095284357173358)
    
    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as rcon:
            for user in all_users:
                mc_name = user["mc_name"]
                response = rcon.command(f"bal {mc_name}")
                
                # 【重要：デバッグ用】コンソールに何が返ってきているか出力
                print(f"DEBUG: {mc_name} の bal 結果: {response}")
                
                import re
                # 数字を探す
                numbers = re.findall(r'\d+', response)
                
                if not numbers:
                    print(f"DEBUG: {mc_name} の数字抽出に失敗しました。")
                    continue
                
                    new_balance = int(numbers[0])
                    old_balance = user.get("points")
                    
                    if old_balance != new_balance:
                        # 差分を計算（増えた分だけ表示するため）
                        diff = new_balance - old_balance
                        
                        # MongoDBを更新
                        user["points"] = new_balance
                        save_user_data(user["_id"], user)
                        
                        # ここでDiscordに通知を送る
                        if channel and diff > 0:
                            await channel.send(f"💰 **マイクラ収入通知**: {mc_name} さんがマイクラで {diff} コイン稼ぎました！Discordにも反映されました！")
                        
                        print(f"自動同期: {mc_name} の残高を {new_balance} に更新しました")
    except Exception as e:
        print(f"自動同期エラー: {e}")

@auto_sync_from_mc.before_loop
async def before_auto_sync():
    await bot.wait_until_ready()

# on_ready 内でタスクを開始させる
# on_ready を以下のように書き換えてください
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    if not check_vc_rewards.is_running(): check_vc_rewards.start()
    if not auto_sync_from_mc.is_running(): auto_sync_from_mc.start()

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
            sync_to_minecraft(self.user_id, win)
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

class BJView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=60.0)
        self.bet = bet
        self.user_id = user_id
        self.msg = msg
        self.p_hand = []
        self.d_hand = []
        self.can_double = True
    async def deal_cards(self):
        for _ in range(2): self.p_hand.append(draw_card()); self.d_hand.append(draw_card())
        await self.update_display("あなたのターンです", self)
    async def update_display(self, status, view=None):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = f"{card_to_str(self.d_hand[0])}, ❓" if "あなたのターン" in status else ", ".join([card_to_str(c) for c in self.d_hand])
        content = f"🃏 **Blackjack**\nディーラー: {d_str}\nあなた ({calc_score(self.p_hand)}点): {p_str}\n\n{status}"
        await self.msg.edit(content=content, view=view)
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, i: discord.Interaction, b: discord.ui.Button):
        self.can_double = False; self.p_hand.append(draw_card())
        if calc_score(self.p_hand) > 21: await self.finish_game("💀 バースト！負けました...", 0)
        else: await self.update_display("あなたのターンです", self)
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, i: discord.Interaction, b: discord.ui.Button): await self.dealer_turn()
    async def dealer_turn(self):
        while calc_score(self.d_hand) < 17: self.d_hand.append(draw_card())
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand)
        if d_sc > 21 or p_sc > d_sc: await self.finish_game("🎉 勝ち！", self.bet * 2)
        elif p_sc == d_sc: await self.finish_game("🤝 引き分け", self.bet)
        else: await self.finish_game("💀 負け...", 0)
    async def finish_game(self, result_text, payout):
        self.clear_items(); data = get_user_data(self.user_id)
        if payout > 0: data["points"] += payout; sync_to_minecraft(self.user_id, payout - self.bet)
        save_user_data(self.user_id, data); await self.msg.edit(content=f"{result_text}\n💳 所持金: {data['points']}コイン", view=None)

class DiceView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=60.0); self.bet = bet; self.user_id = str(user_id); self.msg = msg
        self.d_dice = [random.randint(1, 6), random.randint(1, 6)]; self.p_dice = []
    async def start_dice(self):
        btn = discord.ui.Button(label="振る！", style=discord.ButtonStyle.success)
        btn.callback = self.roll; self.add_item(btn); await self.msg.edit(view=self)
    async def roll(self, i: discord.Interaction):
        self.p_dice.append(random.randint(1, 6))
        if len(self.p_dice) == 2:
            d_sum, p_sum = sum(self.d_dice), sum(self.p_dice); data = get_user_data(self.user_id)
            if p_sum > d_sum: data["points"] += self.bet * 2; sync_to_minecraft(self.user_id, self.bet)
            elif p_sum == d_sum: data["points"] += self.bet; sync_to_minecraft(self.user_id, 0)
            save_user_data(self.user_id, data); await self.msg.edit(content=f"結果: D:{d_sum} vs P:{p_sum}", view=None)
        else: await self.msg.edit(content=f"次を振ってね！ 現在: {self.p_dice}", view=self)

# ─── コマンド ───
async def get_bet(ctx):
    await ctx.send("💸 **賭け金を入力してね！**")
    try:
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content); data = get_user_data(ctx.author.id)
        if bet <= 0 or data["points"] < bet: await ctx.send("❌ 不正か所持金不足！"); return None
        data["points"] -= bet; save_user_data(ctx.author.id, data); sync_to_minecraft(ctx.author.id, -bet)
        return bet
    except: await ctx.send("❌ 無効です。"); return None

@bot.command()
async def blackjack(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🃏 開始..."); v = BJView(bet, ctx.author.id, msg); await msg.edit(view=v); await v.deal_cards()

@bot.command()
async def slot(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎰 開始..."); await msg.edit(view=SlotView(bet, ctx.author.id, msg))

@bot.command()
async def dice(ctx):
    bet = await get_bet(ctx)
    if bet: msg = await ctx.send("🎲 開始..."); v = DiceView(bet, ctx.author.id, msg); await v.start_dice()

@bot.command()
async def register(ctx, mc_name: str):
    data = get_user_data(ctx.author.id); data["mc_name"] = mc_name; save_user_data(ctx.author.id, data)
    await ctx.send(f"✅ 登録完了: {mc_name}")

@bot.command()
@is_allowed_user()
async def give_points(ctx, member: discord.Member, amount: int):
    data = get_user_data(member.id); data["points"] += amount; save_user_data(member.id, data)
    sync_to_minecraft(member.id, amount); await ctx.send(f"✅ 付与完了: {member.mention}")


@bot.command()
async def sync(ctx):
    """マイクラの残高をDiscordに強制同期する"""
    data = get_user_data(ctx.author.id)
    if not data.get("mc_name"):
        await ctx.send("❌ まだマイクラ名を登録していません！ `!register <名前>` で登録してください。")
        return

    mc_name = data["mc_name"]
    try:
        with MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT) as rcon:
            # マイクラの残高を取得するコマンド
            response = rcon.command(f"bal {mc_name}")
            
            # responseの中から数字だけを抽出（サーバーの表示形式に合わせて調整が必要な場合があります）
            # ここではシンプルにコンソールに結果を表示し、ユーザーに手動入力してもらうか、
            # 抽出処理を組み込むのが一般的です。
            await ctx.send(f"🔍 マイクラサーバーからの応答:\n```\n{response}\n```\n※マイクラ内の残高をDiscordに反映させるには、管理者に相談するか、この数値を基準に管理してください。")
    except Exception as e:
        await ctx.send(f"❌ 同期エラー: {e}")

bot.run(os.getenv('TOKEN'))
