import discord
from discord.ext import commands
import random
import asyncio
import json
import os
from flask import Flask
from threading import Thread

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

def load_points():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_points(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_points = load_points()

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

# ─── 🎰 スロット ───
SLOT_EMOJIS = ['🎰', '💎', '🔔', '🍒', '🍋', '🍇']
class SlotView(discord.ui.View):
    def __init__(self, ctx, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet; self.user_id = str(user_id); self.msg = msg
        self.final_grid = [[random.choice(SLOT_EMOJIS) for _ in range(3)] for _ in range(3)]
        self.stopped = [False, False, False]; self.is_spinning = True
        self.bg_task = asyncio.create_task(self.spin_animation())

    async def spin_animation(self):
        try:
            while self.is_spinning:
                grid = [[random.choice(SLOT_EMOJIS) if not self.stopped[c] else self.final_grid[r][c] for c in range(3)] for r in range(3)]
                display = "\n".join([f"  [ {row[0]} | {row[1]} | {row[2]} ]" for row in grid])
                await self.msg.edit(content=f"🎰 **闇の3×3スロット** 🎰\n賭け金: {self.bet}\n\n{display}\n\n⏳ 狙ってボタンで止めて！", view=self)
                await asyncio.sleep(0.3)
        except: pass

    async def check_finish(self, interaction):
        if all(self.stopped):
            self.is_spinning = False; self.bg_task.cancel(); self.stop()
            win = sum([1 for r in range(3) if self.final_grid[r][0] == self.final_grid[r][1] == self.final_grid[r][2]])
            res = f"💀 **結果: はずれ**\n賭け金は没収です...\n\n{''.join(['['+'|'.join(r)+']\n' for r in self.final_grid])}"
            if win > 0:
                p = self.bet * (win * 5)
                user_points[self.user_id] = user_points.get(self.user_id, 0) + p
                res = f"🎉 **結果: {win}ライン当選！**\n{p}コイン獲得！\n\n{''.join(['['+'|'.join(r)+']\n' for r in self.final_grid])}"
            save_points(user_points)
            await interaction.response.edit_message(content=res, view=None)

    @discord.ui.button(label="左停止", style=discord.ButtonStyle.primary)
    async def b1(self, i, b): self.stopped[0]=True; b.disabled=True; await i.response.edit_message(view=self); await self.check_finish(i)
    @discord.ui.button(label="中停止", style=discord.ButtonStyle.primary)
    async def b2(self, i, b): 
        if not self.stopped[0]: await i.response.send_message("左から！", ephemeral=True); return
        self.stopped[1]=True; b.disabled=True; await i.response.edit_message(view=self); await self.check_finish(i)
    @discord.ui.button(label="右停止", style=discord.ButtonStyle.primary)
    async def b3(self, i, b):
        if not self.stopped[1]: await i.response.send_message("中から！", ephemeral=True); return
        self.stopped[2]=True; b.disabled=True; await self.check_finish(i)

# ─── 🃏 ブラックジャック ───
class BJView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet; self.user_id = str(user_id); self.msg = msg
        self.p_hand = [draw_card(), draw_card()]; self.d_hand = [draw_card(), draw_card()]
    
    async def update(self, i=None):
        p_str = " , ".join([card_to_str(c) for c in self.p_hand])
        d_str = f"{card_to_str(self.d_hand[0])} , ?"
        txt = f"🃏 **闇のブラックジャック** (賭け金:{self.bet})\n\nディーラー: {d_str}\nあなた ({calc_score(self.p_hand)}): {p_str}"
        if i: await i.response.edit_message(content=txt, view=self)
        else: await self.msg.edit(content=txt, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, i, b):
        self.p_hand.append(draw_card())
        if calc_score(self.p_hand) > 21:
            await i.response.edit_message(content=f"💀 **バースト！**\n合計: {calc_score(self.p_hand)}\n手札: {', '.join([card_to_str(c) for c in self.p_hand])}\n賭け金は没収です...", view=None)
            self.stop()
        else: await self.update(i)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, i, b):
        while calc_score(self.d_hand) < 17: self.d_hand.append(draw_card())
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand)
        p_str = " , ".join([card_to_str(c) for c in self.p_hand])
        d_str = " , ".join([card_to_str(c) for c in self.d_hand])
        res_msg = "負け..."
        desc = f"残念！賭け金は没収です。"
        if d_sc > 21 or p_sc > d_sc: 
            res_msg = "勝ち！"; user_points[self.user_id] = user_points.get(self.user_id,0) + self.bet * 2; desc = f"{self.bet*2}コイン獲得！"
        elif p_sc == d_sc: 
            res_msg = "引き分け"; user_points[self.user_id] = user_points.get(self.user_id,0) + self.bet; desc = f"{self.bet}コインが返却されました。"
        save_points(user_points)
        result_text = f"─ 闇のブラックジャック 結果 ─\nディーラーの手札 (合計: {d_sc}):\n➔ {d_str}\n\nあなたの手札 (合計: {p_sc}):\n➔ {p_str}\n\n【 {res_msg} 】\n{desc}\n（現在の所持金: {user_points.get(self.user_id, 0)} コイン）"
        await i.response.edit_message(content=result_text, view=None)
        self.stop()

# ─── 🎲 サイコロ (演出強化版) ───
class DiceView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet; self.user_id = str(user_id); self.msg = msg
    
    @discord.ui.button(label="サイコロを振る！", style=discord.ButtonStyle.success)
    async def roll(self, i, b):
        b.disabled = True
        dice_map = {1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅'}
        d_n = random.randint(1,6)
        my_n = random.randint(1,6)

        # 1. 最初に「反応しました」と伝える
        await i.response.edit_message(content="🎲 ガチンコサイコロ勝負開始！", view=self)

        # 2. ディーラー回転演出
        for _ in range(10):
            await i.edit_original_response(content=f"🎲 ガチンコサイコロ勝負！\nディーラー: {dice_map[random.randint(1,6)]} ...回転中\nあなた: 待機中")
            await asyncio.sleep(0.1)
        
        # 3. ディーラー確定
        await i.edit_original_response(content=f"🎲 ガチンコサイコロ勝負！\nディーラー: 【 {dice_map[d_n]} 】\nあなた: ロール中...")
        await asyncio.sleep(1.0)

        # 4. 自分回転演出
        for _ in range(10):
            await i.edit_original_response(content=f"🎲 ガチンコサイコロ勝負！\nディーラー: 【 {dice_map[d_n]} 】\nあなた: {dice_map[random.randint(1,6)]} ...回転中")
            await asyncio.sleep(0.1)
        
        # 5. 結果表示
        res_msg = "負け"
        desc = "残念！賭け金は没収です。"
        if my_n > d_n: res_msg="勝ち！"; user_points[self.user_id] = user_points.get(self.user_id,0) + self.bet * 2; desc = f"{self.bet*2}コイン獲得！"
        elif my_n == d_n: res_msg="引き分け"; user_points[self.user_id] = user_points.get(self.user_id,0) + self.bet; desc = f"{self.bet}コインが返却されました。"
        save_points(user_points)
        
        res = f"─ ガチンコサイコロ勝負 結果 ─\nディーラーの出目: 【 {dice_map[d_n]} 】\nあなたの出目: 【 {dice_map[my_n]} 】\n\n【 {res_msg} 】\n{desc}\n（現在の所持金: {user_points.get(self.user_id, 0)} コイン）"
        await i.edit_original_response(content=res, view=None)

# ─── コマンド ───
@bot.command()
async def slot(ctx):
    try:
        await ctx.send("賭け金を入力してね！")
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content)
        user_points[str(ctx.author.id)] = user_points.get(str(ctx.author.id), 0) - bet
        msg = await ctx.send("準備中...")
        await msg.edit(view=SlotView(ctx, bet, ctx.author.id, msg))
    except: await ctx.send("エラーです。")

@bot.command()
async def blackjack(ctx):
    try:
        await ctx.send("賭け金を入力してね！")
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content)
        user_points[str(ctx.author.id)] = user_points.get(str(ctx.author.id), 0) - bet
        msg = await ctx.send("準備中...")
        v = BJView(bet, ctx.author.id, msg)
        await msg.edit(view=v); await v.update()
    except: await ctx.send("エラーです。")

@bot.command()
async def dice(ctx):
    try:
        await ctx.send("賭け金を入力してね！")
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content)
        user_points[str(ctx.author.id)] = user_points.get(str(ctx.author.id), 0) - bet
        msg = await ctx.send("準備中...")
        await msg.edit(view=DiceView(bet, ctx.author.id, msg))
    except: await ctx.send("エラーです。")

TOKEN = os.getenv('TOKEN')
bot.run(TOKEN)