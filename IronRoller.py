import random
import json
import os
import discord
from discord.ext import commands
from discord import app_commands

# Load token from environment (safe for hosting)
TOKEN = os.getenv("TOKEN")

# Fail fast if token is missing
if TOKEN is None:
    raise ValueError("TOKEN environment variable not set")

DATA_FILE = "data.json"
ROLLS_FILE = "last_rolls.json"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def load_json_file(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json_file(filename, data):
    with open(filename, "w") as file:
        json.dump(data, file)

data_store = load_json_file(DATA_FILE)
last_rolls = load_json_file(ROLLS_FILE)

def save_data():
    save_json_file(DATA_FILE, data_store)

def save_last_rolls():
    save_json_file(ROLLS_FILE, last_rolls)

def get_user_data(user_id):
    if user_id not in data_store:
        data_store[user_id] = {
            "momentum": {"current": 2, "max": 10},
            "health": 5,
            "spirit": 5,
            "supply": 5
        }
    return data_store[user_id]

def clamp_stat(value):
    return max(0, min(5, value))

def get_result(score, c1, c2):
    hits = (score > c1) + (score > c2)
    is_match = (c1 == c2)

    if hits == 2:
        return "Strong Hit (Match)" if is_match else "Strong Hit"
    elif hits == 1:
        return "Weak Hit"
    else:
        return "Miss (Match)" if is_match else "Miss"

def get_burn_result(momentum, c1, c2):
    hits = (momentum > c1) + (momentum > c2)

    if hits == 2:
        return "Strong Hit (Momentum Burn)"
    elif hits == 1:
        return "Weak Hit (Momentum Burn)"
    else:
        return "Miss (Momentum Burn)"

class BurnMomentumView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    def disable_all(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Burn Momentum", style=discord.ButtonStyle.primary)
    async def burn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Not your roll.", ephemeral=True)
            return

        if user_id not in last_rolls:
            await interaction.response.send_message("No roll found.", ephemeral=True)
            return

        roll = last_rolls[user_id]
        user = get_user_data(user_id)
        momentum = user["momentum"]["current"]

        new_result = get_burn_result(momentum, roll["c1"], roll["c2"])

        user["momentum"]["current"] = min(2, user["momentum"]["max"])
        save_data()

        del last_rolls[user_id]
        save_last_rolls()

        self.disable_all()

        await interaction.response.edit_message(
            content=
            f"Action Die: {roll['action_die']}\n"
            + f"Score: {roll['score']}\n"
            + f"Challenge Dice: {roll['c1']}, {roll['c2']}\n"
            + f"Momentum was: {momentum}/{user['momentum']['max']}\n"
            + "Decision: Burned momentum\n"
            + "--------------------\n"
            + f"**RESULT: {new_result.upper()}**",
            view=self
        )

    @discord.ui.button(label="Keep Roll", style=discord.ButtonStyle.secondary)
    async def keep_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)

        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Not your roll.", ephemeral=True)
            return

        if user_id not in last_rolls:
            await interaction.response.send_message("No roll found.", ephemeral=True)
            return

        roll = last_rolls[user_id]
        del last_rolls[user_id]
        save_last_rolls()

        self.disable_all()

        await interaction.response.edit_message(
            content=
            f"Action Die: {roll['action_die']}\n"
            + f"Score: {roll['score']}\n"
            + f"Challenge Dice: {roll['c1']}, {roll['c2']}\n"
            + "Decision: Kept roll\n"
            + "--------------------\n"
            + f"**RESULT: {roll['result'].upper()}**",
            view=self
        )

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="action", description="Make an action roll")
@app_commands.describe(stat="Your stat", adds="Any bonus to the roll")
async def action(interaction: discord.Interaction, stat: int, adds: int = 0):
    action_die = random.randint(1, 6)
    c1 = random.randint(1, 10)
    c2 = random.randint(1, 10)

    score = action_die + stat + adds
    result = get_result(score, c1, c2)

    user_id = str(interaction.user.id)
    user = get_user_data(user_id)

    last_rolls[user_id] = {
        "action_die": action_die,
        "score": score,
        "c1": c1,
        "c2": c2,
        "result": result
    }
    save_last_rolls()

    view = BurnMomentumView(interaction.user.id)

    await interaction.response.send_message(
        f"Action Die: {action_die}\n"
        + f"Score: {score}\n"
        + f"Challenge Dice: {c1}, {c2}\n"
        + f"Momentum: {user['momentum']['current']}/{user['momentum']['max']}\n"
        + "--------------------\n"
        + f"**RESULT: {result.upper()}**\n"
        + "Choose now:",
        view=view
    )

@bot.tree.command(name="progress", description="Make a progress roll")
@app_commands.describe(score="Your progress score")
async def progress(interaction: discord.Interaction, score: int):
    c1 = random.randint(1, 10)
    c2 = random.randint(1, 10)

    result = get_result(score, c1, c2)

    await interaction.response.send_message(
        f"Progress Score: {score}\n"
        + f"Challenge Dice: {c1}, {c2}\n"
        + "--------------------\n"
        + f"**RESULT: {result.upper()}**"
    )

@bot.tree.command(name="roll", description="Roll d100 multiple times")
@app_commands.describe(count="How many d100 rolls")
async def roll(interaction: discord.Interaction, count: int):
    if count < 1 or count > 20:
        await interaction.response.send_message("Choose 1–20 rolls.")
        return

    rolls = [random.randint(1, 100) for _ in range(count)]
    lines = "\n".join([f"Roll {i+1}: {r}" for i, r in enumerate(rolls)])

    await interaction.response.send_message(lines)

@bot.tree.command(name="sheet", description="Show your current sheet")
async def sheet(interaction: discord.Interaction):
    user = get_user_data(str(interaction.user.id))

    await interaction.response.send_message(
        "Character Sheet\n"
        + f"Health: {user['health']}/5\n"
        + f"Spirit: {user['spirit']}/5\n"
        + f"Supply: {user['supply']}/5\n"
        + f"Momentum: {user['momentum']['current']}/{user['momentum']['max']}"
    )

@bot.tree.command(name="momentum", description="Show current momentum")
async def momentum(interaction: discord.Interaction):
    user = get_user_data(str(interaction.user.id))
    await interaction.response.send_message(
        f"Momentum: {user['momentum']['current']}/{user['momentum']['max']}"
    )

@bot.tree.command(name="momentum_set", description="Set current momentum")
@app_commands.describe(value="New current momentum")
async def momentum_set(interaction: discord.Interaction, value: int):
    user_id = str(interaction.user.id)
    user = get_user_data(user_id)

    value = max(-6, min(value, user["momentum"]["max"]))
    user["momentum"]["current"] = value
    save_data()

    await interaction.response.send_message(
        f"Momentum: {user['momentum']['current']}/{user['momentum']['max']}"
    )

@bot.tree.command(name="momentum_max", description="Set max momentum")
@app_commands.describe(value="New max momentum")
async def momentum_max(interaction: discord.Interaction, value: int):
    user_id = str(interaction.user.id)
    user = get_user_data(user_id)

    value = max(0, min(value, 10))
    user["momentum"]["max"] = value
    user["momentum"]["current"] = min(user["momentum"]["current"], value)

    save_data()

    await interaction.response.send_message(
        f"Momentum: {user['momentum']['current']}/{user['momentum']['max']}"
    )

@bot.tree.command(name="momentum_add", description="Add to momentum")
@app_commands.describe(amount="Amount to add")
async def momentum_add(interaction: discord.Interaction, amount: int):
    user_id = str(interaction.user.id)
    user = get_user_data(user_id)

    new_val = min(user["momentum"]["max"], user["momentum"]["current"] + amount)
    user["momentum"]["current"] = new_val
    save_data()

    await interaction.response.send_message(
        f"Momentum: {user['momentum']['current']}/{user['momentum']['max']}"
    )

@bot.tree.command(name="momentum_sub", description="Subtract from momentum")
@app_commands.describe(amount="Amount to subtract")
async def momentum_sub(interaction: discord.Interaction, amount: int):
    user_id = str(interaction.user.id)
    user = get_user_data(user_id)

    new_val = max(-6, user["momentum"]["current"] - amount)
    user["momentum"]["current"] = new_val
    save_data()

    await interaction.response.send_message(
        f"Momentum: {user['momentum']['current']}/{user['momentum']['max']}"
    )

@bot.tree.command(name="momentum_clear", description="Reset momentum to 2/10")
async def momentum_clear(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user = get_user_data(user_id)

    user["momentum"]["current"] = 2
    user["momentum"]["max"] = 10
    save_data()

    await interaction.response.send_message("Momentum reset to 2/10.")

def stat_command(name):
    @bot.tree.command(name=name, description=f"Show {name}")
    async def show(interaction: discord.Interaction):
        user = get_user_data(str(interaction.user.id))
        await interaction.response.send_message(f"{name.capitalize()}: {user[name]}/5")

    @bot.tree.command(name=f"{name}_set", description=f"Set {name}")
    @app_commands.describe(value=f"New {name} value")
    async def set_stat(interaction: discord.Interaction, value: int):
        user = get_user_data(str(interaction.user.id))
        user[name] = clamp_stat(value)
        save_data()
        await interaction.response.send_message(f"{name.capitalize()}: {user[name]}/5")

    @bot.tree.command(name=f"{name}_add", description=f"Add to {name}")
    @app_commands.describe(amount=f"Amount to add to {name}")
    async def add_stat(interaction: discord.Interaction, amount: int):
        user = get_user_data(str(interaction.user.id))
        user[name] = clamp_stat(user[name] + amount)
        save_data()
        await interaction.response.send_message(f"{name.capitalize()}: {user[name]}/5")

    @bot.tree.command(name=f"{name}_sub", description=f"Subtract from {name}")
    @app_commands.describe(amount=f"Amount to subtract from {name}")
    async def sub_stat(interaction: discord.Interaction, amount: int):
        user = get_user_data(str(interaction.user.id))
        user[name] = clamp_stat(user[name] - amount)
        save_data()
        await interaction.response.send_message(f"{name.capitalize()}: {user[name]}/5")

    @bot.tree.command(name=f"{name}_clear", description=f"Reset {name} to 5")
    async def clear_stat(interaction: discord.Interaction):
        user = get_user_data(str(interaction.user.id))
        user[name] = 5
        save_data()
        await interaction.response.send_message(f"{name.capitalize()} reset to 5.")

stat_command("health")
stat_command("spirit")
stat_command("supply")

@bot.tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Ironsworn Bot Commands**\n"
        + "--------------------\n"
        + "**Core Rolls**\n"
        + "/action stat:# adds:# - Action roll with Burn or Keep buttons\n"
        + "/progress score:# - Progress roll\n"
        + "/roll count:# - Roll d100 multiple times\n\n"
        + "**Momentum**\n"
        + "/momentum - Show current/max momentum\n"
        + "/momentum_set value:# - Set current momentum\n"
        + "/momentum_add amount:# - Add momentum\n"
        + "/momentum_sub amount:# - Subtract momentum\n"
        + "/momentum_max value:# - Set max momentum\n"
        + "/momentum_clear - Reset momentum to 2/10\n\n"
        + "**Health / Spirit / Supply**\n"
        + "/health, /spirit, /supply - Show value\n"
        + "/health_set value:# - Set health\n"
        + "/health_add amount:# - Add health\n"
        + "/health_sub amount:# - Subtract health\n"
        + "/health_clear - Reset health to 5\n"
        + "/spirit_set value:# - Set spirit\n"
        + "/spirit_add amount:# - Add spirit\n"
        + "/spirit_sub amount:# - Subtract spirit\n"
        + "/spirit_clear - Reset spirit to 5\n"
        + "/supply_set value:# - Set supply\n"
        + "/supply_add amount:# - Add supply\n"
        + "/supply_sub amount:# - Subtract supply\n"
        + "/supply_clear - Reset supply to 5\n\n"
        + "**Sheet**\n"
        + "/sheet - Show health, spirit, supply, and momentum\n"
    )

bot.run(TOKEN)
