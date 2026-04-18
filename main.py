import discord
from discord import app_commands
from discord.abc import GuildChannel
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

print("=== JOE FULL CHEST VERSION - 2026-04-18 (ULTIMATE NUKE - DUPLICATES FIXED) ===")

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
            "tickets": {}, "chest_open_cost": 50, "role_bonuses": {},
            "role_chance_bonuses": {}, "ticket_channel": None, "excluded_channels": [],
            "crystal_excluded_channels": [], "daily_excluded_channels": [],
            "gifting_enabled": True, "giveaways": {}, "ticket_chance": 0.25,
            "giveaway_host_role": None, "giveaway_blacklist_roles": [],
            "ticket_mod_role": None, "shop_items": {}, "shop_manager_role": None,
            "invite_reward": 0, "seen_members": [], "daily_chat_reward": {
                "announcement_channel_id": None, "winners": 3, "time": "18:00",
                "tickets_reward": 0, "crystals_reward": 0, "custom_prize": None,
                "reward_display": "Daily Chat Rewards"
            }, "daily_entries": {}, "crystal_cooldown": 60,
            "chest_manager_role": None, "chest_items": {},
            "chest_channel_id": None, "special_reward_channel_id": None,
            "crystals": {}, "chest_message_id": None, "daily_reward_message_id": None
        }
    else:
        gd = data["guilds"][gid]
        if "role_chance_bonuses" not in gd: gd["role_chance_bonuses"] = {}
        if "excluded_channels" not in gd: gd["excluded_channels"] = []
        if "crystal_excluded_channels" not in gd: gd["crystal_excluded_channels"] = []
        if "daily_excluded_channels" not in gd: gd["daily_excluded_channels"] = []
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
        if "daily_chat_reward" not in gd: gd["daily_chat_reward"] = {"announcement_channel_id": None, "winners": 3, "time": "18:00", "tickets_reward": 0, "crystals_reward": 0, "custom_prize": None, "reward_display": "Daily Chat Rewards"}
        if "daily_entries" not in gd: gd["daily_entries"] = {}
        if "crystal_cooldown" not in gd: gd["crystal_cooldown"] = 60
        if "chest_manager_role" not in gd: gd["chest_manager_role"] = None
        if "chest_items" not in gd: gd["chest_items"] = {}
        if "chest_channel_id" not in gd: gd["chest_channel_id"] = None
        if "special_reward_channel_id" not in gd: gd["special_reward_channel_id"] = None
        if "crystals" not in gd: gd["crystals"] = {}
        if "chest_message_id" not in gd: gd["chest_message_id"] = None
        if "daily_reward_message_id" not in gd: gd["daily_reward_message_id"] = None
    return data["guilds"][gid]

# ====================== VIEWS & MODALS ======================
class TicketEntryModal(discord.ui.Modal, title="🎟️ Enter the Raffle"):
    def __init__(self, giveaway_message_id: str, max_entries: int, tickets_per_entry: int):
        super().__init__()
        self.giveaway_message_id = giveaway_message_id
        self.tickets_per_entry = tickets_per_entry
        self.amount = discord.ui.TextInput(
            label="How many entries?",
            style=discord.TextStyle.short,
            placeholder=f"Max: {max_entries} (costs {tickets_per_entry} tickets each)",
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
        if message_id not in guild_data["giveaways"]:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return

        giveaway = guild_data["giveaways"][message_id]
        user_id_str = str(interaction.user.id)
        current_tickets = guild_data.get("tickets", {}).get(user_id_str, 0)
        cost = amount * self.tickets_per_entry

        if cost > current_tickets:
            await interaction.response.send_message(f"❌ You only have **{current_tickets}** tickets! (need {cost})", ephemeral=True)
            return

        guild_data.setdefault("tickets", {})[user_id_str] = current_tickets - cost
        entries = giveaway.setdefault("entries", {})
        entries[user_id_str] = entries.get(user_id_str, 0) + amount
        save_data()

        try:
            await refresh_giveaway_embed(interaction.message, giveaway)
        except:
            pass

        await interaction.response.send_message(
            f"✅ **You entered with {amount} entr(ies)!** (cost: {cost} tickets)\n"
            f"You now have **{entries[user_id_str]}** entries.\n"
            f"Tickets left: **{current_tickets - cost}**",
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

        giveaway = guild_data["giveaways"][message_id]
        current_tickets = guild_data.get("tickets", {}).get(str(interaction.user.id), 0)
        tickets_per_entry = giveaway.get("tickets_per_entry", 1)
        max_entries = current_tickets // tickets_per_entry

        if max_entries < 1:
            await interaction.response.send_message("❌ You don't have enough tickets!", ephemeral=True)
            return

        modal = TicketEntryModal(message_id, max_entries, tickets_per_entry)
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

class ChestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Chest", style=discord.ButtonStyle.green)
    async def open_chest(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_data = get_guild_data(interaction.guild.id)
        user_id = str(interaction.user.id)
        cost = guild_data.get("chest_open_cost", 50)
        crystals = guild_data["crystals"].get(user_id, 0)
        if crystals < cost:
            await interaction.response.send_message(f"❌ You need **{cost}** crystals to open the chest!", ephemeral=True)
            return

        guild_data["crystals"][user_id] = crystals - cost
        save_data()

        items = guild_data.get("chest_items", {})
        if not items:
            await interaction.response.send_message("❌ No items in the chest yet!", ephemeral=True)
            return

        total = sum(item.get("chance", 0) for item in items.values())
        roll = random.random() * total
        cumulative = 0
        won = None
        won_name = ""
        for name, data in items.items():
            cumulative += data.get("chance", 0)
            if roll <= cumulative:
                won = data
                won_name = name
                break

        reward_text = ""
        if won.get("crystal_prize", 0) > 0:
            guild_data["crystals"][user_id] = guild_data["crystals"].get(user_id, 0) + won["crystal_prize"]
            reward_text += f"**{won['crystal_prize']} crystals** "
        if won.get("ticket_prize", 0) > 0:
            tickets_dict = guild_data.setdefault("tickets", {})
            tickets_dict[user_id] = tickets_dict.get(user_id, 0) + won["ticket_prize"]
            reward_text += f"**{won['ticket_prize']} tickets** "
        if won.get("custom_prize"):
            reward_text += f"**{won['custom_prize']}** "

        save_data()

        await interaction.response.send_message(
            f"🎉 You opened the chest and got **{won_name}** → {reward_text or 'nothing'}!",
            ephemeral=True
        )

        if won.get("chance", 0) <= 0.001 and guild_data.get("special_reward_channel_id"):
            ch = interaction.guild.get_channel(int(guild_data["special_reward_channel_id"]))
            if ch:
                await ch.send(f"🌟 **MASSIVE WIN!** {interaction.user.mention} just hit a super rare item from the chest!")

    @discord.ui.button(label="Check Crystals", style=discord.ButtonStyle.gray)
    async def check_crystals(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_data = get_guild_data(interaction.guild.id)
        crystals = guild_data["crystals"].get(str(interaction.user.id), 0)
        await interaction.response.send_message(f"💎 You have **{crystals}** crystals!", ephemeral=True)

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
    total_entries = sum(entries.values())
    title = "**TICKET GIVEAWAY**" if giveaway.get("is_free") else "🎟️ **RAFFLE / GIVEAWAY** 🎟️"
    desc = f"**Prize:** {giveaway.get('prize', giveaway.get('prize_tickets', 0))}\n"
    desc += f"**Winners:** {giveaway['winners']}\n"
    desc += f"**Ends:** <t:{int(giveaway['end_time'])}:R>\n"
    if "tickets_per_entry" in giveaway:
        desc += f"**Cost:** {giveaway['tickets_per_entry']} ticket(s) per entry\n"
    desc += f"**Giveaway ID:** `{giveaway['message_id']}`\n\n"
    desc += f"**Entries:** {total_people} people ({total_entries} total entries)\nClick the button below to enter!"
    embed = discord.Embed(title=title, description=desc, color=0x00ff88 if giveaway.get("is_free") else 0x00ff00)
    embed.set_footer(text=f"Hosted by {giveaway.get('host_name', 'Unknown')}")
    if giveaway.get("image_url"):
        embed.set_image(url=giveaway["image_url"])
    await message.edit(embed=embed)

async def refresh_chest_embed(guild: discord.Guild):
    guild_data = get_guild_data(guild.id)
    if not guild_data.get("chest_channel_id") or not guild_data.get("chest_message_id"):
        return
    channel = guild.get_channel(int(guild_data["chest_channel_id"]))
    if not channel:
        return
    try:
        message = await channel.fetch_message(int(guild_data["chest_message_id"]))
    except discord.NotFound:
        guild_data["chest_message_id"] = None
        save_data()
        return
    except:
        return

    items = guild_data.get("chest_items", {})
    loot_desc = "**What you can win:**\n"
    if items:
        for name, data in items.items():
            rewards = []
            if data.get("crystal_prize", 0) > 0:
                rewards.append(f"{data['crystal_prize']} crystals")
            if data.get("ticket_prize", 0) > 0:
                rewards.append(f"{data['ticket_prize']} tickets")
            if data.get("custom_prize"):
                rewards.append(data["custom_prize"])
            chance = data.get("chance", 0) * 100
            loot_desc += f"• **{name}** — {', '.join(rewards) or 'Nothing'} ({chance:.1f}%)\n"
    else:
        loot_desc += "No items added yet!\n"

    embed = discord.Embed(
        title="🎁 Server Chests",
        description=f"Open a chest for **{guild_data.get('chest_open_cost', 50)} crystals**!\n\n{loot_desc}",
        color=0xff00ff
    )
    embed.set_footer(text="Click 'Open Chest' below • Rewards are private (ephemeral)")
    view = ChestView()
    await message.edit(embed=embed, view=view)

async def refresh_daily_reward_embed(guild: discord.Guild):
    guild_data = get_guild_data(guild.id)
    daily = guild_data.get("daily_chat_reward", {})
    if not daily.get("announcement_channel_id"):
        return
    channel = guild.get_channel(int(daily["announcement_channel_id"]))
    if not channel:
        return
    try:
        h, m = map(int, daily["time"].split(":"))
        now = datetime.datetime.now(datetime.timezone.utc)
        target = datetime.datetime(now.year, now.month, now.day, h, m, tzinfo=datetime.timezone.utc)
        timestamp = int(target.timestamp())
    except:
        timestamp = 0

    embed = discord.Embed(
        title=daily["reward_display"],
        description="Send any message in **any channel** today to earn entries!\nMore messages = more entries.",
        color=0x00ff88
    )
    embed.add_field(name="🕒 Trigger Time", value=f"<t:{timestamp}:t>", inline=True)
    embed.add_field(name="👑 Winners", value=f"**{daily['winners']}**", inline=True)
    prize_text = ""
    if daily.get("tickets_reward", 0) > 0:
        prize_text += f"**{daily['tickets_reward']} tickets** each\n"
    if daily.get("crystals_reward", 0) > 0:
        prize_text += f"**{daily['crystals_reward']} crystals** each\n"
    if daily.get("custom_prize"):
        prize_text += f"**Custom Prize:** {daily['custom_prize']}\n"
    embed.add_field(name="🎁 Prize", value=prize_text or "None set", inline=False)
    embed.set_footer(text="Just chat anywhere • Resets daily at the trigger time")

    if guild_data.get("daily_reward_message_id"):
        try:
            message = await channel.fetch_message(int(guild_data["daily_reward_message_id"]))
            await message.edit(embed=embed)
            return
        except discord.NotFound:
            guild_data["daily_reward_message_id"] = None

    msg = await channel.send(embed=embed)
    guild_data["daily_reward_message_id"] = str(msg.id)
    save_data()

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

def is_channel_excluded(message, excluded_list):
    if not excluded_list:
        return False
    cid = str(message.channel.id)
    if cid in excluded_list:
        return True
    if hasattr(message.channel, "parent") and message.channel.parent:
        parent_id = str(message.channel.parent.id)
        if parent_id in excluded_list:
            return True
    return False

# ====================== BACKGROUND TASKS ======================
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
            if daily.get("announcement_channel_id") is None:
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
                crystals_dict = guild_data.setdefault("crystals", {})
                winner_mentions = []
                for w in winners:
                    uid = str(w)
                    if daily.get("tickets_reward", 0) > 0:
                        tickets_dict[uid] = tickets_dict.get(uid, 0) + daily["tickets_reward"]
                    if daily.get("crystals_reward", 0) > 0:
                        crystals_dict[uid] = crystals_dict.get(uid, 0) + daily["crystals_reward"]
                    winner_mentions.append(f"<@{w}>")
                save_data()
                channel = guild.get_channel(int(daily["announcement_channel_id"]))
                if channel:
                    embed = discord.Embed(title="🏆 Daily Chat Rewards - WINNERS!", color=0x00ff88)
                    embed.add_field(name="Congratulations to the Winners!", value=", ".join(winner_mentions), inline=False)
                    if daily.get("tickets_reward", 0) > 0:
                        embed.add_field(name="Tickets", value=f"**{daily['tickets_reward']}** each", inline=True)
                    if daily.get("crystals_reward", 0) > 0:
                        embed.add_field(name="Crystals", value=f"**{daily['crystals_reward']}** each", inline=True)
                    if daily.get("custom_prize"):
                        embed.add_field(name="Custom Prize", value=daily["custom_prize"], inline=False)
                        embed.set_footer(text="Open a ticket to claim your custom prize!")
                    await channel.send(embed=embed)
                guild_data["daily_entries"] = {}
                save_data()

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

# ====================== TICKET MANAGEMENT COMMANDS ======================
@tree.command(name="add_tickets", description="Give tickets to a user (Mod role only)")
@app_commands.describe(member="User to give tickets to", amount="Number of tickets")
@app_commands.default_permissions(administrator=True)
async def add_tickets(interaction: discord.Interaction, member: discord.Member, amount: int):
    guild_data = get_guild_data(interaction.guild.id)
    mod_role_id = guild_data.get("ticket_mod_role")
    if mod_role_id and not any(str(role.id) == mod_role_id for role in interaction.user.roles):
        await interaction.response.send_message("❌ You need the ticket mod role to use this command!", ephemeral=True)
        return
    if amount < 1:
        await interaction.response.send_message("❌ Amount must be at least 1!", ephemeral=True)
        return
    tickets_dict = guild_data.setdefault("tickets", {})
    uid = str(member.id)
    tickets_dict[uid] = tickets_dict.get(uid, 0) + amount
    save_data()
    await interaction.response.send_message(f"✅ Gave **{amount}** tickets to {member.mention}. They now have **{tickets_dict[uid]}** tickets.", ephemeral=True)

@tree.command(name="remove_tickets", description="Remove tickets from a user (Mod role only)")
@app_commands.describe(member="User to remove tickets from", amount="Number of tickets")
@app_commands.default_permissions(administrator=True)
async def remove_tickets(interaction: discord.Interaction, member: discord.Member, amount: int):
    guild_data = get_guild_data(interaction.guild.id)
    mod_role_id = guild_data.get("ticket_mod_role")
    if mod_role_id and not any(str(role.id) == mod_role_id for role in interaction.user.roles):
        await interaction.response.send_message("❌ You need the ticket mod role to use this command!", ephemeral=True)
        return
    if amount < 1:
        await interaction.response.send_message("❌ Amount must be at least 1!", ephemeral=True)
        return
    tickets_dict = guild_data.setdefault("tickets", {})
    uid = str(member.id)
    current = tickets_dict.get(uid, 0)
    tickets_dict[uid] = max(0, current - amount)
    save_data()
    await interaction.response.send_message(f"✅ Removed **{amount}** tickets from {member.mention}. They now have **{tickets_dict[uid]}** tickets.", ephemeral=True)

# ====================== ROLE BONUS COMMANDS ======================
@tree.command(name="add_role_bonus", description="Add ticket bonus for a role")
@app_commands.describe(role="Role to give bonus tickets", amount="Extra tickets")
@app_commands.default_permissions(administrator=True)
async def add_role_bonus(interaction: discord.Interaction, role: discord.Role, amount: int):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["role_bonuses"][str(role.id)] = amount
    save_data()
    await interaction.response.send_message(f"✅ **{role.name}** now gives **+{amount}** tickets on message!", ephemeral=True)

@tree.command(name="remove_role_bonus", description="Remove ticket bonus from a role")
@app_commands.describe(role="Role to remove bonus from")
@app_commands.default_permissions(administrator=True)
async def remove_role_bonus(interaction: discord.Interaction, role: discord.Role):
    guild_data = get_guild_data(interaction.guild.id)
    if str(role.id) in guild_data["role_bonuses"]:
        del guild_data["role_bonuses"][str(role.id)]
        save_data()
        await interaction.response.send_message(f"✅ Removed bonus from **{role.name}**", ephemeral=True)
    else:
        await interaction.response.send_message("❌ That role has no bonus.", ephemeral=True)

@tree.command(name="list_role_bonuses", description="List all role bonuses")
@app_commands.default_permissions(administrator=True)
async def list_role_bonuses(interaction: discord.Interaction):
    guild_data = get_guild_data(interaction.guild.id)
    if not guild_data["role_bonuses"]:
        await interaction.response.send_message("No role bonuses set.", ephemeral=True)
        return
    embed = discord.Embed(title="Role Bonuses", color=0x00ff88)
    for rid, amt in guild_data["role_bonuses"].items():
        role = interaction.guild.get_role(int(rid))
        name = role.name if role else f"Unknown ({rid})"
        embed.add_field(name=name, value=f"+{amt} tickets", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ====================== BLACKLIST COMMANDS ======================
@tree.command(name="add_giveaway_blacklist_role", description="Blacklist a role from hosting giveaways")
@app_commands.describe(role="Role that cannot host giveaways")
@app_commands.default_permissions(administrator=True)
async def add_giveaway_blacklist_role(interaction: discord.Interaction, role: discord.Role):
    guild_data = get_guild_data(interaction.guild.id)
    cid = str(role.id)
    if cid in guild_data["giveaway_blacklist_roles"]:
        await interaction.response.send_message(f"❌ **{role.name}** is already blacklisted.", ephemeral=True)
        return
    guild_data["giveaway_blacklist_roles"].append(cid)
    save_data()
    await interaction.response.send_message(f"✅ **{role.name}** can no longer host giveaways.", ephemeral=True)

@tree.command(name="remove_giveaway_blacklist_role", description="Remove blacklist from a role")
@app_commands.describe(role="Role to un-blacklist")
@app_commands.default_permissions(administrator=True)
async def remove_giveaway_blacklist_role(interaction: discord.Interaction, role: discord.Role):
    guild_data = get_guild_data(interaction.guild.id)
    cid = str(role.id)
    if cid in guild_data["giveaway_blacklist_roles"]:
        guild_data["giveaway_blacklist_roles"].remove(cid)
        save_data()
        await interaction.response.send_message(f"✅ **{role.name}** can now host giveaways again.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ That role was not blacklisted.", ephemeral=True)

# ====================== SHOP COMMANDS ======================
@tree.command(name="add_shop_item", description="Add an item to the shop")
@app_commands.describe(name="Item name", price="Ticket price", description="Item description", stock="Server-wide stock (leave blank for unlimited)")
@app_commands.default_permissions(administrator=True)
async def add_shop_item(interaction: discord.Interaction, name: str, price: int, description: str, stock: int = None):
    guild_data = get_guild_data(interaction.guild.id)
    item_id = name.lower().replace(" ", "_")
    guild_data["shop_items"][item_id] = {
        "name": name,
        "price": price,
        "description": description,
        "server_stock": stock
    }
    save_data()
    await interaction.response.send_message(f"✅ Added **{name}** to the shop for **{price}** tickets!", ephemeral=True)

@tree.command(name="remove_shop_item", description="Remove an item from the shop")
@app_commands.describe(name="Item name")
@app_commands.default_permissions(administrator=True)
async def remove_shop_item(interaction: discord.Interaction, name: str):
    guild_data = get_guild_data(interaction.guild.id)
    item_id = name.lower().replace(" ", "_")
    if item_id in guild_data["shop_items"]:
        del guild_data["shop_items"][item_id]
        save_data()
        await interaction.response.send_message(f"✅ Removed **{name}** from the shop.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Item not found.", ephemeral=True)

@tree.command(name="buy", description="Buy an item from the shop")
@app_commands.describe(item="Item name")
async def buy(interaction: discord.Interaction, item: str):
    guild_data = get_guild_data(interaction.guild.id)
    item_id = item.lower().replace(" ", "_")
    if item_id not in guild_data["shop_items"]:
        await interaction.response.send_message("❌ That item doesn't exist!", ephemeral=True)
        return
    shop_item = guild_data["shop_items"][item_id]
    price = shop_item["price"]
    user_tickets = guild_data.get("tickets", {}).get(str(interaction.user.id), 0)
    if user_tickets < price:
        await interaction.response.send_message(f"❌ You need **{price}** tickets!", ephemeral=True)
        return
    guild_data.setdefault("tickets", {})[str(interaction.user.id)] = user_tickets - price
    if shop_item.get("server_stock") is not None:
        shop_item["server_stock"] -= 1
    save_data()
    await interaction.response.send_message(f"✅ You bought **{shop_item['name']}**!", ephemeral=False)

@tree.command(name="my_tickets", description="Quickly check your tickets")
async def my_tickets(interaction: discord.Interaction):
    guild_data = get_guild_data(interaction.guild.id)
    tickets = guild_data.get("tickets", {}).get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"🎟️ You have **{tickets}** tickets!", ephemeral=True)

# ====================== GIVEAWAY COMMANDS ======================
@tree.command(name="create_giveaway", description="Create a new raffle/giveaway (costs tickets to enter)")
@app_commands.describe(
    prize="What the winner gets",
    duration="How long (e.g. 30s, 5m, 1h, 2d)",
    winners="Number of winners",
    tickets_per_entry="Tickets required per entry (default 1)",
    image="Optional image for the embed",
    ping_role="Role to ping when the giveaway starts (leave empty for no ping)",
    channel="Channel to post the giveaway in (leave empty for current channel)"
)
@app_commands.default_permissions(administrator=True)
async def create_giveaway(interaction: discord.Interaction, prize: str, duration: str, winners: int = 1,
                          tickets_per_entry: int = 1, image: discord.Attachment = None,
                          ping_role: discord.Role = None, channel: discord.TextChannel = None):
    guild_data = get_guild_data(interaction.guild.id)
    host_role_id = guild_data.get("giveaway_host_role")
    blacklist = guild_data.get("giveaway_blacklist_roles", [])
    has_host_role = host_role_id is None or any(str(role.id) == str(host_role_id) for role in interaction.user.roles)
    is_blacklisted = any(str(role.id) in blacklist for role in interaction.user.roles) and not has_host_role
    if not has_host_role or is_blacklisted:
        await interaction.response.send_message("❌ You do not have permission to host giveaways!\n(You need the host role or admin permissions)", ephemeral=True)
        return
    if tickets_per_entry < 1:
        await interaction.response.send_message("❌ Tickets per entry must be at least 1!", ephemeral=True)
        return
    await interaction.response.defer()
    seconds = parse_duration(duration)
    end_time = datetime.datetime.now(datetime.timezone.utc).timestamp() + seconds
    desc = f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(end_time)}:R>\n"
    desc += f"**Cost:** {tickets_per_entry} ticket(s) per entry\n**Giveaway ID:** `pending`\n\n"
    desc += "**Entries:** 0 people (0 total entries)\nClick the button below to enter!"
    embed = discord.Embed(title="🎟️ **RAFFLE / GIVEAWAY** 🎟️", description=desc, color=0x00ff00)
    embed.set_footer(text=f"Hosted by {interaction.user.name}")
    if image:
        embed.set_image(url=image.url)
    view = GiveawayEnterView()
    send_channel = channel or interaction.channel
    content = ping_role.mention if ping_role else None
    msg = await send_channel.send(content=content, embed=embed, view=view)
    guild_data["giveaways"][str(msg.id)] = {
        "message_id": str(msg.id),
        "prize": prize,
        "winners": winners,
        "end_time": end_time,
        "channel_id": str(send_channel.id),
        "host_name": interaction.user.name,
        "image_url": image.url if image else None,
        "entries": {},
        "tickets_per_entry": tickets_per_entry
    }
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
    is_blacklisted = any(str(role.id) in blacklist for role in interaction.user.roles) and not has_host_role
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
    guild_data["giveaways"][str(msg.id)] = {"message_id": str(msg.id), "prize_tickets": prize_tickets, "winners": winners, "end_time": end_time, "channel_id": str(send_channel.id), "host_name": interaction.user.name, "image_url": image.url if image else None, "entries": {}, "is_free": True}
    save_data()
    await refresh_giveaway_embed(msg, guild_data["giveaways"][str(msg.id)])
    await interaction.followup.send(f"✅ Free giveaway created in {send_channel.mention}!", ephemeral=True)

# ====================== ROLE / CHEST / DAILY / SETUP COMMANDS ======================
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

@tree.command(name="set_daily_chat_reward", description="Set up daily chat rewards (global + easy)")
@app_commands.describe(
    announcement_channel="Channel where the daily info embed will be posted",
    winners="Number of winners",
    time="Time of day in 24h format (e.g. 18:00)",
    tickets_reward="Tickets each winner gets (0 = none)",
    crystals_reward="Crystals each winner gets (0 = none)",
    custom_prize="Optional custom prize text",
    reward_display="Title of the announcement embed"
)
@app_commands.default_permissions(administrator=True)
async def set_daily_chat_reward(interaction: discord.Interaction, announcement_channel: discord.TextChannel,
                                winners: int, time: str, tickets_reward: int = 0,
                                crystals_reward: int = 0, custom_prize: str = None,
                                reward_display: str = "Daily Chat Rewards"):
    if winners < 1:
        await interaction.response.send_message("❌ Winners must be at least 1!", ephemeral=True)
        return
    try:
        datetime.datetime.strptime(time, "%H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Time must be in HH:MM 24-hour format!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["daily_chat_reward"] = {
        "announcement_channel_id": str(announcement_channel.id),
        "winners": winners,
        "time": time,
        "tickets_reward": tickets_reward,
        "crystals_reward": crystals_reward,
        "custom_prize": custom_prize,
        "reward_display": reward_display
    }
    guild_data["daily_entries"] = {}
    save_data()
    await refresh_daily_reward_embed(interaction.guild)
    msg = f"✅ Daily chat rewards enabled!\nAnnouncement in: {announcement_channel.mention}\nTime: **{time}**\nWinners: **{winners}**"
    if tickets_reward > 0:
        msg += f"\nTickets: **{tickets_reward}** each"
    if crystals_reward > 0:
        msg += f"\nCrystals: **{crystals_reward}** each"
    if custom_prize:
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

@tree.command(name="set_chest_open_cost", description="Set the crystal cost to open the chest")
@app_commands.describe(amount="Crystals required to open the chest")
@app_commands.default_permissions(administrator=True)
async def set_chest_open_cost(interaction: discord.Interaction, amount: int):
    if amount < 1:
        await interaction.response.send_message("❌ Cost must be at least 1!", ephemeral=True)
        return
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["chest_open_cost"] = amount
    save_data()
    await interaction.response.send_message(f"✅ Opening the chest now costs **{amount}** crystals!", ephemeral=True)
    await refresh_chest_embed(interaction.guild)

@tree.command(name="set_special_reward_channel", description="Set the channel for rare chest win announcements")
@app_commands.describe(channel="Channel for rare announcements")
@app_commands.default_permissions(administrator=True)
async def set_special_reward_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_data = get_guild_data(interaction.guild.id)
    guild_data["special_reward_channel_id"] = str(channel.id)
    save_data()
    await interaction.response.send_message(f"✅ Special reward announcement channel set to {channel.mention}!", ephemeral=True)

@tree.command(name="add_chest_item", description="Add a reward to the chest loot table")
@app_commands.describe(
    name="Name of the reward",
    crystal_prize="Crystals awarded (0 = none)",
    ticket_prize="Tickets awarded (0 = none)",
    custom_prize="Custom prize text (e.g. VIP Role 7 days, Special Shoutout)",
    chance="Drop chance (0.0 - 1.0)"
)
async def add_chest_item(interaction: discord.Interaction, name: str, crystal_prize: int = 0, ticket_prize: int = 0, custom_prize: str = None, chance: float = 0.0):
    guild_data = get_guild_data(interaction.guild.id)
    manager_role_id = guild_data.get("chest_manager_role")
    is_manager = manager_role_id is None or any(str(r.id) == manager_role_id for r in interaction.user.roles)
    if not is_manager and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You do not have permission to add chest items!", ephemeral=True)
        return
    if name in guild_data["chest_items"]:
        await interaction.response.send_message("❌ An item with this name already exists!", ephemeral=True)
        return
    if chance <= 0 or chance > 1:
        await interaction.response.send_message("❌ Chance must be between 0.0 and 1.0!", ephemeral=True)
        return
    if crystal_prize < 0 or ticket_prize < 0:
        await interaction.response.send_message("❌ Prizes cannot be negative!", ephemeral=True)
        return
    guild_data["chest_items"][name] = {
        "name": name,
        "crystal_prize": crystal_prize,
        "ticket_prize": ticket_prize,
        "custom_prize": custom_prize,
        "chance": chance
    }
    save_data()
    await interaction.response.send_message(f"✅ Added **{name}** to the chest loot table (chance: {chance*100:.1f}%)", ephemeral=True)
    await refresh_chest_embed(interaction.guild)

@tree.command(name="setup_chest", description="Post the persistent chest embed with full loot table")
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
    items = guild_data.get("chest_items", {})
    loot_desc = "**What you can win:**\n"
    if items:
        for name, data in items.items():
            rewards = []
            if data.get("crystal_prize", 0) > 0:
                rewards.append(f"{data['crystal_prize']} crystals")
            if data.get("ticket_prize", 0) > 0:
                rewards.append(f"{data['ticket_prize']} tickets")
            if data.get("custom_prize"):
                rewards.append(data["custom_prize"])
            chance = data.get("chance", 0) * 100
            loot_desc += f"• **{name}** — {', '.join(rewards) or 'Nothing'} ({chance:.1f}%)\n"
    else:
        loot_desc += "No items added yet!\n"
    embed = discord.Embed(
        title="🎁 Server Chests",
        description=f"Open a chest for **{guild_data.get('chest_open_cost', 50)} crystals**!\n\n{loot_desc}",
        color=0xff00ff
    )
    embed.set_footer(text="Click 'Open Chest' below • Rewards are private (ephemeral)")
    view = ChestView()
    msg = await channel.send(embed=embed, view=view)
    guild_data["chest_message_id"] = str(msg.id)
    save_data()
    await interaction.response.send_message(f"✅ Chest embed posted in {channel.mention} and will now auto-update when items change!", ephemeral=True)

# ====================== ULTIMATE NUKE COMMAND ======================
@tree.command(name="nuke_all_commands", description="NUKE EVERYTHING - clears global + guild commands (use this when force_sync fails)")
@app_commands.default_permissions(administrator=True)
async def nuke_all_commands(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        # Clear global commands first
        await tree.sync(guild=None)
        # Clear guild commands
        tree.clear_commands(guild=interaction.guild)
        await tree.sync(guild=interaction.guild)
        # Clear again for safety
        tree.clear_commands(guild=interaction.guild)
        tree.copy_global_to(guild=interaction.guild)
        synced = await tree.sync(guild=interaction.guild)
        
        await interaction.followup.send(
            f"✅ **ULTIMATE NUKE COMPLETE!**\n"
            f"Global and guild commands have been wiped and re-registered (**{len(synced)}** commands).\n"
            f"Duplicates should now be gone. Wait 30 seconds and check your command list.",
            ephemeral=True
        )
        print(f"✅ ULTIMATE NUKE RUN on {interaction.guild.name} - {len(synced)} commands")
    except Exception as e:
        await interaction.followup.send(f"❌ Nuke failed: {e}", ephemeral=True)
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
    print("✅ All background tasks started!")

client.setup_hook = setup_hook

# ====================== EVENTS ======================
@client.event
async def on_ready():
    print(f'✅ Logged in as {client.user}')
    for guild in client.guilds:
        try:
            # Aggressive global + guild clear on startup
            await tree.sync(guild=None)
            tree.clear_commands(guild=guild)
            await tree.sync(guild=guild)
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
            print(f'✅ Synced {len(synced)} commands to {guild.name}')
        except Exception as e:
            print(f'❌ Sync failed for {guild.name}: {e}')

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

    if not is_channel_excluded(message, guild_data.get("excluded_channels", [])):
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

    if not is_channel_excluded(message, guild_data.get("crystal_excluded_channels", [])):
        user_id = str(message.author.id)
        now = datetime.datetime.now().timestamp()
        cooldown = guild_data.get("crystal_cooldown", 60)
        if user_id not in last_crystal_time or now - last_crystal_time[user_id] >= cooldown:
            length = len(message.content)
            crystals_gained = 5 if length < 10 else 10 + (length // 15)
            crystals_gained = min(crystals_gained, 40)
            guild_data.setdefault("crystals", {})[user_id] = guild_data["crystals"].get(user_id, 0) + crystals_gained
            last_crystal_time[user_id] = now
            save_data()
            print(f"💎 {message.author} earned {crystals_gained} crystals (message length: {length})")

    if not is_channel_excluded(message, guild_data.get("daily_excluded_channels", [])):
        daily = guild_data.get("daily_chat_reward", {})
        if daily.get("announcement_channel_id"):
            entries = guild_data.setdefault("daily_entries", {})
            uid = str(message.author.id)
            entries[uid] = entries.get(uid, 0) + 1
            save_data()

# ====================== RUN BOT ======================
if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN environment variable is missing!")
    else:
        client.run(TOKEN)
