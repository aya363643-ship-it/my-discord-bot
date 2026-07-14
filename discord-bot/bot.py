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

# ─── 告知用チャンネルの設定 ───
ANNOUNCEMENT_CHANNEL_ID = 1526095284357173358

# ─── 💡 特定の人のみ許可する設定 ───
ALLOWED_USERS = [825679340209438820, 872839459740192768]

# 特定の人かどうかを判定するカスタムチェック
def is_allowed_user():
    async def predicate(ctx):
        if ctx.author.id in ALLOWED_USERS:
            return True
        await ctx.send("❌ このコマンドを実行する権限がありません！")
        return False
    return commands.check(predicate)

# ─── VC報酬用のデータ保持 ───
vc_durations = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    if not check_vc_rewards.is_running():
        check_vc_rewards.start()

# ─── VC滞在をチェックする定期タスク (1分ごとに実行) ───
@tasks.loop(minutes=1)
async def check_vc_rewards():
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                if member.bot:
                    continue

                user_id = member.id
                if user_id not in vc_durations:
                    vc_durations[user_id] = 0
                
                # 1分経過したのでカウントアップ
                vc_durations[user_id] += 1
                
                # 30分経過したかの判定
                if vc_durations[user_id] >= 30:
                    vc_durations[user_id] = 0 # リセット
                    try:
                        data = get_user_data(user_id)
                        data["points"] += 50 # 50コイン付与
                        save_user_data(user_id, data)
                        
                        channel = bot.get_channel(ANNOUNCEMENT_CHANNEL_ID)
                        if channel:
                            await channel.send(f"🎙️ {member.mention} がボイスチャンネルに30分滞在したため、💰 **50コイン** を獲得しました！ (現在の所持金: {data['points']})")
                    except Exception as e:
                        print(f"VC報酬付与エラー: {e}")

# ─── VCの入退室を検知するイベント ───
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    if before.channel and not after.channel:
        if member.id in vc_durations:
            del vc_durations[member.id]

# ─── 管理者専用コマンド ───
@bot.command()
@is_allowed_user()
async def give_points(ctx, member: discord.Member, amount: int):
    """【管理者専用】特定のユーザーにコインを付与する"""
    try:
        data = get_user_data(member.id)
        data["points"] += amount
        save_user_data(member.id, data)
        await ctx.send(f"👑 管理者権限: {member.mention} に 💰 **{amount}コイン** を付与しました！ (現在の所持金: {data['points']})")
    except Exception as e:
        await ctx.send(f"❌ データの更新に失敗しました: `{e}`")

@bot.command()
@is_allowed_user()
async def reset_points(ctx, member: discord.Member):
    """【管理者専用】特定のユーザーのコインを0にする"""
    try:
        data = get_user_data(member.id)
        data["points"] = 0
        save_user_data(member.id, data)
        await ctx.send(f"👑 管理者権限: {member.mention} の所持コインを **0** にリセットしました！")
    except Exception as e:
        await ctx.send(f"❌ データの更新に失敗しました: `{e}`")

# ─── 一般コマンド ───
@bot.command()
async def daily(ctx):
    try:
        data = get_user_data(ctx.author.id)
    except Exception as e:
        await ctx.send(f"❌ データベースへの接続に失敗しました。\nエラー詳細: `{e}`")
        return

    now = datetime.now()
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
    
    try:
        save_user_data(ctx.author.id, data)
    except Exception as e:
        await ctx.send(f"❌ データの保存に失敗しました: `{e}`")
        return
        
    await ctx.send(f"🎉 デイリーボーナス！💰 +{amount}コイン (現在の所持金: {data['points']})")

@bot.command()
async def points(ctx):
    try:
        data = get_user_data(ctx.author.id)
        await ctx.send(f"💰 あなたの所持金は {data['points']} コインです。")
    except Exception as e:
        await ctx.send(f"❌ 所持金の取得に失敗しました: `{e}`")

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

# ─── 各ゲームクラス ───
# ─── スロット用追加データ（グローバル） ───
slot_data = {}

# ─── スロット用データ ───
slot_data = {}

class SlotView(discord.ui.View):
    def __init__(self, bet, user_id, msg):
        super().__init__(timeout=300.0)
        self.bet = bet
        self.user_id = str(user_id)
        self.msg = msg
        
        if self.user_id not in slot_data:
            slot_data[self.user_id] = {"jackpot_until": 0}
            
        self.is_jackpot = time.time() < slot_data[self.user_id]["jackpot_until"]
        self.icons = ['🎰', '💎', '🔔', '🍒', '🍋', '🍇', '✨', '🍀']
        self.final_grid = self.generate_result()
        
        self.btn_spin = discord.ui.Button(label="レバーを叩く！", style=discord.ButtonStyle.success, emoji="🕹️")
        self.btn_spin.callback = self.start_spin
        self.add_item(self.btn_spin)

    def generate_result(self):
        # ...（生成ロジックはそのまま）...
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
        await interaction.response.defer()
        
        # 1. 回転演出（3回更新）
        for _ in range(3):
            temp_grid = [[random.choice(self.icons) for _ in range(3)] for _ in range(3)]
            grid_str = "\n".join([" | ".join(row) for row in temp_grid])
            embed = discord.Embed(title="🎰 スロット回転中...", description=f"{grid_str}", color=0x3498db)
            await self.msg.edit(embed=embed)
            await asyncio.sleep(0.5)
        
        # 2. 1秒待機してから結果表示
        await asyncio.sleep(1)
        await self.show_result()

    async def show_result(self):
        lines = self.check_win(self.final_grid)
        mult = 1.0
        if '🎰' in lines: mult = 7.0
        elif '💎' in lines: mult = 3.0
        elif '✨' in lines: mult = 2.0
        elif '🍇' in lines: mult = 1.5
        elif '🍒' in lines: mult = 1.2

        res_text = "残念！はずれ！"
        if mult > 1.0:
            win = int(self.bet * mult)
            data = get_user_data(self.user_id)
            data["points"] += win
            save_user_data(self.user_id, data)
            res_text = f"🎉 {mult}倍的中！ {win}コイン獲得！"
            
            if mult == 7.0 and not self.is_jackpot:
                slot_data[self.user_id]["jackpot_until"] = time.time() + 10
                res_text += "\n🚨 **JACKPOTモード突入！**"

        grid_str = "\n".join([" | ".join(row) for row in self.final_grid])
        embed = discord.Embed(title="🎰 結果発表", description=f"{grid_str}\n\n{res_text}", color=0xf1c40f)
        await self.msg.edit(embed=embed)

    def check_win(self, grid):
        lines = []
        for r in range(3):
            if grid[r][0] == grid[r][1] == grid[r][2]: lines.append(grid[r][0])
        if grid[0][0] == grid[1][1] == grid[2][2]: lines.append(grid[0][0])
        if grid[0][2] == grid[1][1] == grid[2][0]: lines.append(grid[0][2])
        return lines

    async def start_spin(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🎰 スロット演出中", description="ぐるぐる...ぐるぐる...", color=0x3498db)
        await self.msg.edit(embed=embed, view=None)
        
        await asyncio.sleep(1.5)
        # 演出省略：最終結果を表示
        await self.show_result()

    async def show_result(self):
        lines = self.check_win(self.final_grid)
        mult = 1.0
        if '🎰' in lines: mult = 7.0
        elif '💎' in lines: mult = 3.0
        elif '✨' in lines: mult = 2.0
        elif '🍇' in lines: mult = 1.5
        elif '🍒' in lines: mult = 1.2

        res_text = "残念！はずれ！"
        if mult > 1.0:
            win = int(self.bet * mult)
            data = get_user_data(self.user_id)
            data["points"] += win
            save_user_data(self.user_id, data)
            res_text = f"🎉 {mult}倍的中！ {win}コイン獲得！"
            
            # ジャックポット判定（7が揃ったら）
            if mult == 7.0 and not self.is_jackpot:
                slot_data[self.user_id]["jackpot_until"] = time.time() + 10
                res_text += "\n🚨 **JACKPOTモード突入！**"

        grid_str = "\n".join([" | ".join(row) for row in self.final_grid])
        embed = discord.Embed(title="🎰 結果発表", description=f"{grid_str}\n\n{res_text}", color=0xf1c40f)
        await self.msg.edit(embed=embed)

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
            try:
                data = get_user_data(self.user_id)
                await i.edit_original_response(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)\n💰 現在の所持金: {data['points']}コイン", view=None)
            except:
                await i.edit_original_response(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)\n❌ 所持金の取得失敗", view=None)
            self.stop()
        else:
            await self.update()

    async def stand(self, i: discord.Interaction):
        await i.response.defer()
        await self.stop_game(i)

    async def double(self, i: discord.Interaction):
        try:
            data = get_user_data(self.user_id)
        except Exception as e:
            await i.response.edit_message(content=f"❌ データベースエラー: `{e}`", view=None)
            self.stop()
            return

        if data["points"] < self.bet:
            await i.response.edit_message(content="❌ 所持金不足でダブルダウンできません！", view=None)
            self.stop()
            return
        
        data["points"] -= self.bet
        try:
            save_user_data(self.user_id, data)
        except Exception as e:
            await i.response.edit_message(content=f"❌ データの保存失敗: `{e}`", view=None)
            self.stop()
            return

        self.bet *= 2
        card = draw_card()
        self.p_hand.append(card)
        
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        await i.response.edit_message(content=f"🔥 **ダブルダウン！**\n引いたカード: {card_to_str(card)}\n現在のあなたの手札: {p_str}", view=None)
        await asyncio.sleep(1)
        
        if calc_score(self.p_hand) > 21:
            await i.edit_original_response(content=f"💀 **バースト！** (合計: {calc_score(self.p_hand)}点)\n💰 現在の所持金: {data['points']}コイン", view=None)
            self.stop()
        else:
            await self.stop_game(i)

    async def stop_game(self, i: discord.Interaction):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        await i.edit_original_response(content=f"🃏 **ディーラーの番です...**\nあなたの全カード: {p_str}", view=None)
        
        # ディーラーが引く処理
        while calc_score(self.d_hand) < 17:
            await asyncio.sleep(1.5) # 少し間隔を空けて見やすくする
            self.d_hand.append(draw_card())
            d_str = ", ".join([card_to_str(c) for c in self.d_hand])
            await i.edit_original_response(content=f"🃏 **ディーラードロー中...**\nディーラー: {d_str}\nあなた: {p_str}")
        
        # ここで「最終結果を表示する前の一覧表示」を追加
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand)
        d_str_final = ", ".join([card_to_str(c) for c in self.d_hand])
        
        await i.edit_original_response(
            content=f"🃏 **ディーラーの手札が確定しました！**\n\n"
                    f"👤 あなた: {p_str} ({p_sc}点)\n"
                    f"🤖 ディーラー: {d_str_final} ({d_sc}点)\n\n"
                    f"集計中..."
        )
        await asyncio.sleep(3) # 結果発表前に3秒間見せる
        
        # 最終的な勝敗判定とデータ更新
        try:
            data = get_user_data(self.user_id)
            if d_sc > 21 or p_sc > d_sc: 
                data["points"] += (self.bet * 2); res = "🎉 **勝ち！**"
            elif p_sc == d_sc: 
                data["points"] += self.bet; res = "🤝 **引き分け**"
            else: 
                res = "💀 **負け...**"
            save_user_data(self.user_id, data)
            pts_str = f"{data['points']}コイン"
        except Exception as e:
            res = f"⚠️ 試合終了（データ保存失敗: {e}）"
            pts_str = "エラー"
        
        await i.edit_original_response(
            content=f"─ 結果: {res} ─\n\n"
                    f"👤 あなたの全カード: {p_str} ({p_sc}点)\n"
                    f"🤖 ディーラーの全カード: {d_str_final} ({d_sc}点)\n\n"
                    f"💰 **現在の所持金: {pts_str}**", 
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
        # 💡 タイムアウトを防ぐため、演出アニメーションが始まる前に最優先でdeferを実行します！
        await i.response.defer()
        
        count = len(self.p_dice) + 1
        n = await self.roll_animation(f"あなた：{count}つ目を振っています...", False)
        self.p_dice.append(n)
        
        if len(self.p_dice) == 2:
            d_sum, p_sum = sum(self.d_dice), sum(self.p_dice)
            res = "🤝 引き分け"
            
            try:
                data = get_user_data(self.user_id)
                if p_sum > d_sum: 
                    data["points"] += (self.bet * 2); res = "🎉 勝ち！"
                elif p_sum < d_sum: 
                    res = "💀 負け..."
                else:
                    data["points"] += self.bet
                save_user_data(self.user_id, data)
                pts_str = f"{data['points']}コイン"
            except Exception as e:
                res = f"⚠️ 終了（データ保存失敗: {e}）"
                pts_str = "エラー"
            
            d_str = " ".join([self.dice_map[n] for n in self.d_dice])
            p_str = " ".join([self.dice_map[n] for n in self.p_dice])
            
            # deferした後の最終結果の送信には i.edit_original_response を使用します
            await i.edit_original_response(content=f"🎲 **結果発表！**\nディーラー: {d_str} (合計{d_sum})\nあなた: {p_str} (合計{p_sum})\n\n{res}\n💰 所持金: {pts_str}", view=None)
            self.stop()
        else:
            await self.update_view("1つ目が確定しました！")

# ─── コマンド (ゲーム開始と賭け金処理) ───
async def get_bet(ctx):
    await ctx.send("💸 **賭け金を入力してね！**")
    try:
        m = await bot.wait_for('message', check=lambda x: x.author==ctx.author, timeout=30)
        bet = int(m.content)
        user_id = str(ctx.author.id)
        
        try:
            data = get_user_data(user_id)
        except Exception as e:
            await ctx.send(f"❌ データベースからユーザーデータを取得できませんでした: `{e}`")
            return None

        if bet <= 0 or data["points"] < bet: 
            await ctx.send("❌ 不正な額か、所持金が足りません！")
            return None
        
        data["points"] -= bet
        save_user_data(user_id, data)
        return bet
    except asyncio.TimeoutError:
        await ctx.send("⏱️ 時間切れです。もう一度コマンドを入力してください。")
        return None
    except ValueError:
        await ctx.send("❌ 有効な数値を入力してください。")
        return None
    except Exception as e:
        await ctx.send(f"❌ エラーが発生しました: `{e}`")
        return None

@bot.command()
async def slot(ctx):
    bet = await get_bet(ctx)
    if not bet: return
    msg = await ctx.send("🎰 準備中..."); await msg.edit(view=SlotView(bet, ctx.author.id, msg))

@bot.command()
async def blackjack(ctx):
    bet = await get_bet(ctx)
    if not bet: return
    msg = await ctx.send("🃏 準備中..."); v = BJView(bet, ctx.author.id, msg); await msg.edit(view=v); await v.start_game()

@bot.command()
async def dice(ctx):
    bet = await get_bet(ctx)
    if not bet: return
    msg = await ctx.send("🎲 準備中..."); view = DiceView(bet, ctx.author.id, msg)
    await msg.edit(view=view); await view.start_dice()

bot.run(os.getenv('TOKEN'))
