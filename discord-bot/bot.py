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
        """回転中も現在の状況を表示し続けるアニメーション"""
        self.clear_items()
        
        for _ in range(5):
            temp_n = random.randint(1, 6)
            d_str = " ".join([self.dice_map[n] for n in self.d_dice])
            p_str = " ".join([self.dice_map[n] for n in self.p_dice])
            
            # ディーラーが振っているときはディーラーの欄で数字が回るようにする
            if is_dealer:
                content = (f"🎲 **ガチンコサイコロ勝負！**\n"
                           f"ディーラー: {d_str} {self.dice_map[temp_n]} ({temp_n})\n"
                           f"あなた: {p_str}\n\n🎲 **{label}**")
            else:
                content = (f"🎲 **ガチンコサイコロ勝負！**\n"
                           f"ディーラー: {d_str}\n"
                           f"あなた: {p_str} {self.dice_map[temp_n]} ({temp_n})\n\n🎲 **{label}**")
            
            await self.msg.edit(content=content, view=self)
            await asyncio.sleep(0.3)
        return random.randint(1, 6)

    async def start_dice(self):
        # ディーラーのターン（is_dealer=True）
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
        # プレイヤーのターン（is_dealer=False）
        count = len(self.p_dice) + 1
        n = await self.roll_animation(f"あなた：{count}つ目を振っています...", False)
        self.p_dice.append(n)
        
        if len(self.p_dice) == 2:
            d_sum, p_sum = sum(self.d_dice), sum(self.p_dice)
            res = "🤝 引き分け"
            if p_sum > d_sum: 
                user_points[self.user_id] += (self.bet * 2); res = "🎉 勝ち！"
            elif p_sum < d_sum: 
                res = "💀 負け..."
            else:
                user_points[self.user_id] += self.bet
            
            save_json(DATA_FILE, user_points)
            d_str = " ".join([self.dice_map[n] for n in self.d_dice])
            p_str = " ".join([self.dice_map[n] for n in self.p_dice])
            await i.response.edit_message(content=f"🎲 **結果発表！**\nディーラー: {d_str} (合計{d_sum})\nあなた: {p_str} (合計{p_sum})\n\n{res}", view=None)
            self.stop()
        else:
            await self.update_view("1つ目が確定しました！")
            await i.response.defer()
