import discord
from discord.ext import commands
import random
import asyncio
import json
import os
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# ─── 24時間稼働用サーバー ───
app = Flask('')
@app.route('/')
def home(): return "I am alive"
def run(): app.run(host='0.0.0.0', port=8080)
Thread(target=run).start()

# ─── ボット設定・データ管理 ───
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
DATA_FILE = 'points.json'
DAILY_FILE = 'daily.json'

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_points = load_json(DATA_FILE)
daily_data = load_json(DAILY_FILE)

# ─── デイリーボーナス ───
@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)
    now = datetime.now()
    last_claimed_str = daily_data.get(user_id)
    
    if last_claimed_str:
        last_claimed = datetime.fromisoformat(last_claimed_str)
        next_claim = last_claimed + timedelta(hours=24)
        if now < next_claim:
            diff = next_claim - now
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.send(f"⏳ **あと {hours}時間{minutes}分** 待ってね！")
            return

    amount = random.randint(100, 500)
    user_points[user_id] = user_points.get(user_id, 0) + amount
    daily_data[user_id] = now.isoformat()
    save_json(DATA_FILE, user_points)
    save_json(DAILY_FILE, daily_data)
    await ctx.send(f"🎉 **デイリーボーナス！**\n💰 **+{amount}コイン** ゲット！")

# ─── ゲーム共通ヘルパー ───
def draw_card(): return {'num': random.randint(1, 13), 'suit': random.choice(['♠️', '♥️', '♣️', '♦️'])}
def card_to_str(c):
    # 【固定】数字とマークの表記
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

# ─── 各ゲームクラス ───
class SlotView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet; self.user_id = str(user_id); self.msg = msg
        self.icons = ['🎰', '💎', '🔔', '🍒', '🍋', '🍇', '✨', '🍀']
        self.final_grid = [[random.choice(self.icons) for _ in range(3)] for _ in range(3)]
        self.stopped = [False, False, False]; self.is_spinning = True
        self.bg_task = asyncio.create_task(self.spin_animation())

    async def spin_animation(self):
        try:
            while self.is_spinning:
                grid = [[random.choice(self.icons) if not self.stopped[c] else self.final_grid[r][c] for c in range(3)] for r in range(3)]
                display = "\n".join([f"  [ {row[0]} | {row[1]} | {row[2]} ]" for row in grid])
                await self.msg.edit(content=f"🎰 **スロット** 🎰\n賭け金: {self.bet}\n\n{display}\n\n👇 **ボタンを押して止めて！**", view=self)
                await asyncio.sleep(0.3)
        except: pass

    async def check_finish(self, interaction):
        if all(self.stopped):
            self.is_spinning = False; self.bg_task.cancel(); self.stop()
            win = sum([1 for r in range(3) if self.final_grid[r][0] == self.final_grid[r][1] == self.final_grid[r][2]])
            if win > 0:
                p = self.bet * (win * 10)
                user_points[self.user_id] += p
                res = f"🎉 **大勝利！{win}ライン的中！**\n💰 **{p}コイン獲得！**"
            else: res = "💀 **残念！はずれ！**"
            save_json(DATA_FILE, user_points)
            await interaction.response.edit_message(content=res, view=None)

    @discord.ui.button(label="STOP", style=discord.ButtonStyle.primary)
    async def b(self, i, b):
        if not self.stopped[0]: self.stopped[0]=True
        elif not self.stopped[1]: self.stopped[1]=True
        else: self.stopped[2]=True
        b.disabled = all(self.stopped)
        await i.response.edit_message(view=self)
        if all(self.stopped): await self.check_finish(i)

class BJView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet; self.user_id = str(user_id); self.msg = msg
        self.p_hand = []; self.d_hand = []
        self.can_double = True

    async def start_game(self):
        for _ in range(2):
            self.p_hand.append(draw_card())
            await self.update(f"🃏 カードを引いています... あなたのカード: {card_to_str(self.p_hand[-1])}")
            await asyncio.sleep(1)
            self.d_hand.append(draw_card())
            await self.update(f"🃏 ディーラーがカードを引きました...")
            await asyncio.sleep(1)
        await self.update("あなたのターンです！")

    async def update(self, status=""):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = f"{card_to_str(self.d_hand[0])} , ❓"
        txt = f"🃏 **Blackjack** (賭け金:{self.bet})\nディーラー: {d_str}\nあなた ({calc_score(self.p_hand)}点): {p_str}\n\n{status}"
        await self.msg.edit(content=txt, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, i, b):
        self.can_double = False
        self.p_hand.append(draw_card())
        if calc_score(self.p_hand) > 21:
            await i.response.edit_message(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)", view=None); self.stop()
        else:
            self.update_buttons()
            await i.response.edit_message(view=self); await self.update()

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, i, b):
        await self.stop_game(i)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.success)
    async def double(self, i, b):
        user_points[self.user_id] -= self.bet
        self.bet *= 2
        self.p_hand.append(draw_card())
        await self.stop_game(i)

    def update_buttons(self):
        self.children[2].disabled = not self.can_double

    async def stop_game(self, i):
        while calc_score(self.d_hand) < 17: self.d_hand.append(draw_card())
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand)
        if d_sc > 21 or p_sc > d_sc: user_points[self.user_id] += (self.bet * 2); res = "🎉 **勝ち！**"
        elif p_sc == d_sc: user_points[self.user_id] += self.bet; res = "🤝 **引き分け**"
        else: res = "💀 **負け...**"
        save_json(DATA_FILE, user_points)
        await i.response.edit_message(content=f"─ 結果: {res} ─\nあなた: {p_sc}点 / ディーラー: {d_sc}点", view=None); self.stop()

class DiceView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet; self.user_id = str(user_id); self.msg = msg
    @discord.ui.button(label="振る！", style=discord.ButtonStyle.success)
    async def roll(self, i, b):
        b.disabled = True; d_n, my_n = random.randint(1,6), random.randint(1,6)
        dice_map = {1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅'}
        res = "💀 負け..."
        if my_n > d_n: user_points[self.user_id] += (self.bet * 2); res = "🎉 勝ち！"
        elif my_n == d_n: user_points[self.user_id] += self.bet; res = "🤝 引き分け"
        save_json(DATA_FILE, user_points)
        await i.response.edit_message(content=f"🎲 **ガチンコサイコロ勝負！**\nディーラー: {dice_map[d_n]} vs あなた: {dice_map[my_n]}\n結果: {res}", view=None)

# ─── コマンド ───
async def get_bet(ctx):
    await ctx.send("💸 **賭け金を入力してね！**")
    try:
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content)
        user_id = str(ctx.author.id)
        if bet <= 0 or user_points.get(user_id, 0) < bet: return None
        user_points[user_id] -= bet
        save_json(DATA_FILE, user_points)
        return bet
    except: return None

@bot.command()
async def slot(ctx):
    bet = await get_bet(ctx)
    if not bet: await ctx.send("❌ 不正な額か所持金不足です。"); return
    msg = await ctx.send("🎰 準備中..."); await msg.edit(view=SlotView(bet, ctx.author.id, msg))

@bot.command()
async def blackjack(ctx):
    bet = await get_bet(ctx)
    if not bet: await ctx.send("❌ 不正な額か所持金不足です。"); return
    msg = await ctx.send("🃏 準備中..."); v = BJView(bet, ctx.author.id, msg); await msg.edit(view=v); await v.start_game()

@bot.command()
async def dice(ctx):
    bet = await get_bet(ctx)
    if not bet: await ctx.send("❌ 不正な額か所持金不足です。"); return
    msg = await ctx.send("🎲 準備中..."); await msg.edit(view=DiceView(bet, ctx.author.id, msg))

bot.run(os.getenv('TOKEN'))
