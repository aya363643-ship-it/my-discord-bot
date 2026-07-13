import discord
from discord.ext import commands, tasks
import random
import asyncio
import os
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
from pymongo import MongoClient

# ─── MongoDB設定 ───
MONGO_URI = "mongodb+srv://baketan373_db_user:15351348650Ad@cluster0.misxalm.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
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
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# ─── コマンド ───
@bot.command()
async def daily(ctx):
    data = get_user_data(ctx.author.id)
    now = datetime.now()
    
    # 24時間経過チェック
    if data.get("last_daily"):
        last_claimed = datetime.fromisoformat(data["last_daily"])
        diff = (now - last_claimed).total_seconds()
        if diff < 86400:
            remaining = int((86400 - diff) // 3600)
            await ctx.send(f"⏳ まだだよ！あと約 {remaining} 時間待ってね。")
            return

    amount = random.randint(100, 500)
    data["points"] += amount
    data["last_daily"] = now.isoformat()
    save_user_data(ctx.author.id, data)
    await ctx.send(f"🎉 デイリーボーナス！💰 +{amount}コイン (現在の所持金: {data['points']})")

@bot.command()
async def points(ctx):
    data = get_user_data(ctx.author.id)
    await ctx.send(f"💰 あなたの所持金は {data['points']} コインです。")

# ─── ゲーム用ヘルパー (MongoDB対応) ───
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
            data = get_user_data(self.user_id)
            if win > 0:
                p = self.bet * (win * 10)
                data["points"] += p
                save_user_data(self.user_id, data)
                res = f"🎉 **大勝利！{win}ライン的中！**\n💰 **{p}コイン獲得！** (所持金: {data['points']})"
            else: 
                res = f"💀 **残念！はずれ！** (所持金: {data['points']})"
            
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
        self.bet = bet
        self.user_id = str(user_id)
        self.msg = msg
        self.p_hand = []
        self.d_hand = []
        self.can_double = True

    async def start_game(self):
        await self.msg.edit(content=f"🃏 **Blackjack (賭け金:{self.bet})**\nカードを配っています...", view=None)
        for i in range(2):
            await asyncio.sleep(0.8)
            self.p_hand.append(draw_card())
            await self.msg.edit(content=f"🃏 **Blackjack** (賭け金:{self.bet})\nカードを配っています...\nあなた: {', '.join([card_to_str(c) for c in self.p_hand])}")
            await asyncio.sleep(0.8)
            self.d_hand.append(draw_card())
            d_str = f"{card_to_str(self.d_hand[0])} , ❓"
            await self.msg.edit(content=f"🃏 **Blackjack** (賭け金:{self.bet})\nディーラー: {d_str}\nあなた: {', '.join([card_to_str(c) for c in self.p_hand])}")
        await self.update("あなたのターンです！")

    async def update(self, status=""):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = f"{card_to_str(self.d_hand[0])} , ❓"
        txt = f"🃏 **Blackjack** (賭け金:{self.bet})\nディーラー: {d_str}\nあなた ({calc_score(self.p_hand)}点): {p_str}\n\n{status}"
        
        self.clear_items()
        self.add_item(discord.ui.Button(label="Hit", style=discord.ButtonStyle.primary, custom_id="hit"))
        self.add_item(discord.ui.Button(label="Stand", style=discord.ButtonStyle.secondary, custom_id="stand"))
        if self.can_double:
            self.add_item(discord.ui.Button(label="Double", style=discord.ButtonStyle.success, custom_id="double"))
        
        self.children[0].callback = self.hit
        self.children[1].callback = self.stand
        if self.can_double:
            self.children[2].callback = self.double
            
        await self.msg.edit(content=txt, view=self)

    async def hit(self, i: discord.Interaction):
        self.can_double = False
        card = draw_card()
        self.p_hand.append(card)
        await i.response.edit_message(content=f"🃏 カードを引いています...\n新しく出たカード: {card_to_str(card)}", view=None)
        await asyncio.sleep(1)
        if calc_score(self.p_hand) > 21:
            data = get_user_data(self.user_id)
            await i.edit_original_response(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)\n💰 現在の所持金: {data['points']}コイン", view=None)
            self.stop()
        else:
            await self.update()

    async def stand(self, i: discord.Interaction):
        await i.response.defer()
        await self.stop_game(i)

    async def double(self, i: discord.Interaction):
        data = get_user_data(self.user_id)
        if data["points"] < self.bet:
            await i.response.edit_message(content="❌ 所持金不足でダブルダウンできません！", view=None)
            self.stop()
            return
        
        data["points"] -= self.bet
        save_user_data(self.user_id, data)
        self.bet *= 2
        card = draw_card()
        self.p_hand.append(card)
        
        # ダブルダウン後のカード表示を明確にする
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        await i.response.edit_message(content=f"🔥 **ダブルダウン！**\n引いたカード: {card_to_str(card)}\n現在のあなたの手札: {p_str}", view=None)
        await asyncio.sleep(1)
        
        if calc_score(self.p_hand) > 21:
            data = get_user_data(self.user_id)
            await i.edit_original_response(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)\n💰 現在の所持金: {data['points']}コイン", view=None)
            self.stop()
        else:
            await self.stop_game(i)

    async def stop_game(self, i: discord.Interaction):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        await i.edit_original_response(content=f"🃏 **ディーラーの番です...**\nあなたの全カード: {p_str}", view=None)
        
        while calc_score(self.d_hand) < 17:
            await asyncio.sleep(1)
            self.d_hand.append(draw_card())
            d_str = ", ".join([card_to_str(c) for c in self.d_hand])
            await i.edit_original_response(content=f"🃏 **ディーラードロー中...**\nディーラー: {d_str}\nあなた: {p_str}")
        
        await i.edit_original_response(content=f"🃏 **ディーラーの全カード確定**\n結果を集計しています...")
        await asyncio.sleep(3)
        
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand)
        data = get_user_data(self.user_id)

        if d_sc > 21 or p_sc > d_sc: 
            data["points"] += (self.bet * 2); res = "🎉 **勝ち！**"
        elif p_sc == d_sc: 
            data["points"] += self.bet; res = "🤝 **引き分け**"
        else: 
            res = "💀 **負け...**"
        
        save_user_data(self.user_id, data)
        await i.edit_original_response(
            content=f"─ 結果: {res} ─\n\n"
                    f"👤 あなたの全カード: {', '.join([card_to_str(c) for c in self.p_hand])} ({p_sc}点)\n"
                    f"🤖 ディーラーの全カード: {', '.join([card_to_str(c) for c in self.d_hand])} ({d_sc}点)\n\n"
                    f"💰 **現在の所持金: {data['points']}コイン**", 
            view=None
        )
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

    async def roll_animation(self, label, is_dealer):
        self.clear_items()
        for _ in range(5):
            temp_n = random.randint(1, 6)
            d_str = " ".join([self.dice_map[n] for n in self.d_dice])
            p_str = " ".join([self.dice_map[n] for n in self.p_dice])
            
            if is_dealer:
                content = (f"🎲 **ガチンコサイコロ勝負！**\n"
                           f"ディーラー: {d_str} {self.dice_map[temp_n]} ({temp_n})\n"
                           f"あなた: {p_str}\n\n"
                           f"🎲 **{label}**")
            else:
                content = (f"🎲 **ガチンコサイコロ勝負！**\n"
                           f"ディーラー: {d_str}\n"
                           f"あなた: {p_str} {self.dice_map[temp_n]} ({temp_n})\n\n"
                           f"🎲 **{label}**")
            
            await self.msg.edit(content=content, view=self)
            await asyncio.sleep(0.3)
        return random.randint(1, 6)

    async def start_dice(self):
        d1 = await self.roll_animation("ディーラー：1つ目を振っています...", True)
        self.d_dice.append(d1)
        d2 = await self.roll_animation("ディーラー：2つ目を振っています...", True)
        self.d_dice.append(d2)
        await self.update_view("ディーラーのサイコロが出揃いました！")

    async def update_view(self, status):
        d_str = " ".join([self.dice_map[n] for n in self.d_dice])
        p_str = " ".join([self.dice_map[n] for n in self.p_dice])
        count_p = len(self.p_dice) + 1
        
        content = (f"🎲 **ガチンコサイコロ勝負！**\n"
                   f"ディーラー: {d_str}\n"
                   f"あなた: {p_str}\n\n"
                   f"【状態】: {status}\n"
                   f"※次はあなたの **{count_p}つ目** です！")
        
        self.clear_items()
        self.add_item(discord.ui.Button(label=f"{count_p}つ目を振る！", style=discord.ButtonStyle.success, custom_id="roll"))
        self.children[0].callback = self.roll
        await self.msg.edit(content=content, view=self)

    async def roll(self, i: discord.Interaction):
        count = len(self.p_dice) + 1
        n = await self.roll_animation(f"あなた：{count}つ目を振っています...", False)
        self.p_dice.append(n)
        
        if len(self.p_dice) == 2:
            d_sum, p_sum = sum(self.d_dice), sum(self.p_dice)
            res = "🤝 引き分け"
            
            data = get_user_data(self.user_id)
            if p_sum > d_sum: 
                data["points"] += (self.bet * 2); res = "🎉 勝ち！"
            elif p_sum < d_sum: 
                res = "💀 負け..."
            else:
                data["points"] += self.bet
            
            save_user_data(self.user_id, data)
            
            d_str = " ".join([self.dice_map[n] for n in self.d_dice])
            p_str = " ".join([self.dice_map[n] for n in self.p_dice])
            await i.response.edit_message(content=f"🎲 **結果発表！**\nディーラー: {d_str} (合計{d_sum})\nあなた: {p_str} (合計{p_sum})\n\n{res}\n💰 所持金: {data['points']}コイン", view=None)
            self.stop()
        else:
            await self.update_view("1つ目が確定しました！")
            await i.response.defer()

# ─── コマンド (ゲーム開始と賭け金処理) ───
async def get_bet(ctx):
    await ctx.send("💸 **賭け金を入力してね！**")
    try:
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content)
        user_id = str(ctx.author.id)
        
        data = get_user_data(user_id)
        if bet <= 0 or data["points"] < bet: return None
        
        # 賭け金を引いてMongoDBに保存
        data["points"] -= bet
        save_user_data(user_id, data)
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
    msg = await ctx.send("🎲 準備中..."); view = DiceView(bet, ctx.author.id, msg)
    await msg.edit(view=view); await view.start_dice()

bot.run(os.getenv('TOKEN'))
