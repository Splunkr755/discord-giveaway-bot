import discord
from discord import app_commands
import random
import json
import os
import asyncio
import datetime
import re
import traceback
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.invites = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
DATA_FILE = "/data/bot_data.json"
data = {}
invite_cache = {}
last_crystal_time = {}
def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    else:
        data = {"guilds": {}}
def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
def get_guild_data(guild_id):
    gid = str(guild_id)
    if "guilds" not in data:
        data["guilds"] = {}
    if gid not in data["guilds"]:
        data["guilds"][gid] = {
            "tickets": {},
            "role_bonuses": {},
            "role_chance_bonuses": {},
            "ticket_channel": None,
            "excluded_channels": [],
            "gifting_enabled": True,
            "giveaways": {},
            "ticket_chance": 0.25,
            "giveaway_host_role": None,
            "giveaway_blacklist_roles": [],
            "ticket_mod_role": None,
            "shop_items": {},
            "shop_manager_role": None,
            "invite_reward": 0,
            "seen_members": [],
            "daily_chat_reward": {"channel_id": None, "reward": 0, "winners": 3, "time": "18:00", "custom_prize": None, "prize_type": "tickets"},
            "daily_entries": {},
            "crystal_cooldown": 60,
            "chest_manager_role": None,
            "chest_items": {},
            "chest_channel_id": None,
            "special_reward_channel_id": None,
            "crystals": {}
        }
    else:
        gd = data["guilds"][gid]
        if "role_chance_bonuses" not in gd: gd["role_chance_bonuses"] = {}
        if "excluded_channels" not in gd: gd["excluded_channels"] = []
        if "gifting_enabled" not in gd: gd["gifting_enabled"] = True
        if "giveaways" not in gd: gd["giveaways"] = {}
        if "ticket_chance" not in gd: gd["ticket_chance"] = 0.25
        if "giveaway_host_role" not in gd: gd["giveaway_host_role"] = None
        if "giveaway_blacklist_roles" not in gd: gd["giveaway_blacklist_roles"] = []
        if "ticket_mod_role" not in gd: gd["ticket_mod_role"] = None
        if "shop_items" not in gd: gd["shop_items"] = {}
        if "shop_manager_role" not in gd: gd["shop_manager_role"] = None
        if "invite_reward" not in gd: gd["invite_reward"] = 0
        if "seen_members" not in gd: gd["seen_members"] = []
        if "daily_chat_reward" not in gd: gd["daily_chat_reward"] = {"channel_id": None, "reward": 0, "winners": 3, "time": "18:00", "custom_prize": None, "prize_type": "tickets"}
        if "daily_entries" not in gd: gd["daily_entries"] = {}
        if "crystal_cooldown" not in gd: gd["crystal_cooldown"] = 60
        if "chest_manager_role" not in gd: gd["chest_manager_role"] = None
        if "chest_items" not in gd: gd["chest_items"] = {}
        if "chest_channel_id" not in gd: gd["chest_channel_id"] = None
        if "special_reward_channel_id" not in gd: gd["special_reward_channel_id"] = None
        if "crystals" not in gd: gd["crystals"] = {}
    return data["guilds"][gid]
# ====================== VIEWS & MODALS ======================
class TicketEntryModal(discord.ui.Modal, title="🎟️ Enter the Raffle"):
    def __init__(self, giveaway_message_id: str, max_tickets: int):
        super().__init__()
        self.giveaway_message_id = giveaway_message_id
        self.max_tickets = max_tickets
        self.amount = discord.ui.TextInput(
            label="How many tickets to enter?",
            style=discord.TextStyle.short,
            placeholder=f"Max: {max_tickets}",
            required=True,
            max_length=10
        )
        self.add_item(self.amount)
    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild: return
        try:
            amount = int(self.amount.value)
            if amount < 1: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)
            return
        guild_data = get_guild_data(interaction.guild.id)
        message_id = self.giveaway_message_id
        user_id_str = str(interaction.user.id)
        if message_id not in guild_data["giveaways"]:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return
        giveaway = guild_data["giveaways"][message_id]
        current_tickets = guild_data.get("tickets", {}).get(user_id_str, 0)
        if amount > current_tickets:
            await interaction.response.send_message(f"❌ You only have **{current_tickets}** tickets!", ephemeral=True)
            return
        guild_data.setdefault("tickets", {})[user_id_str] = current_tickets - amount
        entries = giveaway.setdefault("entries", {})
        entries[user_id_str] = entries.get(user_id_str, 0) + amount
        save_data()
        try:
            await refresh_giveaway_embed(interaction.message, giveaway)
        except:
            pass
        await interaction.response.send_message(
            f"✅ **You entered with {amount} ticket(s)!**\n"
            f"You now have **{entries[user_id_str]}** entries.\n"
            f"Tickets left: **{current_tickets - amount}**",
            ephemeral=True
        )
class GiveawayEnterView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Enter Raffle", style=discord.ButtonStyle.green, custom_id="giveaway_enter_modal")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild: return
        message_id = str(interaction.message.id)
        guild_data = get_guild_data(interaction.guild.id)
        if message_id not in guild_data["giveaways"]:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return
        current_tickets = guild_data.get("tickets", {}).get(str(interaction.user.id), 0)
        if current_tickets < 1:
            await interaction.response.send_message("❌ You don't have any tickets!", ephemeral=True)
            return
        modal = TicketEntryModal(message_id, current_tickets)
        await interaction.response.send_modal(modal)
class FreeGiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green, custom_id="free_giveaway_enter")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild: return
        message_id = str(interaction.message.id)
        guild_data = get_guild_data(interaction.guild.id)
        if message_id not in guild_data["giveaways"]:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return
        giveaway = guild_data["giveaways"][message_id]
        entries = giveaway.setdefault("entries", {})
        user_id_str = str(interaction.user.id)
        if user_id_str in entries:
            await interaction.response.send_message("❌ You have already entered!", ephemeral=True)
            return
        entries[user_id_str] = 1
        save_data()
        try:
            await refresh_giveaway_embed(interaction.message, giveaway)
        except:
            pass
        await interaction.response.send_message("✅ You have entered the giveaway!", ephemeral=True)
# ====================== CHEST VIEW ======================
class ChestView(discord.ui.View):
    def __init__(self, guild_data):
        super().__init__(timeout=None)
        self.guild_data = guild_data
    @discord.ui.button(label="Open Chest", style=discord.ButtonStyle.green)
    async def open_chest(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_data = get_guild_data(interaction.guild.id)
        user_id = str(interaction.user.id)
        crystals = guild_data["crystals"].get(user_id, 0)
        if not guild_data["chest_items"]:
            await interaction.response.send_message("No chest items available!", ephemeral=True)
            return
        item_name = random.choice(list(guild_data["chest_items"].keys()))
        item = guild_data["chest_items"][item_name]
        cost = item.get("crystal_cost", 50)
        if crystals < cost:
            await interaction.response.send_message(f"❌ You need **{cost}** crystals to open this chest!", ephemeral=True)
            return
        guild_data["crystals"][user_id] = crystals - cost
        save_data()
        rewards = item.get("rewards", [{"type": "crystals", "amount": 100, "chance": 1.0}])
        roll = random.random()
        cumulative = 0
        reward_text = "Nothing"
        for r in rewards:
            cumulative += r["chance"]
            if roll <= cumulative:
                if r["type"] == "tickets":
                    tickets_dict = guild_data.setdefault("tickets", {})
                    tickets_dict[user_id] = tickets_dict.get(user_id, 0) + r["amount"]
                    reward_text = f"**{r['amount']} tickets**"
                elif r["type"] == "crystals":
                    guild_data["crystals"][user_id] = guild_data["crystals"].get(user_id, 0) + r["amount"]
                    reward_text = f"**{r['amount']} crystals**"
                else:
                    reward_text = r.get("prize", "Custom prize")
                break
        save_data()
        await interaction.response.send_message(f"🎉 You opened a chest and got **{reward_text}**!", ephemeral=False)
        if any(r.get("chance", 0) <= 0.001 for r in rewards):
            special_ch = interaction.guild.get_channel(int(guild_data.get("special_reward_channel_id", 0)))
            if special_ch:
                await special_ch.send(f"🌟 **MASSIVE WIN!** {interaction.user.mention} just pulled a **super rare** reward from a chest!")
    @discord.ui.button(label="Check Crystals", style=discord.ButtonStyle.gray)
    async def check_crystals(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_data = get_guild_data(interaction.guild.id)
        crystals = guild_data["crystals"].get(str(interaction.user.id), 0)
        await interaction.response.send_message(f"💎 You currently have **{crystals}** crystals!", ephemeral=True)
# ====================== SHOP PAGINATION VIEW ======================
class ShopView(discord.ui.View):
    def __init__(self, guild_data, page=0):
        super().__init__(timeout=300)
        self.guild_data = guild_data
        self.page = page
        self.items = list(guild_data["shop_items"].items())
    def get_embed(self):
        start = self.page * 5
        end = start + 5
        page_items = self.items[start:end]
        embed = discord.Embed(title="🛒 Server Shop", color=0x00ff88)
        if not page_items:
            embed.description = "No items in the shop right now."
            return embed
        desc = ""
        for i, (item_id, item) in enumerate(page_items, start=start+1):
            stock = item.get("server_stock", "∞")
            if stock is not None and stock <= 0:
                continue
            desc += f"**{i}. {item['name']}** — `{item['price']}` tickets\n"
            desc += f"{item['description'][:150]}{'...' if len(item['description']) > 150 else ''}\n\n"
        embed.description = desc
        embed.set_footer(text=f"Page {self.page+1} • Use buttons to navigate")
        return embed
    @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.gray)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.page + 1) * 5 < len(self.items):
            self.page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
# ====================== LIVE EMBED REFRESH ======================
async def refresh_giveaway_embed(message: discord.Message, giveaway: dict):
    entries = giveaway.get("entries", {})
    total_people = len(entries)
    total_tickets = sum(entries.values()) if not giveaway.get("is_free") else 0
    title = "**TICKET GIVEAWAY**" if giveaway.get("is_free") else "🎟️ **RAFFLE / GIVEAWAY** 🎟️"
    desc = f"**Prize:** {giveaway.get('prize', giveaway.get('prize_tickets', 0))}\n"
    desc += f"**Winners:** {giveaway['winners']}\n"
    desc += f"**Ends:** <t:{int(giveaway['end_time'])}:R>\n"
    desc += f"**Giveaway ID:** `{giveaway['message_id']}`\n\n"
    desc += f"**Entries:** {total_people} people"
    if not giveaway.get("is_free"):
        desc += f" ({total_tickets} total tickets)"
    desc += "\nClick the button below to enter!"
    embed = discord.Embed(title=title, description=desc, color=0x00ff88 if giveaway.get("is_free") else 0x00ff00)
    embed.set_footer(text=f"Hosted by {giveaway.get('host_name', 'Unknown')}")
    if giveaway.get("image_url"):
        embed.set_image(url=giveaway["image_url"])
    await message.edit(embed=embed)
# ====================== HELPERS ======================
def parse_duration(duration_str: str) -> int:
    duration_str = duration_str.lower().strip()
    if duration_str.isdigit():
        return int(duration_str)
    pattern = re.compile(r'(\d+)([dhms]?)')
    total = 0
    for amount, unit in pattern.findall(duration_str):
        amount = int(amount)
        if unit == 'd': total += amount * 86400
        elif unit == 'h': total += amount * 3600
        elif unit == 'm': total += amount * 60
        else: total += amount
    return total if total > 0 else 300
async def finish_giveaway(guild: discord.Guild, message_id: str, refund: bool = False):
    guild_data = get_guild_data(guild.id)
    if message_id not in guild_data["giveaways"]:
        return
    giveaway = guild_data["giveaways"][message_id]
    entries = giveaway.get("entries", {})
    channel = guild.get_channel(int(giveaway["channel_id"]))
    if not channel:
        del guild_data["giveaways"][message_id]
        save_data()
        return
    if refund:
        tickets_dict = guild_data.setdefault("tickets", {})
        for uid, count in entries.items():
            tickets_dict[uid] = tickets_dict.get(uid, 0) + count
        await channel.send("❌ **Giveaway cancelled** — all tickets have been refunded!")
    else:
        if not entries:
            await channel.send("🎟️ Giveaway ended — nobody entered 😢")
        else:
            all_entries = []
            for uid, count in entries.items():
                all_entries.extend([uid] * count)
            num_winners = min(giveaway["winners"], len(all_entries))
            winners = random.sample(all_entries, num_winners)
            winner_mentions = ", ".join(f"<@{w}>" for w in winners)
            if giveaway.get("is_free"):
                prize = giveaway.get("prize_tickets", 0)
                tickets_dict = guild_data.setdefault("tickets", {})
                for w in winners:
                    tickets_dict[w] = tickets_dict.get(w, 0) + prize
                await channel.send(f"🎉 **GIVEAWAY ENDED!**\n**Prize:** {prize} tickets each\n**Winners:** {winner_mentions}\nCongrats! 🎟️")
            else:
                await channel.send(f"🎉 **GIVEAWAY ENDED!**\n**Prize:** {giveaway['prize']}\n**Winners:** {winner_mentions}\nCongrats! 🎟️")
    del guild_data["giveaways"][message_id]
    save_data()
async def giveaway_checker(client):
    await client.wait_until_ready()
    while True:
        await asyncio.sleep(30)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        for guild in client.guilds:
            guild_data = get_guild_data(guild.id)
            ended = [mid for mid, g in list(guild_data["giveaways"].items()) if now > g.get("end_time", 0)]
            for mid in ended:
                await finish_giveaway(guild, mid)
async def shop_checker(client):
    await client.wait_until_ready()
    while True:
        await asyncio.sleep(30)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        for guild in client.guilds:
            guild_data = get_guild_data(guild.id)
            expired = [iid for iid, item in list(guild_data["shop_items"].items()) if item.get("expires_at") and now > item["expires_at"]]
            for iid in expired:
                del guild_data["shop_items"][iid]
            if expired:
                save_data()
async def daily_chat_checker(client):
    await client.wait_until_ready()
    while True:
        await asyncio.sleep(60)
        now = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")
        for guild in client.guilds:
            guild_data = get_guild_data(guild.id)
            daily = guild_data.get("daily_chat_reward", {})
            if daily.get("channel_id") is None or daily.get("reward", 0) <= 0:
                continue
            if current_time_str == daily["time"]:
                entries = guild_data.get("daily_entries", {})
                if not entries:
                    continue
                all_entries = []
                for uid, count in entries.items():
                    all_entries.extend([uid] * count)
                if not all_entries:
                    continue
                num_winners = daily["winners"]
                winners = random.sample(all_entries, min(num_winners, len(all_entries)))
                tickets_dict = guild_data.setdefault("tickets", {})
                winner_mentions = []
                for w in winners:
                    uid = str(w)
                    if daily["prize_type"] in ["tickets", "both"]:
                        tickets_dict[uid] = tickets_dict.get(uid, 0) + daily["reward"]
                    winner_mentions.append(f"<@{w}>")
                save_data()
                channel = guild.get_channel(int(daily["channel_id"]))
                if channel:
                    embed = discord.Embed(title="🏆 Daily Chat Rewards", color=0x00ff88)
                    embed.add_field(name="Congratulations to the Winners!", value=", ".join(winner_mentions), inline=False)
                    if daily["prize_type"] in ["tickets", "both"]:
                        embed.add_field(name="Reward", value=f"**{daily['reward']} tickets** each", inline=False)
                    if daily.get("custom_prize"):
                        embed.add_field(name="Custom Prize", value=daily["custom_prize"], inline=False)
                        embed.set_footer(text="Open a ticket to claim your custom prize!")
                    await channel.send(embed=embed)
                guild_data["daily_entries"] = {}
                save_data()
# ====================== ALL COMMANDS ======================
@tree.command(name="create_giveaway", description="Create a new raffle/giveaway (costs tickets to enter)")
@app_commands.describe(prize="What the winner gets", duration="How long (e.g. 30s, 5m, 1h, 2d)", winners="Number of winners", image="Optional image for the embed", ping_role="Role to ping when the giveaway starts (leave empty for no ping)", channel="Channel to post the giveaway in (leave empty for current channel)")
@app_commands.default_permissions(administrator=True)
async def create_giveaway(interaction: discord.Interaction, prize: str, duration: str, winners: int = 1, image: discord.Attachment = None, ping_role: discord.Role = None, channel: discord.TextChannel = None):
    guild_data = get_guild_data(interaction.guild.id)
    host_role_id = guild_data.get("giveaway_host_role")
    blacklist = guild_data.get("giveaway_blacklist_roles", [])
    has_host_role = host_role_id is None or any(str(role.id) == str(host_role_id) for role in interaction.user.roles)
    is_blacklisted = any(str(role.id) in blacklist for role in interaction.user.roles)
    if not has_host_role or is_blacklisted:
        await interaction.response.send_message("❌ You do not have permission to host giveaways!", ephemeral=True)
        return
    await interaction.response.defer()
    seconds = parse_duration(duration)
    end_time = datetime.datetime.now(datetime.timezone.utc).timestamp() + seconds
    embed = discord.Embed(title="🎟️ **RAFFLE / GIVEAWAY** 🎟️", description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(end_time)}:R>\n**Giveaway ID:** `pending`\n\n**Entries:** 0 people (0 total tickets)\nClick the button below to enter with your tickets!", color=0x00ff00)
    embed.set_footer(text=f"Hosted by {interaction.user.name}")
    if image: embed.set_image(url=image.url)
    view = GiveawayEnterView()
    send_channel = channel or interaction.channel
    content = ping_role.mention if ping_role else None
    msg = await send_channel.send(content=content, embed=embed, view=view)
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["giveaways"][str(msg.id)] = {"message_id": str(msg.id), "prize": prize, "winners": winners, "end_time": end_time, "channel_id": str(send_channel.id), "host_name": interaction.user.name, "image_url": image.url if image else None, "entries": {}}
    save_data()
    await refresh_giveaway_embed(msg, guild_data["giveaways"][str(msg.id)])
    await interaction.followup.send(f"✅ Giveaway created in {send_channel.mention}!", ephemeral=True)
@tree.command(name="create_free_giveaway", description="Create a free button-entry giveaway (winners get tickets)")
@app_commands.describe(prize_tickets="How many tickets each winner gets", duration="How long (e.g. 30s, 5m, 1h, 2d)", winners="Number of winners", image="Optional image for the embed", ping_role="Role to ping when the giveaway starts (leave empty for no ping)", channel="Channel to post the giveaway in (leave empty for current channel)")
@app_commands.default_permissions(administrator=True)
async def create_free_giveaway(interaction: discord.Interaction, prize_tickets: int, duration: str, winners: int = 1, image: discord.Attachment = None, ping_role: discord.Role = None, channel: discord.TextChannel = None):
    guild_data = get_guild_data(interaction.guild.id)
    host_role_id = guild_data.get("giveaway_host_role")
    blacklist = guild_data.get("giveaway_blacklist_roles", [])
    has_host_role = host_role_id is None or any(str(role.id) == str(host_role_id) for role in interaction.user.roles)
    is_blacklisted = any(str(role.id) in blacklist for role in interaction.user.roles)
    if not has_host_role or is_blacklisted:
        await interaction.response.send_message("❌ You do not have permission to host giveaways!", ephemeral=True)
        return
    await interaction.response.defer()
    seconds = parse_duration(duration)
    end_time = datetime.datetime.now(datetime.timezone.utc).timestamp() + seconds
    embed = discord.Embed(title="**TICKET GIVEAWAY**", description=f"**Prize:** {prize_tickets} tickets each\n**Winners:** {winners}\n**Ends:** <t:{int(end_time)}:R>\n**Giveaway ID:** `pending`\n\n**Entries:** 0 people\nClick the button below to enter (free)!", color=0x00ff88)
    embed.set_footer(text=f"Hosted by {interaction.user.name}")
    if image: embed.set_image(url=image.url)
    view = FreeGiveawayView()
    send_channel = channel or interaction.channel
    content = ping_role.mention if ping_role else None
    msg = await send_channel.send(content=content, embed=embed, view=view)
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["giveaways"][str(msg.id)] = {"message_id": str(msg.id), "prize_tickets": prize_tickets, "winners": winners, "end_time": end_time, "channel_id": str(send_channel.id), "host_name": interaction.user.name, "image_url": image.url if image else None, "entries": {}, "is_free": True}
    save_data()
    await refresh_giveaway_embed(msg, guild_data["giveaways"][str(msg.id)])
    await interaction.followup.send(f"✅ Free giveaway created in {send_channel.mention}!", ephemeral=True)
@tree.command(name="set_giveaway_host_role", description="Set the role required to host giveaways (Admins only)")
@app_commands.describe(role="Role that can host giveaways (leave empty to remove restriction)")
@app_commands.default_permissions(administrator=True)
async def set_giveaway_host_role(interaction: discord.Interaction, role: discord.Role = None):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["giveaway_host_role"] = str(role.id) if role else None
    save_data()
    if role:
        await interaction.response.send_message(f"✅ Only users with the **{role.name}** role can now host giveaways!", ephemeral=True)
    else:
        await interaction.response.send_message("✅ Host role restriction removed — only admins can host giveaways!", ephemeral=True)
@tree.command(name="set_ticket_mod_role", description="Set the role required to give/remove tickets (Admins only)")
@app_commands.describe(role="Role that can give/remove tickets (leave empty to remove restriction)")
@app_commands.default_permissions(administrator=True)
async def set_ticket_mod_role(interaction: discord.Interaction, role: discord.Role = None):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["ticket_mod_role"] = str(role.id) if role else None
    save_data()
    if role:
        await interaction.response.send_message(f"✅ Only users with the **{role.name}** role can now give/remove tickets!", ephemeral=True)
    else:
        await interaction.response.send_message("✅ Ticket mod role restriction removed — only admins can give/remove tickets!", ephemeral=True)
@tree.command(name="set_shop_manager_role", description="Set the role required to manage the shop (Admins only)")
@app_commands.describe(role="Role that can add/remove shop items (leave empty to remove restriction)")
@app_commands.default_permissions(administrator=True)
async def set_shop_manager_role(interaction: discord.Interaction, role: discord.Role = None):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["shop_manager_role"] = str(role.id) if role else None
    save_data()
    if role:
        await interaction.response.send_message(f"✅ Only users with the **{role.name}** role can now manage the shop!", ephemeral=True)
    else:
        await interaction.response.send_message("✅ Shop manager role restriction removed — only admins can manage the shop!", ephemeral=True)
@tree.command(name="set_chest_manager_role", description="Set the role required to add chest items (Admins only)")
@app_commands.describe(role="Role that can add/remove chest items (leave empty to remove restriction)")
@app_commands.default_permissions(administrator=True)
async def set_chest_manager_role(interaction: discord.Interaction, role: discord.Role = None):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["chest_manager_role"] = str(role.id) if role else None
    save_data()
    if role:
        await interaction.response.send_message(f"✅ Only users with the **{role.name}** role can now manage chests!", ephemeral=True)
    else:
        await interaction.response.send_message("✅ Chest manager role restriction removed — only admins can manage chests!", ephemeral=True)
@tree.command(name="set_crystal_cooldown", description="Set cooldown (in seconds) between crystal gains from chatting")
@app_commands.describe(seconds="Cooldown in seconds")
@app_commands.default_permissions(administrator=True)
async def set_crystal_cooldown(interaction: discord.Interaction, seconds: int):
    if seconds < 0:
        await interaction.response.send_message("❌ Cooldown cannot be negative!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["crystal_cooldown"] = seconds
    save_data()
    await interaction.response.send_message(f"✅ Crystal cooldown set to **{seconds}** seconds!", ephemeral=True)
@tree.command(name="set_invite_reward", description="Set how many tickets a user gets for inviting someone (0 to disable)")
@app_commands.describe(amount="Tickets per successful invite (0 = disabled)")
@app_commands.default_permissions(administrator=True)
async def set_invite_reward(interaction: discord.Interaction, amount: int):
    if amount < 0:
        await interaction.response.send_message("❌ Amount cannot be negative!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["invite_reward"] = amount
    save_data()
    if amount == 0:
        await interaction.response.send_message("✅ Invite reward disabled.", ephemeral=True)
    else:
        await interaction.response.send_message(f"✅ Users will now receive **{amount}** tickets for every successful invite!", ephemeral=True)
@tree.command(name="set_daily_chat_reward", description="Set up daily chat rewards")
@app_commands.describe(channel="Channel to track messages", reward="Tickets per winner", winners="Number of winners", time="Time of day in 24h format (e.g. 18:00)", prize_type="tickets, custom, or both", custom_prize="Custom prize text (if prize_type is custom or both)")
@app_commands.default_permissions(administrator=True)
async def set_daily_chat_reward(interaction: discord.Interaction, channel: discord.TextChannel, reward: int, winners: int, time: str, prize_type: str = "tickets", custom_prize: str = None):
    if reward < 1 or winners < 1:
        await interaction.response.send_message("❌ Reward and winners must be at least 1!", ephemeral=True)
        return
    if prize_type not in ["tickets", "custom", "both"]:
        await interaction.response.send_message("❌ prize_type must be tickets, custom, or both!", ephemeral=True)
        return
    try:
        datetime.datetime.strptime(time, "%H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Time must be in HH:MM 24-hour format!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["daily_chat_reward"] = {
        "channel_id": str(channel.id),
        "reward": reward,
        "winners": winners,
        "time": time,
        "prize_type": prize_type,
        "custom_prize": custom_prize
    }
    guild_data["daily_entries"] = {}
    save_data()
    msg = f"✅ Daily chat rewards enabled!\nChannel: {channel.mention}\nReward: **{reward} tickets** each\nWinners: **{winners}**\nTime: **{time}**"
    if prize_type in ["custom", "both"] and custom_prize:
        msg += f"\nCustom prize: {custom_prize}"
    await interaction.response.send_message(msg, ephemeral=True)
@tree.command(name="set_chest_channel", description="Set the channel for the persistent chest embed")
@app_commands.describe(channel="Channel for the chest embed")
@app_commands.default_permissions(administrator=True)
async def set_chest_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["chest_channel_id"] = str(channel.id)
    save_data()
    await interaction.response.send_message(f"✅ Chest embed channel set to {channel.mention}!", ephemeral=True)
@tree.command(name="set_special_reward_channel", description="Set the channel for rare chest win announcements")
@app_commands.describe(channel="Channel for rare announcements")
@app_commands.default_permissions(administrator=True)
async def set_special_reward_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["special_reward_channel_id"] = str(channel.id)
    save_data()
    await interaction.response.send_message(f"✅ Special reward announcement channel set to {channel.mention}!", ephemeral=True)
@tree.command(name="add_chest_item", description="Add a new chest item (Chest managers only)")
@app_commands.describe(
    name="Chest item name",
    crystal_cost="Crystals required to open",
    tickets_reward="Tickets reward (0 = none)",
    crystals_reward="Crystals reward (0 = none)",
    custom_prize="Custom prize text (leave blank for none)",
    tickets_chance="Chance for tickets reward (0-1)",
    crystals_chance="Chance for crystals reward (0-1)",
    custom_chance="Chance for custom prize (0-1)"
)
async def add_chest_item(interaction: discord.Interaction, name: str, crystal_cost: int, tickets_reward: int = 0, crystals_reward: int = 0, custom_prize: str = None, tickets_chance: float = 0.0, crystals_chance: float = 0.0, custom_chance: float = 0.0):
    guild_data = get_guild_data(interaction.guild.id)
    manager_role_id = guild_data.get("chest_manager_role")
    is_manager = manager_role_id is None or any(str(r.id) == manager_role_id for r in interaction.user.roles)
    if not is_manager and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You do not have permission to add chest items!", ephemeral=True)
        return
    if name in guild_data["chest_items"]:
        await interaction.response.send_message("❌ An item with this name already exists!", ephemeral=True)
        return
    rewards = []
    total_chance = 0.0
    if tickets_reward > 0 and tickets_chance > 0:
        rewards.append({"type": "tickets", "amount": tickets_reward, "chance": tickets_chance})
        total_chance += tickets_chance
    if crystals_reward > 0 and crystals_chance > 0:
        rewards.append({"type": "crystals", "amount": crystals_reward, "chance": crystals_chance})
        total_chance += crystals_chance
    if custom_prize and custom_chance > 0:
        rewards.append({"type": "custom", "prize": custom_prize, "chance": custom_chance})
        total_chance += custom_chance
    if total_chance <= 0:
        await interaction.response.send_message("❌ You must set at least one reward with a positive chance!", ephemeral=True)
        return
    guild_data["chest_items"][name] = {
        "name": name,
        "crystal_cost": crystal_cost,
        "rewards": rewards
    }
    save_data()
    await interaction.response.send_message(f"✅ Chest item **{name}** added! Cost: **{crystal_cost}** crystals.", ephemeral=True)
@tree.command(name="setup_chest", description="Post the persistent chest embed")
@app_commands.default_permissions(administrator=True)
async def setup_chest(interaction: discord.Interaction):
    guild_data = get_guild_data(interaction.guild.id)
    if not guild_data.get("chest_channel_id"):
        await interaction.response.send_message("❌ Set a chest channel first with /set_chest_channel!", ephemeral=True)
        return
    channel = interaction.guild.get_channel(int(guild_data["chest_channel_id"]))
    if not channel:
        await interaction.response.send_message("❌ Chest channel not found!", ephemeral=True)
        return
    embed = discord.Embed(title="🎁 Server Chests", description="Open a chest with crystals for amazing rewards!", color=0xff00ff)
    view = ChestView(guild_data)
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Chest embed posted in {channel.mention}!", ephemeral=True)
@tree.command(name="force_sync", description="Force sync all commands to this server (Admin only)")
@app_commands.default_permissions(administrator=True)
async def force_sync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ Successfully synced **{len(synced)}** commands to this server!", ephemeral=True)
        print(f"✅ Manual force sync: {len(synced)} commands synced to {interaction.guild.name}")
    except Exception as e:
        await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)
        traceback.print_exc()
# ====================== SETUP HOOK ======================
async def setup_hook():
    print("🚀 Running setup_hook...")
    load_data()
    client.add_view(GiveawayEnterView())
    client.add_view(FreeGiveawayView())
    asyncio.create_task(giveaway_checker(client))
    asyncio.create_task(shop_checker(client))
    asyncio.create_task(daily_chat_checker(client))
    print("✅ Giveaway + Shop + Daily Chat checker started!")
client.setup_hook = setup_hook
# ====================== EVENTS ======================
@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    for guild in client.guilds:
        try:
            invites = await guild.invites()
            invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
            print(f"✅ Cached {len(invites)} invites for {guild.name}")
            synced = await tree.sync(guild=guild)
            print(f'✅ Synced {len(synced)} commands to guild: {guild.name} ({guild.id})')
        except Exception as e:
            print(f'❌ Sync failed for {guild.name}: {e}')
            traceback.print_exc()
@client.event
async def on_member_join(member):
    if member.bot or not member.guild:
        return
    guild_data = get_guild_data(member.guild.id)
    reward = guild_data.get("invite_reward", 0)
    if reward <= 0:
        return
    if (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days < 7:
        return
    seen = guild_data.get("seen_members", [])
    if str(member.id) in seen:
        return
    try:
        current_invites = await member.guild.invites()
        cached = invite_cache.get(member.guild.id, {})
        for inv in current_invites:
            old_uses = cached.get(inv.code, 0)
            if inv.uses > old_uses:
                inviter = inv.inviter
                if inviter:
                    tickets_dict = guild_data.setdefault("tickets", {})
                    uid = str(inviter.id)
                    current = tickets_dict.get(uid, 0)
                    tickets_dict[uid] = current + reward
                    save_data()
                    print(f"🎟️ Invite reward: Gave {reward} tickets to {inviter} for inviting {member}")
                    try:
                        await inviter.send(f"🎟️ Thanks for the invite! You received **{reward}** tickets for bringing **{member}** to the server!")
                    except:
                        pass
                invite_cache[member.guild.id] = {i.code: i.uses for i in current_invites}
                seen.append(str(member.id))
                guild_data["seen_members"] = seen
                save_data()
                return
    except Exception as e:
        print(f"Invite reward error: {e}")
@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    guild_data = get_guild_data(message.guild.id)
    if str(message.channel.id) in guild_data.get("excluded_channels", []):
        return
    # Daily chat reward counting
    daily = guild_data.get("daily_chat_reward", {})
    if daily.get("channel_id") and str(message.channel.id) == daily["channel_id"]:
        entries = guild_data.setdefault("daily_entries", {})
        uid = str(message.author.id)
        entries[uid] = entries.get(uid, 0) + 1
        save_data()
    # Crystal earning - IMPROVED SCALING (base 10 + length scaling)
    user_id = str(message.author.id)
    now = datetime.datetime.now().timestamp()
    cooldown = guild_data.get("crystal_cooldown", 60)
    if user_id not in last_crystal_time or now - last_crystal_time[user_id] >= cooldown:
        length = len(message.content)
        if length < 10:
            crystals_gained = 5
        else:
            crystals_gained = 10 + (length // 15)
        crystals_gained = min(crystals_gained, 40)
        guild_data.setdefault("crystals", {})[user_id] = guild_data["crystals"].get(user_id, 0) + crystals_gained
        last_crystal_time[user_id] = now
        save_data()
        print(f"💎 {message.author} earned {crystals_gained} crystals (message length: {length})")
    # Regular ticket farming
    role_bonuses = guild_data.get("role_bonuses", {})
    role_chance_bonuses = guild_data.get("role_chance_bonuses", {})
    extra_tickets = 0
    extra_chance = 0.0
    for role in message.author.roles:
        rid = str(role.id)
        if rid in role_bonuses:
            extra_tickets += role_bonuses[rid]
        if rid in role_chance_bonuses:
            extra_chance += role_chance_bonuses[rid]
    base_chance = guild_data.get("ticket_chance", 0.25)
    total_chance = base_chance + extra_chance
    tickets_won = 0
    chance = total_chance
    while chance > 0:
        if random.random() < min(chance, 1.0):
            tickets_won += 1
        chance -= 1.0
    if tickets_won > 0:
        total_tickets = tickets_won + extra_tickets
        tickets_dict = guild_data.setdefault("tickets", {})
        user_id_str = str(message.author.id)
        current = tickets_dict.get(user_id_str, 0)
        new_total = current + total_tickets
        tickets_dict[user_id_str] = new_total
        save_data()
        ticket_channel_id = guild_data.get("ticket_channel")
        announcement_channel = message.channel
        if ticket_channel_id:
            ch = message.guild.get_channel(int(ticket_channel_id))
            if ch:
                announcement_channel = ch
        try:
            await announcement_channel.send(
                f"🎟️ {message.author.mention} won **{total_tickets}** ticket(s)! "
                f"(+{extra_tickets} from roles) **Total: {new_total}** 🎟️"
            )
        except:
            pass
        print(f"🎟️ TICKET AWARDED to {message.author} (+{extra_tickets} role bonus) → now has {new_total}")
# ====================== RUN BOT ======================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN environment variable is missing!")
    else:
        client.run(TOKEN)
