import discord
from discord import app_commands
from discord.ui import View, Button
import json
import os
import math

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DATA_FILE = "match_data.json"
K_FACTOR = 32

# Load or initialize data
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        match_data = json.load(f)
else:
    match_data = {"sports": {}, "elo": {}, "matches": [], "naked_laps": {}}


def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(match_data, f, indent=4)


def get_elo(user_id: str, sport: str) -> float:
    return match_data["elo"].get(user_id, {}).get(sport, 1000)


def set_elo(user_id: str, sport: str, new_elo: float):
    if user_id not in match_data["elo"]:
        match_data["elo"][user_id] = {}
    match_data["elo"][user_id][sport] = round(new_elo, 2)


def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo_winner_loser(winner_ids, loser_ids, sport):
    winner_elos = [get_elo(str(uid), sport) for uid in winner_ids]
    loser_elos = [get_elo(str(uid), sport) for uid in loser_ids]

    avg_winner_elo = sum(winner_elos) / len(winner_elos)
    avg_loser_elo = sum(loser_elos) / len(loser_elos)

    expected_win = expected_score(avg_winner_elo, avg_loser_elo)
    expected_loss = expected_score(avg_loser_elo, avg_winner_elo)

    for uid, r in zip(winner_ids, winner_elos):
        new_r = r + K_FACTOR * (1 - expected_win)
        set_elo(str(uid), sport, new_r)

    for uid, r in zip(loser_ids, loser_elos):
        new_r = r + K_FACTOR * (0 - expected_loss)
        set_elo(str(uid), sport, new_r)


async def autocomplete_sports(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=sport, value=sport)
        for sport in match_data.get("sports", {})
        if current.lower() in sport.lower()
    ][:25]


class ConfirmMatchView(View):
    def __init__(self, losers, winners, score, sport, interaction):
        super().__init__(timeout=60)
        self.losers = losers
        self.finalized = False
        self.interaction = interaction
        self.sport = sport
        self.score = score
        self.winner_ids = [m.id for m in winners]
        self.loser_ids = [m.id for m in losers]

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [m.id for m in self.losers]:
            await interaction.response.send_message(
                "⛔ Only a losing player can confirm this match.", ephemeral=True
            )
            return

        if self.finalized:
            await interaction.response.send_message(
                "✅ Match already confirmed.", ephemeral=True
            )
            return

        self.finalized = True

        match_data["matches"].append(
            {
                "sport": self.sport,
                "winner_ids": self.winner_ids,
                "loser_ids": self.loser_ids,
                "score": self.score,
                "reported_by": self.interaction.user.id,
            }
        )

        update_elo_winner_loser(self.winner_ids, self.loser_ids, self.sport)

        if self.score.split("-")[1].strip() == "0":
            for uid in self.loser_ids:
                uid_str = str(uid)
                match_data["naked_laps"][uid_str] = (
                    match_data["naked_laps"].get(uid_str, 0) + 1
                )

        save_data()

        await interaction.response.edit_message(
            content="✅ Match confirmed and recorded!", view=None
        )


@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Logged in as {client.user}. Slash commands synced.")


# ------------------------------------------
# /create_sport with validation
# ------------------------------------------
@tree.command(
    name="create_sport",
    description="Create a new sport",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(name="Name of the sport", team_size="Team size (1 or 2 only)")
async def create_sport(interaction: discord.Interaction, name: str, team_size: int):
    name = name.lower()
    if team_size not in [1, 2]:
        await interaction.response.send_message(
            "❌ Only team sizes of 1 or 2 are allowed.", ephemeral=True
        )
        return
    if name in match_data["sports"]:
        await interaction.response.send_message(
            f"⚠️ Sport **{name}** already exists.", ephemeral=True
        )
        return
    match_data["sports"][name] = {"team_size": team_size}
    save_data()
    await interaction.response.send_message(
        f"✅ Sport **{name}** created with team size **{team_size}v{team_size}**."
    )


# ------------------------------------------
# /match for 1v1 or 2v2
# ------------------------------------------
@tree.command(
    name="match",
    description="Record a match result (1v1 or 2v2)",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(
    sport="Sport name",
    winner1="Player 1 on winning team",
    winner2="(Optional) Player 2 on winning team",
    loser1="Player 1 on losing team",
    loser2="(Optional) Player 2 on losing team",
    score="Final score (e.g. 2-1)",
)
async def match(
    interaction: discord.Interaction,
    sport: str,
    winner1: discord.Member,
    winner2: discord.Member = None,
    loser1: discord.Member = None,
    loser2: discord.Member = None,
    score: str = "0-0",
):
    sport = sport.lower()

    if sport not in match_data["sports"]:
        await interaction.response.send_message(
            "❌ Sport not found. Use `/create_sport` first.", ephemeral=True
        )
        return

    team_size = match_data["sports"][sport]["team_size"]
    if team_size == 1 and (winner2 or loser2):
        await interaction.response.send_message(
            "❌ This is a 1v1 sport. Only one player per team.", ephemeral=True
        )
        return
    if team_size == 2 and (not winner2 or not loser2):
        await interaction.response.send_message(
            "❌ This is a 2v2 sport. Two players required per team.", ephemeral=True
        )
        return

    winners = [winner1] if team_size == 1 else [winner1, winner2]
    losers = [loser1] if team_size == 1 else [loser1, loser2]

    view = ConfirmMatchView(
        losers=losers,
        winners=winners,
        score=score,
        sport=sport,
        interaction=interaction,
    )
    loser_mentions = " or ".join([m.mention for m in losers])
    winner_names = ", ".join([m.display_name for m in winners])
    loser_names = ", ".join([m.display_name for m in losers])

    await interaction.response.send_message(
        f"📋 Waiting for confirmation from {loser_mentions}...\n"
        f"🏆 **Winners**: {winner_names}\n"
        f"💀 **Losers**: {loser_names}\n"
        f"🎯 **Score**: {score}",
        view=view,
    )


@match.autocomplete("sport")
async def sport_autocomplete(interaction: discord.Interaction, current: str):
    return await autocomplete_sports(interaction, current)


# ------------------------------------------
# /leaderboard
# ------------------------------------------
@tree.command(
    name="leaderboard",
    description="Show ELO rankings for a sport",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(sport="Sport name")
async def leaderboard(interaction: discord.Interaction, sport: str):
    sport = sport.lower()

    leaderboard = [
        (int(user_id), elo[sport])
        for user_id, elo in match_data["elo"].items()
        if sport in elo
    ]

    if not leaderboard:
        await interaction.response.send_message(
            "❌ No ELO data available for this sport."
        )
        return

    leaderboard.sort(key=lambda x: x[1], reverse=True)

    lines = []
    for rank, (uid, elo) in enumerate(leaderboard, start=1):
        user = await client.fetch_user(uid)
        lines.append(f"**#{rank}** – {user.display_name}: {elo}")

    await interaction.response.send_message(
        f"🏆 **{sport.title()} Leaderboard** 🏆\n" + "\n".join(lines)
    )


@leaderboard.autocomplete("sport")
async def sport_autocomplete(interaction: discord.Interaction, current: str):
    return await autocomplete_sports(interaction, current)


# ------------------------------------------
# /match_history
# ------------------------------------------
@tree.command(
    name="match_history",
    description="See the match history for a user",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(user="The user to view match history for")
async def match_history(interaction: discord.Interaction, user: discord.Member):
    user_id = user.id
    matches = match_data.get("matches", [])

    # Filter matches involving the user
    user_matches = [
        m
        for m in matches
        if user_id in m.get("winner_ids", []) or user_id in m.get("loser_ids", [])
    ]

    if not user_matches:
        await interaction.response.send_message(
            f"📭 No matches found for {user.display_name}."
        )
        return

    # Sort by most recent (optional)
    user_matches = user_matches[::-1]

    history_lines = []
    for match in user_matches[-10:]:  # show up to last 10
        sport = match["sport"]
        score = match.get("score", "N/A")
        winners = ", ".join(
            [(await client.fetch_user(uid)).display_name for uid in match["winner_ids"]]
        )
        losers = ", ".join(
            [(await client.fetch_user(uid)).display_name for uid in match["loser_ids"]]
        )
        outcome = "✅ Win" if user_id in match["winner_ids"] else "❌ Loss"
        history_lines.append(
            f"**{sport.title()}** | {outcome} | 🏆 {winners} vs 💀 {losers} | 🎯 {score}"
        )

    await interaction.response.send_message(
        f"📜 **Match History for {user.display_name}**\n" + "\n".join(history_lines)
    )


# ------------------------------------------
# /show_naked_laps
# ------------------------------------------
@tree.command(
    name="show_naked_laps",
    description="See who's doing naked laps (0-point losses)",
    guild=discord.Object(id=GUILD_ID),
)
async def show_naked_laps(interaction: discord.Interaction):
    laps = match_data.get("naked_laps", {})

    if not laps:
        await interaction.response.send_message("🎉 No naked laps yet!")
        return

    sorted_laps = sorted(laps.items(), key=lambda x: x[1], reverse=True)

    lines = []
    for rank, (uid, count) in enumerate(sorted_laps, start=1):
        user = await client.fetch_user(int(uid))
        lines.append(f"**#{rank}** – {user.display_name}: {count} naked lap(s)")

    await interaction.response.send_message(
        "🏃‍♂️ **Naked Lap Leaderboard** 🏃‍♀️\n" + "\n".join(lines)
    )


# ------------------------------------------
# /clear_naked_laps
# ------------------------------------------
@tree.command(
    name="clear_naked_lap",
    description="(Admin only) Remove one naked lap from a specific user",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(user="The user whose naked lap count should be reduced by one")
async def clear_naked_lap(interaction: discord.Interaction, user: discord.Member):
    # Admin-only check
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "⛔ You must be an administrator to use this command.", ephemeral=True
        )
        return

    uid = str(user.id)
    laps = match_data.get("naked_laps", {})

    if uid not in laps or laps[uid] == 0:
        await interaction.response.send_message(
            f"🧼 {user.display_name} has no naked laps to clear.", ephemeral=True
        )
        return

    match_data["naked_laps"][uid] -= 1

    # Clean up if count hits zero
    if match_data["naked_laps"][uid] == 0:
        del match_data["naked_laps"][uid]

    save_data()

    await interaction.response.send_message(
        f"✅ Removed 1 naked lap from **{user.display_name}**. Remaining: {match_data['naked_laps'].get(uid, 0)}"
    )


client.run(TOKEN)
