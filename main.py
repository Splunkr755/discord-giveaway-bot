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
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
DATA_FILE = "/data/bot_data.json"
data = {}
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
            "shop_items": {}
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
@tree.command(name="give_tickets", description="Give tickets to a user")
@app_commands.describe(user="User to give tickets to", amount="How many tickets")
@app_commands.default_permissions(administrator=True)
async def give_tickets(interaction: discord.Interaction, user: discord.Member, amount: int):
    guild_data = get_guild_data(interaction.guild.id)
    mod_role_id = guild_data.get("ticket_mod_role")
    if mod_role_id and not any(str(role.id) == mod_role_id for role in interaction.user.roles):
        await interaction.response.send_message("❌ You do not have permission to give tickets!", ephemeral=False)
        return
    if amount < 1:
        await interaction.response.send_message("Amount must be at least 1!", ephemeral=False)
        return
    tickets_dict = guild_data.setdefault("tickets", {})
    uid = str(user.id)
    tickets_dict[uid] = tickets_dict.get(uid, 0) + amount
    save_data()
    await interaction.response.send_message(f"✅ Gave **{amount}** tickets to {user.mention}!", ephemeral=False)
@tree.command(name="remove_tickets", description="Remove tickets from a user")
@app_commands.describe(user="User to remove tickets from", amount="How many tickets")
@app_commands.default_permissions(administrator=True)
async def remove_tickets(interaction: discord.Interaction, user: discord.Member, amount: int):
    guild_data = get_guild_data(interaction.guild.id)
    mod_role_id = guild_data.get("ticket_mod_role")
    if mod_role_id and not any(str(role.id) == mod_role_id for role in interaction.user.roles):
        await interaction.response.send_message("❌ You do not have permission to remove tickets!", ephemeral=False)
        return
    if amount < 1:
        await interaction.response.send_message("Amount must be at least 1!", ephemeral=False)
        return
    tickets_dict = guild_data.setdefault("tickets", {})
    uid = str(user.id)
    current = tickets_dict.get(uid, 0)
    new_amount = max(0, current - amount)
    tickets_dict[uid] = new_amount
    save_data()
    await interaction.response.send_message(f"✅ Removed **{amount}** tickets from {user.mention} (now has {new_amount})!", ephemeral=False)
@tree.command(name="gift_tickets", description="Gift tickets to another user")
@app_commands.describe(user="User to gift to", amount="How many tickets")
async def gift_tickets(interaction: discord.Interaction, user: discord.Member, amount: int):
    if amount < 1:
        await interaction.response.send_message("Amount must be at least 1!", ephemeral=False)
        return
    guild_data = get_guild_data(interaction.guild.id)
    if not guild_data["gifting_enabled"]:
        await interaction.response.send_message("❌ Ticket gifting is currently disabled!", ephemeral=False)
        return
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ You can't gift tickets to yourself!", ephemeral=False)
        return
    tickets_dict = guild_data.setdefault("tickets", {})
    giver_id = str(interaction.user.id)
    giver_tickets = tickets_dict.get(giver_id, 0)
    if giver_tickets < amount:
        await interaction.response.send_message(f"❌ You only have **{giver_tickets}** tickets!", ephemeral=False)
        return
    tickets_dict[giver_id] = giver_tickets - amount
    receiver_id = str(user.id)
    tickets_dict[receiver_id] = tickets_dict.get(receiver_id, 0) + amount
    save_data()
    await interaction.response.send_message(f"✅ You gifted **{amount}** tickets to {user.mention}!", ephemeral=False)
@tree.command(name="my_tickets", description="Check your ticket count")
async def my_tickets(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This only works in servers!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    user_id_str = str(interaction.user.id)
    tickets = guild_data.get("tickets", {}).get(user_id_str, 0)
    await interaction.response.send_message(f"🎟️ You currently have **{tickets}** tickets!", ephemeral=True)
@tree.command(name="set_role_bonus", description="Set extra tickets a role gets on win (Admins only)")
@app_commands.describe(role="Role to configure", extra="Extra tickets on win (0 = remove)")
@app_commands.default_permissions(administrator=True)
async def set_role_bonus(interaction: discord.Interaction, role: discord.Role, extra: int):
    if extra < 0: extra = 0
    guild_data = get_guild_data(interaction.guild.id)
    role_bonuses = guild_data.setdefault("role_bonuses", {})
    role_id_str = str(role.id)
    if extra == 0:
        role_bonuses.pop(role_id_str, None)
        msg = f"✅ Removed any bonus for **{role.name}**."
    else:
        role_bonuses[role_id_str] = extra
        msg = f"✅ **{role.name}** now gives **+{extra}** extra ticket(s) when winning!"
    save_data()
    await interaction.response.send_message(msg)
@tree.command(name="set_ticket_channel", description="Set the channel where ticket win messages appear (Admins only)")
@app_commands.describe(channel="Channel for ticket announcements (leave empty to disable)")
@app_commands.default_permissions(administrator=True)
async def set_ticket_channel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_data = get_guild_data(interaction.guild.id)
    if channel is None:
        guild_data.pop("ticket_channel", None)
        msg = "✅ Ticket announcements will now appear in the **same channel** where the message was sent."
    else:
        guild_data["ticket_channel"] = str(channel.id)
        msg = f"✅ Ticket announcements will now be sent to {channel.mention}!"
    save_data()
    await interaction.response.send_message(msg)
@tree.command(name="list_role_bonuses", description="List all role bonuses + current settings")
async def list_role_bonuses(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Server only!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    role_bonuses = guild_data.get("role_bonuses", {})
    role_chance_bonuses = guild_data.get("role_chance_bonuses", {})
    excluded = guild_data.get("excluded_channels", [])
    gifting = "Enabled" if guild_data.get("gifting_enabled", True) else "Disabled"
    lines = ["**🎟️ Current Settings:**"]
    lines.append(f"Gifting: **{gifting}**")
    lines.append(f"Base ticket chance: **{int(guild_data.get('ticket_chance', 0.25)*100)}%**")
    if excluded:
        lines.append("Excluded channels: " + ", ".join([f"<#{ch}>" for ch in excluded]))
    else:
        lines.append("Excluded channels: None")
    if role_bonuses:
        lines.append("\n**Ticket Bonuses:**")
        for rid_str, bonus in role_bonuses.items():
            role = interaction.guild.get_role(int(rid_str))
            rname = role.name if role else f"Unknown ({rid_str})"
            lines.append(f"• **{rname}**: +{bonus} tickets")
    if role_chance_bonuses:
        lines.append("\n**Chance Bonuses:**")
        for rid_str, bonus in role_chance_bonuses.items():
            role = interaction.guild.get_role(int(rid_str))
            rname = role.name if role else f"Unknown ({rid_str})"
            lines.append(f"• **{rname}**: +{bonus*100:.0f}% chance")
    await interaction.response.send_message("\n".join(lines))
@tree.command(name="set_ticket_chance", description="Change the base chance of winning a ticket per message (Admins only)")
@app_commands.describe(chance="Chance as decimal (0.01 = 1%, 0.25 = 25%, 0.5 = 50%)")
@app_commands.default_permissions(administrator=True)
async def set_ticket_chance(interaction: discord.Interaction, chance: float):
    if chance < 0.01 or chance > 1.0:
        await interaction.response.send_message("❌ Chance must be between 0.01 and 1.0!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["ticket_chance"] = chance
    save_data()
    percent = int(chance * 100)
    await interaction.response.send_message(f"✅ Base ticket win chance is now **{percent}%** per message!", ephemeral=True)
@tree.command(name="set_role_chance_bonus", description="Add extra % chance per message for a role")
@app_commands.describe(role="Role to give extra chance", extra_percent="Extra chance (0.1 = +10%)")
@app_commands.default_permissions(administrator=True)
async def set_role_chance_bonus(interaction: discord.Interaction, role: discord.Role, extra_percent: float):
    if extra_percent < 0: extra_percent = 0
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["role_chance_bonuses"][str(role.id)] = extra_percent
    save_data()
    await interaction.response.send_message(f"✅ **{role.name}** now gets **+{extra_percent*100:.0f}%** extra ticket chance per message!", ephemeral=True)
@tree.command(name="add_excluded_channel", description="Add a channel where users cannot earn tickets")
@app_commands.describe(channel="Channel to exclude")
@app_commands.default_permissions(administrator=True)
async def add_excluded_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_data = get_guild_data(interaction.guild.id)
    if str(channel.id) not in guild_data["excluded_channels"]:
        guild_data["excluded_channels"].append(str(channel.id))
        save_data()
    await interaction.response.send_message(f"✅ {channel.mention} is now **excluded** from ticket farming!", ephemeral=True)
@tree.command(name="remove_excluded_channel", description="Remove a channel from the excluded list")
@app_commands.describe(channel="Channel to remove from excluded list")
@app_commands.default_permissions(administrator=True)
async def remove_excluded_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_data = get_guild_data(interaction.guild.id)
    if str(channel.id) in guild_data["excluded_channels"]:
        guild_data["excluded_channels"].remove(str(channel.id))
        save_data()
    await interaction.response.send_message(f"✅ {channel.mention} can now earn tickets again!", ephemeral=True)
@tree.command(name="toggle_gifting", description="Turn ticket gifting on/off (Admin only)")
@app_commands.default_permissions(administrator=True)
async def toggle_gifting(interaction: discord.Interaction):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["gifting_enabled"] = not guild_data["gifting_enabled"]
    save_data()
    status = "enabled" if guild_data["gifting_enabled"] else "disabled"
    await interaction.response.send_message(f"✅ Ticket gifting is now **{status}**!", ephemeral=True)
@tree.command(name="end_giveaway", description="End a giveaway early (or cancel + refund)")
@app_commands.describe(message="Message link or ID of the giveaway", refund="Refund all tickets and cancel? (No = end normally and pick winners)")
@app_commands.default_permissions(administrator=True)
async def end_giveaway(interaction: discord.Interaction, message: str, refund: bool = False):
    await interaction.response.defer(ephemeral=True)
    if "/" in message:
        message_id = message.split("/")[-1]
    else:
        message_id = message
    await finish_giveaway(interaction.guild, message_id, refund)
    action = "cancelled & refunded" if refund else "ended early"
    await interaction.followup.send(f"✅ Giveaway **{action}**!", ephemeral=True)
@tree.command(name="add_giveaway_blacklist_role", description="Add a role that cannot host giveaways")
@app_commands.describe(role="Role to blacklist from hosting")
@app_commands.default_permissions(administrator=True)
async def add_giveaway_blacklist_role(interaction: discord.Interaction, role: discord.Role):
    guild_data = get_guild_data(interaction.guild.id)
    if str(role.id) not in guild_data["giveaway_blacklist_roles"]:
        guild_data["giveaway_blacklist_roles"].append(str(role.id))
        save_data()
    await interaction.response.send_message(f"✅ **{role.name}** can no longer host giveaways!", ephemeral=True)
@tree.command(name="remove_giveaway_blacklist_role", description="Remove a role from the giveaway blacklist")
@app_commands.describe(role="Role to remove from blacklist")
@app_commands.default_permissions(administrator=True)
async def remove_giveaway_blacklist_role(interaction: discord.Interaction, role: discord.Role):
    guild_data = get_guild_data(interaction.guild.id)
    if str(role.id) in guild_data["giveaway_blacklist_roles"]:
        guild_data["giveaway_blacklist_roles"].remove(str(role.id))
        save_data()
    await interaction.response.send_message(f"✅ **{role.name}** can now host giveaways again!", ephemeral=True)
@tree.command(name="add_shop_item", description="Add a new item to the server shop (Admins only)")
@app_commands.describe(
    name="Item name (unique)",
    price="Price in tickets",
    description="Item description",
    image="Optional image",
    server_stock="Total stock (leave blank for unlimited)",
    per_user_limit="Max per user (leave blank for unlimited)",
    duration="How long until item expires (e.g. 2h, 3d)",
    role="Role to auto-give on purchase (optional)"
)
@app_commands.default_permissions(administrator=True)
async def add_shop_item(interaction: discord.Interaction, name: str, price: int, description: str,
                        image: discord.Attachment = None, server_stock: int = None,
                        per_user_limit: int = None, duration: str = None, role: discord.Role = None):
    if price < 1:
        await interaction.response.send_message("❌ Price must be at least 1 ticket!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    if name in guild_data["shop_items"]:
        await interaction.response.send_message("❌ An item with this name already exists!", ephemeral=True)
        return
    expires_at = None
    if duration:
        seconds = parse_duration(duration)
        expires_at = datetime.datetime.now(datetime.timezone.utc).timestamp() + seconds
    guild_data["shop_items"][name] = {
        "name": name,
        "price": price,
        "description": description,
        "image_url": image.url if image else None,
        "server_stock": server_stock,
        "per_user_limit": per_user_limit,
        "expires_at": expires_at,
        "role_id": str(role.id) if role else None,
        "purchases": {}
    }
    save_data()
    await interaction.response.send_message(f"✅ Shop item **{name}** added for `{price}` tickets!", ephemeral=True)
@tree.command(name="shop", description="View the current server shop")
async def shop(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("This only works in servers!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    if not guild_data["shop_items"]:
        await interaction.response.send_message("🛒 The shop is currently empty!", ephemeral=True)
        return
    view = ShopView(guild_data)
    await interaction.response.send_message(embed=view.get_embed(), view=view)
@tree.command(name="buy", description="Buy an item from the shop")
@app_commands.describe(item="Name of the item to buy")
async def buy(interaction: discord.Interaction, item: str):
    if not interaction.guild:
        await interaction.response.send_message("This only works in servers!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    if item not in guild_data["shop_items"]:
        await interaction.response.send_message("❌ That item does not exist in the shop!", ephemeral=True)
        return
    shop_item = guild_data["shop_items"][item]
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    if shop_item.get("expires_at") and now > shop_item["expires_at"]:
        del guild_data["shop_items"][item]
        save_data()
        await interaction.response.send_message("❌ This item has expired!", ephemeral=True)
        return
    if shop_item.get("server_stock") is not None and shop_item["server_stock"] <= 0:
        await interaction.response.send_message("❌ This item is out of stock!", ephemeral=True)
        return
    user_id = str(interaction.user.id)
    bought = shop_item["purchases"].get(user_id, 0)
    if shop_item.get("per_user_limit") is not None and bought >= shop_item["per_user_limit"]:
        await interaction.response.send_message(f"❌ You have already reached the limit for this item!", ephemeral=True)
        return
    tickets_dict = guild_data.setdefault("tickets", {})
    current_tickets = tickets_dict.get(user_id, 0)
    if current_tickets < shop_item["price"]:
        await interaction.response.send_message(f"❌ You only have **{current_tickets}** tickets. Need **{shop_item['price']}**!", ephemeral=True)
        return
    tickets_dict[user_id] = current_tickets - shop_item["price"]
    shop_item["purchases"][user_id] = bought + 1
    if shop_item.get("server_stock") is not None:
        shop_item["server_stock"] -= 1
    save_data()
    role_id = shop_item.get("role_id")
    if role_id:
        role = interaction.guild.get_role(int(role_id))
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ **Purchase successful!** You received the **{role.name}** role!", ephemeral=False)
            return
    await interaction.response.send_message(
        f"✅ **Purchase successful!** You bought **{item}** for `{shop_item['price']}` tickets.\n"
        f"Open a ticket to claim your prize (include a screenshot of this message).",
        ephemeral=False
    )
# ====================== SETUP HOOK ======================
async def setup_hook():
    print("🚀 Running setup_hook...")
    load_data()
    client.add_view(GiveawayEnterView())
    client.add_view(FreeGiveawayView())
    asyncio.create_task(giveaway_checker(client))
    asyncio.create_task(shop_checker(client))
    print("✅ Giveaway + Shop checker started!")
client.setup_hook = setup_hook
# ====================== EVENTS ======================
@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    # Guild-specific sync for EVERY server the bot is in (fixes duplicates)
    for guild in client.guilds:
        try:
            synced = await tree.sync(guild=guild)
            print(f'✅ Synced {len(synced)} commands to guild: {guild.name} ({guild.id})')
        except Exception as e:
            print(f'❌ Sync failed for {guild.name}: {e}')
            traceback.print_exc()
# ====================== TICKET FARMING FROM CHAT ======================
@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    guild_data = get_guild_data(message.guild.id)
    if str(message.channel.id) in guild_data.get("excluded_channels", []):
        return
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
