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
        try:
            self.p_hand = []
            self.d_hand = []
            # カードを2枚ずつ配る
            for _ in range(2):
                # プレイヤーのカード
                self.p_hand.append(draw_card())
                await asyncio.sleep(0.5)
                # ディーラーのカード
                self.d_hand.append(draw_card())
                await asyncio.sleep(0.5)
                
                p_str = ", ".join([card_to_str(c) for c in self.p_hand])
                d_str = f"{card_to_str(self.d_hand[0])} , ❓"
                await self.msg.edit(content=f"🃏 **Blackjack (賭け金:{self.bet})**\nカードを配っています... 🎴\nディーラー: {d_str}\nあなた: {p_str}")
            
            await self.update("あなたのターンです！")
        except Exception as e:
            print(f"Error in start_game: {e}")
            await self.msg.edit(content="⚠️ エラーが発生したためゲームを中断します。")

    async def update(self, status=""):
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = f"{card_to_str(self.d_hand[0])} , ❓"
        self.clear_items()
        
        hit_btn = discord.ui.Button(label="Hit", style=discord.ButtonStyle.primary)
        hit_btn.callback = self.hit
        self.add_item(hit_btn)
        
        stand_btn = discord.ui.Button(label="Stand", style=discord.ButtonStyle.secondary)
        stand_btn.callback = self.stand
        self.add_item(stand_btn)
        
        if self.can_double:
            double_btn = discord.ui.Button(label="Double", style=discord.ButtonStyle.success)
            double_btn.callback = self.double
            self.add_item(double_btn)
        
        await self.msg.edit(content=f"🃏 **Blackjack**\nディーラー: {d_str}\nあなた ({calc_score(self.p_hand)}点): {p_str}\n\n{status}", view=self)

    async def hit(self, i: discord.Interaction):
        self.can_double = False
        await i.response.edit_message(content="🃏 カードを引いています...", view=None)
        await asyncio.sleep(1.0)
        self.p_hand.append(draw_card())
        if calc_score(self.p_hand) > 21:
            await self.finish_game("💀 **バースト！負けました...**", -self.bet)
        else: await self.update()

    async def stand(self, i: discord.Interaction):
        await i.response.edit_message(content="🃏 ディーラーのターンです...", view=None)
        await self.dealer_turn()

    async def double(self, i: discord.Interaction):
        data = get_user_data(self.user_id)
        if data["points"] < self.bet: 
            await i.response.send_message("❌ 所持金不足！", ephemeral=True)
            return
        data["points"] -= self.bet
        save_user_data(self.user_id, data)
        self.bet *= 2
        
        await i.response.edit_message(content="🃏 ダブルダウン！カードを1枚引きます...", view=None)
        await asyncio.sleep(1.0)
        self.p_hand.append(draw_card())
        
        if calc_score(self.p_hand) > 21:
            await self.finish_game("💀 **バースト！負けました...**", -self.bet)
        else: await self.dealer_turn()

    async def dealer_turn(self):
        while calc_score(self.d_hand) < 17:
            await asyncio.sleep(1.2)
            self.d_hand.append(draw_card())
            d_str = ", ".join([card_to_str(c) for c in self.d_hand])
            await self.msg.edit(content=f"🃏 ディーラーが引いています...\nディーラー: {d_str} ({calc_score(self.d_hand)}点)")
        
        d_sc, p_sc = calc_score(self.d_hand), calc_score(self.p_hand)
        if d_sc > 21 or p_sc > d_sc: await self.finish_game(f"🎉 **あなたの勝ち！ (+{self.bet}コイン利益)**", self.bet * 2)
        elif p_sc == d_sc: await self.finish_game(f"🤝 **引き分け (返金)**", self.bet)
        else: await self.finish_game(f"💀 **負けました... (-{self.bet}コイン)**", 0)

    async def finish_game(self, result_text, payout):
        data = get_user_data(self.user_id)
        if payout > 0: data["points"] += payout
        save_user_data(self.user_id, data)
        p_str = ", ".join([card_to_str(c) for c in self.p_hand])
        d_str = ", ".join([card_to_str(c) for c in self.d_hand])
        final_msg = f"{result_text}\n\nあなた: {p_str} ({calc_score(self.p_hand)}点)\nディーラー: {d_str} ({calc_score(self.d_hand)}点)\n💳 所持金: {data['points']}コイン"
        await self.msg.edit(content=final_msg, view=None)
        self.stop()
