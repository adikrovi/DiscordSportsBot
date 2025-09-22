import discord
from discord import app_commands
from discord.ui import View, Button, Select
import json
import os
import math
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional

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
    match_data = {
        "sports": {}, 
        "elo": {}, 
        "matches": [], 
        "naked_laps": {},
        "leagues": {},
        "league_signups": {},
        "league_matches": {},
        "league_standings": {},
        "admins": []
    }

# Load admin IDs from environment variable
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",") if os.getenv("ADMIN_IDS") else []
# Convert to integers and filter out empty strings
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS if admin_id.strip().isdigit()]

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(match_data, f, indent=4)

async def get_user_display_info(user_id: int, sport: str = None, guild: discord.Guild = None) -> tuple:
    """Get user display name, ELO, and naked laps for consistent formatting"""
    try:
        user = await client.fetch_user(user_id)
        # Try to get server nickname first, fall back to display name
        display_name = user.display_name
        if guild:
            try:
                member = await guild.fetch_member(user_id)
                display_name = member.display_name
            except:
                pass  # Use user.display_name if member not found
        
        elo = get_elo(str(user_id), sport) if sport else 0
        naked_laps = match_data["naked_laps"].get(str(user_id), 0)
        
        return display_name, elo, naked_laps
    except:
        elo = get_elo(str(user_id), sport) if sport else 0
        naked_laps = match_data["naked_laps"].get(str(user_id), 0)
        return f"Unknown User ({user_id})", elo, naked_laps

# Add any existing admins from environment to the data
if ADMIN_IDS:
    match_data["admins"] = list(set(match_data.get("admins", []) + ADMIN_IDS))
    save_data()

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


# League Management Functions
def create_league(league_name: str, sport: str, season_length: int, signup_deadline: str, 
                  match_day: str, admin_id: int, team_size: int = 1) -> Dict:
    """Create a new league"""
    league = {
        "name": league_name,
        "sport": sport,
        "season_length": season_length,
        "signup_deadline": signup_deadline,
        "match_day": match_day,
        "admin_id": admin_id,
        "team_size": team_size,  # 1 for 1v1, 2 for 2v2
        "status": "signup",  # signup, active, completed
        "created_at": datetime.now().isoformat(),
        "current_week": 0,
        "participants": [],
        "matches": {},
        "standings": {}
    }
    
    match_data["leagues"][league_name] = league
    match_data["league_signups"][league_name] = []
    match_data["league_matches"][league_name] = {}
    match_data["league_standings"][league_name] = {}
    
    save_data()
    return league


def add_participant_to_league(league_name: str, user_id: int) -> bool:
    """Add a participant to a league"""
    if league_name not in match_data["leagues"]:
        return False
    
    league = match_data["leagues"][league_name]
    if league["status"] != "signup":
        return False
    
    if user_id not in match_data["league_signups"][league_name]:
        match_data["league_signups"][league_name].append(user_id)
        save_data()
        return True
    
    return False


def remove_participant_from_league(league_name: str, user_id: int) -> bool:
    """Remove a participant from a league"""
    if league_name not in match_data["leagues"]:
        return False
    
    league = match_data["leagues"][league_name]
    if league["status"] != "signup":
        return False
    
    if user_id in match_data["league_signups"][league_name]:
        match_data["league_signups"][league_name].remove(user_id)
        save_data()
        return True
    
    return False


def start_league(league_name: str) -> bool:
    """Start a league and generate first week matches"""
    if league_name not in match_data["leagues"]:
        return False
    
    league = match_data["leagues"][league_name]
    if league["status"] != "signup":
        return False
    
    participants = match_data["league_signups"][league_name]
    if len(participants) < 2:
        return False
    
    league["status"] = "active"
    league["current_week"] = 1
    league["participants"] = participants.copy()
    
    # Initialize standings
    for user_id in participants:
        match_data["league_standings"][league_name][str(user_id)] = {
            "wins": 0,
            "losses": 0,
            "points": 0,
            "elo": get_elo(str(user_id), league["sport"])
        }
    
    # Generate first week matches
    generate_week_matches(league_name, 1)
    
    save_data()
    return True


def generate_week_matches(league_name: str, week: int):
    """Generate matches for a specific week with minimized repeated matchups and rotated BYEs"""
    if league_name not in match_data["leagues"]:
        return
    
    league = match_data["leagues"][league_name]
    participants = league["participants"]
    
    if week not in match_data["league_matches"][league_name]:
        match_data["league_matches"][league_name][week] = []
    
    if league.get("team_size", 1) == 2:
        matches = generate_week_matches_2v2(league_name, week, participants)
        match_data["league_matches"][league_name][week] = matches
        save_data()
        return
    
    # 1v1 path (existing)
    match_history = get_match_history(league_name)
    bye_history = get_bye_history(league_name)
    matches = generate_optimal_pairings(participants, match_history, bye_history, week)
    match_data["league_matches"][league_name][week] = matches
    save_data()


def get_match_history(league_name: str) -> Dict[tuple, int]:
    """Get how many times each pair of players has faced each other"""
    match_history = {}
    
    for week_num, week_matches in match_data["league_matches"].get(league_name, {}).items():
        for match in week_matches:
            # 1v1 historical matches
            if match.get("player2") is not None and match.get("status") in ["completed", "forfeited", "scheduled"] and "player1" in match:
                player_pair = tuple(sorted([match["player1"], match["player2"]]))
                match_history[player_pair] = match_history.get(player_pair, 0) + 1
            # 2v2 historical opponent pairs (count each individual vs individual) for opponent pressure
            if match.get("team1") and match.get("team2") and match.get("status") in ["completed", "forfeited", "scheduled"]:
                for a in match["team1"]:
                    for b in match["team2"]:
                        pair = tuple(sorted([a, b]))
                        match_history[pair] = match_history.get(pair, 0) + 1
    
    return match_history


def get_bye_history(league_name: str) -> Dict[int, int]:
    """Get how many BYEs each player has received (1v1 or 2v2)"""
    bye_history = {}
    
    for week_num, week_matches in match_data["league_matches"].get(league_name, {}).items():
        for match in week_matches:
            if match.get("status") == "bye":
                # 1v1 bye
                if match.get("player2") is None and match.get("player1") is not None:
                    player_id = match["player1"]
                    bye_history[player_id] = bye_history.get(player_id, 0) + 1
                # 2v2 team bye
                if match.get("team1") and not match.get("team2"):
                    for pid in match["team1"]:
                        bye_history[pid] = bye_history.get(pid, 0) + 1
    
    return bye_history


def get_teammate_history(league_name: str) -> Dict[tuple, int]:
    """Count how many times two users have been teammates in 2v2."""
    teammate_history: Dict[tuple, int] = {}
    for week_num, week_matches in match_data["league_matches"].get(league_name, {}).items():
        for match in week_matches:
            if match.get("team1"):
                t1 = match["team1"]
                if len(t1) == 2:
                    key = tuple(sorted(t1))
                    teammate_history[key] = teammate_history.get(key, 0) + 1
            if match.get("team2"):
                t2 = match["team2"]
                if len(t2) == 2:
                    key = tuple(sorted(t2))
                    teammate_history[key] = teammate_history.get(key, 0) + 1
    return teammate_history


def generate_week_matches_2v2(league_name: str, week: int, participants: List[int]) -> List[Dict]:
    """Generate 2v2 matches: form teams minimizing repeat teammates; pair teams minimizing repeat opponents; rotate byes evenly."""
    if len(participants) < 2:
        return []
    
    bye_history = get_bye_history(league_name)
    teammate_history = get_teammate_history(league_name)
    opponent_history = get_match_history(league_name)  # reuse individual-vs-individual counts
    
    players_pool = participants.copy()
    players_pool_set = set(players_pool)
    
    # Assign individual bye if odd number of players
    byes: List[Dict] = []
    if len(players_pool) % 2 == 1:
        # pick player with fewest byes
        min_byes = min(bye_history.get(p, 0) for p in players_pool)
        candidates = [p for p in players_pool if bye_history.get(p, 0) == min_byes]
        bye_player = candidates[0]
        players_pool.remove(bye_player)
        byes.append({
            "week": week,
            "player1": bye_player,
            "player2": None,
            "status": "bye",
            "result": "bye",
            "scheduled_date": None,
            "completed_date": None
        })
    
    # Form teams from remaining players (greedy, minimize teammate repeats)
    teams: List[List[int]] = []
    used: set = set()
    # sort players by number of times they've played (approximate via opponent_history degree + teammate_history degree)
    def player_load(p: int) -> int:
        opp = sum(ct for (a,b), ct in opponent_history.items() if a == p or b == p)
        team = sum(ct for (a,b), ct in teammate_history.items() if a == p or b == p)
        return opp + team
    players_sorted = sorted(players_pool, key=player_load)
    while players_sorted:
        p = players_sorted.pop(0)
        if p in used:
            continue
        best_q = None
        best_score = float('inf')
        for q in players_sorted:
            if q in used or q == p:
                continue
            # high penalty if they teamed before
            team_penalty = teammate_history.get(tuple(sorted([p, q])), 0) * 1000
            # slight load balance penalty
            balance_penalty = abs(player_load(p) - player_load(q))
            score = team_penalty + balance_penalty
            if score < best_score:
                best_score = score
                best_q = q
        if best_q is not None:
            teams.append([p, best_q])
            used.add(p)
            used.add(best_q)
        # rebuild list without used
        players_sorted = [x for x in players_sorted if x not in used]
    
    # If odd number of teams, assign team bye to the team with fewest combined byes
    team_bye: Optional[List[int]] = None
    if len(teams) % 2 == 1:
        min_team_byes = float('inf')
        for t in teams:
            total_byes = bye_history.get(t[0], 0) + bye_history.get(t[1], 0)
            if total_byes < min_team_byes:
                min_team_byes = total_byes
                team_bye = t
        if team_bye:
            teams.remove(team_bye)
            byes.append({
                "week": week,
                "team1": team_bye,
                "team2": None,
                "status": "bye",
                "result": "bye",
                "scheduled_date": None,
                "completed_date": None
            })
    
    # Pair teams into matches, minimizing repeat opponents at individual level
    matches: List[Dict] = []
    teams_sorted = teams.copy()
    # Greedy: always take first team and find best opponent
    while len(teams_sorted) >= 2:
        t1 = teams_sorted.pop(0)
        best_t2 = None
        best_score = float('inf')
        for i in range(len(teams_sorted)):
            t2 = teams_sorted[i]
            # opponent penalty: sum of opponent_history across the 4 cross pairs
            opp_penalty = sum(opponent_history.get(tuple(sorted([a, b])), 0) for a in t1 for b in t2) * 100
            score = opp_penalty
            if score < best_score:
                best_score = score
                best_t2 = t2
        if best_t2 is not None:
            teams_sorted.remove(best_t2)
            matches.append({
                "week": week,
                "team1": t1,
                "team2": best_t2,
                "status": "scheduled",
                "result": None,
                "scheduled_date": None,
                "completed_date": None
            })
        else:
            break
    
    return matches + byes


def select_bye_player(participants: List[int], bye_history: Dict[int, int]) -> int:
    """Select the player who should get a BYE, prioritizing those with fewer BYEs"""
    if not participants:
        return None
    
    # Find the player with the fewest BYEs
    min_byes = float('inf')
    candidates = []
    
    for player in participants:
        byes = bye_history.get(player, 0)
        if byes < min_byes:
            min_byes = byes
            candidates = [player]
        elif byes == min_byes:
            candidates.append(player)
    
    # If multiple candidates, choose randomly for variety
    import random
    return random.choice(candidates)


def advance_league_week(league_name: str) -> bool:
    """Advance to the next week in a league"""
    if league_name not in match_data["leagues"]:
        return False
    
    league = match_data["leagues"][league_name]
    if league["status"] != "active":
        return False
    
    current_week = league["current_week"]
    if current_week >= league["season_length"]:
        league["status"] = "completed"
        save_data()
        
        # Send final rankings and season summary
        asyncio.create_task(send_league_completion_summary(league_name))
        
        return False
    
    # Process forfeits for current week
    process_week_forfeits(league_name, current_week)
    
    # Advance to next week
    league["current_week"] += 1
    
    # Generate matches for next week
    generate_week_matches(league_name, league["current_week"])
    
    save_data()
    return True


def process_week_forfeits(league_name: str, week: int):
    """Process forfeits for matches that didn't happen"""
    if league_name not in match_data["league_matches"] or week not in match_data["league_matches"][league_name]:
        return
    
    matches = match_data["league_matches"][league_name][week]
    sport = match_data["leagues"][league_name]["sport"]
    team_size = match_data["leagues"][league_name].get("team_size", 1)
    
    for match in matches:
        if match["status"] == "scheduled":
            if team_size == 1 and match.get("player1") is not None and match.get("player2") is not None:
                # 1v1: Both players lose maximum ELO
                player1_id = match["player1"]
                player2_id = match["player2"]
                player1_elo = get_elo(str(player1_id), sport)
                player2_elo = get_elo(str(player2_id), sport)
                new_player1_elo = max(100, player1_elo - K_FACTOR)
                new_player2_elo = max(100, player2_elo - K_FACTOR)
                set_elo(str(player1_id), sport, new_player1_elo)
                set_elo(str(player2_id), sport, new_player2_elo)
                match["status"] = "forfeited"
                match["result"] = "forfeit"
                match["completed_date"] = datetime.now().isoformat()
                update_league_standings(league_name, player1_id, "loss")
                update_league_standings(league_name, player2_id, "loss")
            elif team_size == 2 and match.get("team1") and match.get("team2"):
                # 2v2: All four players lose maximum ELO
                all_players = match["team1"] + match["team2"]
                for pid in all_players:
                    current_elo = get_elo(str(pid), sport)
                    set_elo(str(pid), sport, max(100, current_elo - K_FACTOR))
                    update_league_standings(league_name, pid, "loss")
                match["status"] = "forfeited"
                match["result"] = "forfeit"
                match["completed_date"] = datetime.now().isoformat()


def update_league_standings(league_name: str, user_id: int, result: str):
    """Update league standings for a user"""
    if league_name not in match_data["league_standings"]:
        return
    
    user_id_str = str(user_id)
    if user_id_str not in match_data["league_standings"][league_name]:
        return
    
    standings = match_data["league_standings"][league_name][user_id_str]
    
    if result == "win":
        standings["wins"] += 1
        standings["points"] += 3
    elif result == "loss":
        standings["losses"] += 1
        standings["points"] += 0
    elif result == "draw":
        standings["points"] += 1
    
    # Update current ELO
    sport = match_data["leagues"][league_name]["sport"]
    standings["elo"] = get_elo(user_id_str, sport)
    
    save_data()


def record_league_match_result(league_name: str, week: int, player1_id: int, 
                              player2_id: int, winner_id: int, score: str):
    """Record the result of a league match"""
    if league_name not in match_data["league_matches"] or week not in match_data["league_matches"][league_name]:
        return False
    
    matches = match_data["league_matches"][league_name][week]
    
    for match in matches:
        if (match["player1"] == player1_id and match["player2"] == player2_id) or \
           (match["player1"] == player2_id and match["player2"] == player1_id):
            
            if match["status"] != "scheduled":
                return False
            
            match["status"] = "completed"
            match["result"] = f"{winner_id}_{score}"
            match["completed_date"] = datetime.now().isoformat()
            
            # Update ELO
            sport = match_data["leagues"][league_name]["sport"]
            if winner_id == player1_id:
                update_elo_winner_loser([player1_id], [player2_id], sport)
                update_league_standings(league_name, player1_id, "win")
                update_league_standings(league_name, player2_id, "loss")
                
                # Check for naked lap (loser scored 0 points)
                if score and score.split("-")[1].strip() == "0":
                    match_data["naked_laps"][str(player2_id)] = (
                        match_data["naked_laps"].get(str(player2_id), 0) + 1
                    )
            else:
                update_elo_winner_loser([player2_id], [player1_id], sport)
                update_league_standings(league_name, player2_id, "win")
                update_league_standings(league_name, player1_id, "loss")
                
                # Check for naked lap (loser scored 0 points)
                if score and score.split("-")[1].strip() == "0":
                    match_data["naked_laps"][str(player1_id)] = (
                        match_data["naked_laps"].get(str(player1_id), 0) + 1
                    )
            
            save_data()
            return True
    
    return False


def record_league_match_result_2v2(league_name: str, week: int, team1: List[int], team2: List[int], winner_team: int, score: str) -> bool:
    """Record the result of a 2v2 league match"""
    if league_name not in match_data["leagues"] or week not in match_data["league_matches"][league_name]:
        return False
    
    matches = match_data["league_matches"][league_name][week]
    
    for match in matches:
        if (match["team1"] == team1 and match["team2"] == team2) or \
           (match["team1"] == team2 and match["team2"] == team1):
            
            if match["status"] != "scheduled":
                return False
            
            match["status"] = "completed"
            match["result"] = f"{winner_team}_{score}"
            match["completed_date"] = datetime.now().isoformat()
            
            # Update ELO
            sport = match_data["leagues"][league_name]["sport"]
            if winner_team == 1:
                update_elo_winner_loser(team1, team2, sport)
                for uid in team1:
                    update_league_standings(league_name, uid, "win")
                for uid in team2:
                    update_league_standings(league_name, uid, "loss")
                
                # Check for naked lap (losing team scored 0 points)
                if score and score.split("-")[1].strip() == "0":
                    for uid in team2:
                        match_data["naked_laps"][str(uid)] = (
                            match_data["naked_laps"].get(str(uid), 0) + 1
                        )
            else:
                update_elo_winner_loser(team2, team1, sport)
                for uid in team2:
                    update_league_standings(league_name, uid, "win")
                for uid in team1:
                    update_league_standings(league_name, uid, "loss")
                
                # Check for naked lap (losing team scored 0 points)
                if score and score.split("-")[1].strip() == "0":
                    for uid in team1:
                        match_data["naked_laps"][str(uid)] = (
                            match_data["naked_laps"].get(str(uid), 0) + 1
                        )
            
            save_data()
            return True
    
    return False


# Admin Management Functions
def is_admin(user_id: int) -> bool:
    """Check if a user is an admin"""
    return user_id in match_data.get("admins", [])


def add_admin(user_id: int) -> bool:
    """Add a user as an admin"""
    if user_id not in match_data["admins"]:
        match_data["admins"].append(user_id)
        save_data()
        return True
    return False


def remove_admin(user_id: int) -> bool:
    """Remove a user's admin status"""
    if user_id in match_data["admins"]:
        match_data["admins"].remove(user_id)
        save_data()
        return True
    return False


def get_admins() -> List[int]:
    """Get list of admin user IDs"""
    return match_data.get("admins", [])


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


# League UI Components
class LeagueSignupView(View):
    def __init__(self, league_name: str):
        super().__init__(timeout=None)  # No timeout for signup buttons
        self.league_name = league_name

    async def update_signup_message(self, interaction: discord.Interaction):
        """Update the signup message with current participant list"""
        if self.league_name not in match_data["leagues"]:
            return
        
        league = match_data["leagues"][self.league_name]
        signups = match_data["league_signups"][self.league_name]
        
        # Get participant names with ELO and naked laps
        participant_lines = []
        for user_id in signups:
            display_name, elo, naked_laps = await get_user_display_info(user_id, league["sport"], interaction.guild)
            participant_lines.append(f"• **{display_name}** (ELO: {elo}) 🩲{naked_laps}")
        
        # Create updated message
        updated_content = (
            f"🏆 **League Created: {self.league_name}** 🏆\n"
            f"🎯 **Sport**: {league['sport'].title()}\n"
            f"👥 **Format**: {league['team_size']}v{league['team_size']}\n"
            f"📅 **Season Length**: {league['season_length']} weeks\n"
            f"⏰ **Signup Deadline**: {league['signup_deadline']}\n"
            f"📆 **Match Day**: {league['match_day']}\n\n"
            f"**Current Participants ({len(signups)}):**\n" + 
            ("\n".join(participant_lines) if participant_lines else "No participants yet") +
            f"\n\nPlayers can now sign up using the buttons below!"
        )
        
        try:
            await interaction.message.edit(content=updated_content, view=self)
        except:
            pass  # If we can't edit the message, continue silently

    @discord.ui.button(label="✅ Sign Up", style=discord.ButtonStyle.success, custom_id="signup")
    async def signup(self, interaction: discord.Interaction, button: Button):
        if add_participant_to_league(self.league_name, interaction.user.id):
            await interaction.response.send_message(
                f"✅ You've signed up for **{self.league_name}**!", ephemeral=True
            )
            # Update the signup message
            await self.update_signup_message(interaction)
        else:
            await interaction.response.send_message(
                f"❌ Failed to sign up for **{self.league_name}**. League may not be accepting signups.", ephemeral=True
            )

    @discord.ui.button(label="❌ Withdraw", style=discord.ButtonStyle.danger, custom_id="withdraw")
    async def withdraw(self, interaction: discord.Interaction, button: Button):
        if remove_participant_from_league(self.league_name, interaction.user.id):
            await interaction.response.send_message(
                f"✅ You've withdrawn from **{self.league_name}**!", ephemeral=True
            )
            # Update the signup message
            await self.update_signup_message(interaction)
        else:
            await interaction.response.send_message(
                f"❌ Failed to withdraw from **{self.league_name}**. League may have already started.", ephemeral=True
            )


class LeagueMatchResultView(View):
    def __init__(self, league_name: str, week: int, player1_id: int, player2_id: int):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.league_name = league_name
        self.week = week
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.player1_confirmed = False
        self.player2_confirmed = False
        self.confirmed_winner = None
        self.confirmed_score = None

    @discord.ui.button(label="Player 1 Won", style=discord.ButtonStyle.primary, custom_id="player1_win")
    async def player1_win(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.player1_id, self.player2_id]:
            await interaction.response.send_message(
                "⛔ Only the players in this match can report results.", ephemeral=True
            )
            return
        
        # Record the first confirmation
        if interaction.user.id == self.player1_id:
            if not self.player1_confirmed:
                self.player1_confirmed = True
                self.confirmed_winner = self.player1_id
                self.confirmed_score = "1-0"
                await interaction.response.send_message(
                    "✅ You've confirmed **Player 1** won. Waiting for Player 2's confirmation...", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "⚠️ You've already confirmed this result.", ephemeral=True
                )
        elif interaction.user.id == self.player2_id:
            if not self.player2_confirmed:
                self.player2_confirmed = True
                self.confirmed_winner = self.player1_id
                self.confirmed_score = "1-0"
                await interaction.response.send_message(
                    "✅ You've confirmed **Player 1** won. Waiting for Player 1's confirmation...", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "⚠️ You've already confirmed this result.", ephemeral=True
                )
        
        # Check if both players have confirmed
        if self.player1_confirmed and self.player2_confirmed:
            await self.finalize_match(interaction)

    @discord.ui.button(label="Player 2 Won", style=discord.ButtonStyle.primary, custom_id="player2_win")
    async def player2_win(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.player1_id, self.player2_id]:
            await interaction.response.send_message(
                "⛔ Only the players in this match can report results.", ephemeral=True
            )
            return
        
        # Record the first confirmation
        if interaction.user.id == self.player1_id:
            if not self.player1_confirmed:
                self.player1_confirmed = True
                self.confirmed_winner = self.player2_id
                self.confirmed_score = "0-1"
                await interaction.response.send_message(
                    "✅ You've confirmed **Player 2** won. Waiting for Player 2's confirmation...", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "⚠️ You've already confirmed this result.", ephemeral=True
                )
        elif interaction.user.id == self.player2_id:
            if not self.player2_confirmed:
                self.player2_confirmed = True
                self.confirmed_winner = self.player2_id
                self.confirmed_score = "0-1"
                await interaction.response.send_message(
                    "✅ You've confirmed **Player 2** won. Waiting for Player 1's confirmation...", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "⚠️ You've already confirmed this result.", ephemeral=True
                )
        
        # Check if both players have confirmed
        if self.player1_confirmed and self.player2_confirmed:
            await self.finalize_match(interaction)

    async def finalize_match(self, interaction: discord.Interaction):
        """Finalize the match result after both players confirm"""
        if record_league_match_result(self.league_name, self.week, self.player1_id, 
                                    self.player2_id, self.confirmed_winner, self.confirmed_score):
            
            # Get player names for the final message
            try:
                player1 = await client.fetch_user(self.player1_id)
                player2 = await client.fetch_user(self.player2_id)
                winner = await client.fetch_user(self.confirmed_winner)
                
                await interaction.message.edit(
                    content=f"✅ **Match Result Confirmed!**\n"
                           f"🏆 **{winner.display_name}** defeated "
                           f"**{(player2.display_name if self.confirmed_winner == self.player1_id else player1.display_name)}**\n"
                           f"📊 Result recorded for Week {self.week}",
                    view=None
                )
            except:
                await interaction.message.edit(
                    content=f"✅ **Match Result Confirmed!**\n"
                           f"📊 Result recorded for Week {self.week}",
                    view=None
                )
        else:
            await interaction.response.send_message(
                "❌ Failed to record match result. Please contact an administrator.", ephemeral=True
            )


class LeagueMatchResultView2v2(View):
    def __init__(self, league_name: str, week: int, team1: List[int], team2: List[int]):
        super().__init__(timeout=600)
        self.league_name = league_name
        self.week = week
        self.team1 = team1
        self.team2 = team2
        self.team1_confirmed = False
        self.team2_confirmed = False
        self.confirmed_winner = None
        self.confirmed_score = None

    def _all_players(self) -> List[int]:
        return [*self.team1, *self.team2]

    def _is_player(self, user_id: int) -> bool:
        return user_id in self._all_players()

    def _get_player_team(self, user_id: int) -> int:
        """Return 1 if player is in team1, 2 if in team2, 0 if not found"""
        if user_id in self.team1:
            return 1
        elif user_id in self.team2:
            return 2
        return 0

    async def _handle_choice(self, interaction: discord.Interaction, chosen_team: int):
        if not self._is_player(interaction.user.id):
            await interaction.response.send_message(
                "⛔ Only the players in this match can report results.", ephemeral=True
            )
            return
        
        player_team = self._get_player_team(interaction.user.id)
        if player_team == 0:
            await interaction.response.send_message(
                "⛔ You are not a player in this match.", ephemeral=True
            )
            return

        # Check if this team has already confirmed
        if player_team == 1 and self.team1_confirmed:
            await interaction.response.send_message(
                "⚠️ Your team has already confirmed this result.", ephemeral=True
            )
            return
        elif player_team == 2 and self.team2_confirmed:
            await interaction.response.send_message(
                "⚠️ Your team has already confirmed this result.", ephemeral=True
            )
            return

        # Record the confirmation
        if player_team == 1:
            self.team1_confirmed = True
        else:
            self.team2_confirmed = True
        
        self.confirmed_winner = chosen_team
        self.confirmed_score = "1-0" if chosen_team == 1 else "0-1"

        # Check if both teams have confirmed
        if self.team1_confirmed and self.team2_confirmed:
            await self.finalize_match(interaction)
        else:
            waiting_team = "Team 2" if self.team1_confirmed else "Team 1"
            await interaction.response.send_message(
                f"✅ Your team has confirmed **Team {chosen_team}** won. Waiting for {waiting_team}'s confirmation...", 
                ephemeral=True
            )

    @discord.ui.button(label="Team 1 Won", style=discord.ButtonStyle.primary, custom_id="team1_win")
    async def team1_win(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, 1)

    @discord.ui.button(label="Team 2 Won", style=discord.ButtonStyle.primary, custom_id="team2_win")
    async def team2_win(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, 2)

    async def finalize_match(self, interaction: discord.Interaction):
        """Finalize the match result after both teams confirm"""
        ok = record_league_match_result_2v2(
            self.league_name, self.week, self.team1, self.team2, self.confirmed_winner, self.confirmed_score
        )
        if ok:
            try:
                team1_names = ", ".join([(await client.fetch_user(uid)).display_name for uid in self.team1])
                team2_names = ", ".join([(await client.fetch_user(uid)).display_name for uid in self.team2])
                await interaction.message.edit(
                    content=(
                        "✅ **Match Result Confirmed!**\n"
                        f"🏆 **Team {self.confirmed_winner}** won\n"
                        f"👥 Team 1: {team1_names}\n"
                        f"👥 Team 2: {team2_names}\n"
                        f"📊 Result recorded for Week {self.week}"
                    ),
                    view=None,
                )
            except:
                await interaction.message.edit(
                    content=(
                        "✅ **Match Result Confirmed!**\n"
                        f"🏆 Team {self.confirmed_winner} won\n"
                        f"📊 Result recorded for Week {self.week}"
                    ),
                    view=None,
                )
        else:
            await interaction.response.send_message(
                "❌ Failed to record match result. Please contact an administrator.", ephemeral=True
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
        display_name, _, naked_laps = await get_user_display_info(uid, sport, interaction.guild)
        lines.append(f"**#{rank}** – {display_name}: {elo} 🩲{naked_laps}")

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
        display_name, elo, naked_laps = await get_user_display_info(user_id, None, interaction.guild)
        await interaction.response.send_message(
            f"📭 No matches found for {display_name}."
        )
        return

    # Sort by most recent (optional)
    user_matches = user_matches[::-1]

    history_lines = []
    for match in user_matches[-10:]:  # show up to last 10
        sport = match["sport"]
        score = match.get("score", "N/A")
        
        # Get winner names with server nicknames
        winner_names = []
        for uid in match["winner_ids"]:
            display_name, _, _ = await get_user_display_info(uid, sport, interaction.guild)
            winner_names.append(display_name)
        winners = ", ".join(winner_names)
        
        # Get loser names with server nicknames
        loser_names = []
        for uid in match["loser_ids"]:
            display_name, _, _ = await get_user_display_info(uid, sport, interaction.guild)
            loser_names.append(display_name)
        losers = ", ".join(loser_names)
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
        display_name, _, _ = await get_user_display_info(int(uid), None, interaction.guild)
        lines.append(f"**#{rank}** – {display_name}: {count} naked lap(s)")

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
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to use this command.", ephemeral=True
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


# ------------------------------------------
# League Commands
# ------------------------------------------

@tree.command(
    name="create_league",
    description="(Admin only) Create a new league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(
    name="Name of the league",
    sport="Sport for the league",
    season_length="Number of weeks for the season",
    signup_deadline="Signup deadline (YYYY-MM-DD)",
    match_day="Day of the week for matches (Monday, Tuesday, etc.)",
    team_size="Team size (1 for 1v1, 2 for 2v2)"
)
async def create_league_cmd(
    interaction: discord.Interaction,
    name: str,
    sport: str,
    season_length: int,
    signup_deadline: str,
    match_day: str,
    team_size: int = 1
):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to create leagues.", ephemeral=True
        )
        return

    sport = sport.lower()
    if sport not in match_data["sports"]:
        await interaction.response.send_message(
            "❌ Sport not found. Use `/create_sport` first.", ephemeral=True
        )
        return

    if team_size not in [1, 2]:
        await interaction.response.send_message(
            "❌ Team size must be 1 (1v1) or 2 (2v2).", ephemeral=True
        )
        return

    if name in match_data["leagues"]:
        await interaction.response.send_message(
            f"⚠️ League **{name}** already exists.", ephemeral=True
        )
        return

    try:
        # Validate date format
        datetime.strptime(signup_deadline, "%Y-%m-%d")
    except ValueError:
        await interaction.response.send_message(
            "❌ Invalid date format. Use YYYY-MM-DD.", ephemeral=True
        )
        return

    if season_length < 1 or season_length > 52:
        await interaction.response.send_message(
            "❌ Season length must be between 1 and 52 weeks.", ephemeral=True
        )
        return

    league = create_league(
        name, sport, season_length, signup_deadline, 
        match_day, interaction.user.id, team_size
    )

    view = LeagueSignupView(name)
    
    await interaction.response.send_message(
        f"🏆 **League Created: {name}** 🏆\n"
        f"🎯 **Sport**: {sport.title()}\n"
        f"👥 **Format**: {team_size}v{team_size}\n"
        f"📅 **Season Length**: {season_length} weeks\n"
        f"⏰ **Signup Deadline**: {signup_deadline}\n"
        f"📆 **Match Day**: {match_day}\n\n"
        f"**Current Participants (0):**\nNo participants yet\n\n"
        f"Players can now sign up using the buttons below!",
        view=view
    )


@tree.command(
    name="league_info",
    description="Get information about a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league")
async def league_info(interaction: discord.Interaction, league_name: str):
    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    signups = match_data["league_signups"][league_name]
    
    # Get participant names
    participant_names = []
    for user_id in signups:
        try:
            user = await client.fetch_user(user_id)
            participant_names.append(user.display_name)
        except:
            participant_names.append(f"Unknown User ({user_id})")

    status_emoji = {
        "signup": "📝",
        "active": "🏃‍♂️",
        "completed": "🏆"
    }

    await interaction.response.send_message(
        f"{status_emoji.get(league['status'], '❓')} **League: {league_name}**\n"
        f"🎯 **Sport**: {league['sport'].title()}\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n"
        f"📅 **Season Length**: {league['season_length']} weeks\n"
        f"⏰ **Signup Deadline**: {league['signup_deadline']}\n"
        f"📆 **Match Day**: {league['match_day']}\n"
        f"🔄 **Status**: {league['status'].title()}\n"
        f"👥 **Participants**: {len(signups)}\n\n"
        f"**Participants**:\n" + "\n".join([f"• {name}" for name in participant_names])
    )


@tree.command(
    name="start_league",
    description="(Admin only) Start a league and generate first week matches",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league to start")
async def start_league_cmd(interaction: discord.Interaction, league_name: str):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to start leagues.", ephemeral=True
        )
        return

    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    if start_league(league_name):
        await interaction.response.send_message(
            f"🏃‍♂️ **League {league_name} has started!**\n"
            f"👥 **Format**: {match_data['leagues'][league_name]['team_size']}v{match_data['leagues'][league_name]['team_size']}\n"
            f"First week matches have been generated and sent to participants."
        )
        
        # Send match notifications to participants
        await send_week_matches(league_name, 1)
    else:
        await interaction.response.send_message(
            f"❌ Failed to start league **{league_name}**. Check if it's in signup status and has enough participants.",
            ephemeral=True
        )


@tree.command(
    name="resend_matches",
    description="(Admin only) Resend incomplete matches for the current week",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league")
async def resend_matches(interaction: discord.Interaction, league_name: str):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to resend matches.", ephemeral=True
        )
        return

    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    if league["status"] != "active":
        await interaction.response.send_message(
            f"❌ League **{league_name}** is not active. Current status: {league['status']}", ephemeral=True
        )
        return

    current_week = league["current_week"]
    if current_week not in match_data["league_matches"][league_name]:
        await interaction.response.send_message(
            f"❌ No matches found for week {current_week}.", ephemeral=True
        )
        return

    matches = match_data["league_matches"][league_name][current_week]
    incomplete_matches = [m for m in matches if m["status"] == "scheduled"]
    
    if not incomplete_matches:
        await interaction.response.send_message(
            f"✅ All matches for Week {current_week} have been completed or are already in progress.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"📤 Resending {len(incomplete_matches)} incomplete matches for Week {current_week}...\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}"
    )

    # Resend incomplete matches
    await resend_incomplete_matches(league_name, current_week, incomplete_matches)


@tree.command(
    name="complete_league",
    description="(Admin only) Manually complete a league and send final summary",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league to complete")
async def complete_league_cmd(interaction: discord.Interaction, league_name: str):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to complete leagues.", ephemeral=True
        )
        return

    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    if league["status"] != "active":
        await interaction.response.send_message(
            f"❌ League **{league_name}** is not active. Current status: {league['status']}", ephemeral=True
        )
        return

    # Mark league as completed
    league["status"] = "completed"
    save_data()

    await interaction.response.send_message(
        f"🏆 **League {league_name} has been completed!**\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n"
        f"Final summary and rankings will be sent to the channel."
    )

    # Send completion summary
    await send_league_completion_summary(league_name)


@tree.command(
    name="advance_week",
    description="(Admin only) Advance to the next week in a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league to advance")
async def advance_week_cmd(interaction: discord.Interaction, league_name: str):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to advance league weeks.", ephemeral=True
        )
        return

    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    if advance_league_week(league_name):
        league = match_data["leagues"][league_name]
        if league["status"] == "completed":
            await interaction.response.send_message(
                f"🏆 **League {league_name} has completed!**\n"
                f"Final standings are available."
            )
        else:
            await interaction.response.send_message(
                f"📅 **Week {league['current_week']}** has started for **{league_name}**!\n"
                f"👥 **Format**: {league['team_size']}v{league['team_size']}\n"
                f"New matches have been generated and sent to participants."
            )
            
            # Send match notifications for new week
            await send_week_matches(league_name, league["current_week"])
    else:
        await interaction.response.send_message(
            f"❌ Failed to advance week for **{league_name}**. League may not be active or may have completed.",
            ephemeral=True
        )


@tree.command(
    name="league_standings",
    description="Show current standings for a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league")
async def league_standings(interaction: discord.Interaction, league_name: str):
    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    if league_name not in match_data["league_standings"]:
        await interaction.response.send_message(
            "❌ No standings available for this league yet.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    standings = match_data["league_standings"][league_name]
    
    if not standings:
        await interaction.response.send_message(
            "❌ No standings available for this league yet.", ephemeral=True
        )
        return

    # Sort by points, then by wins, then by ELO
    sorted_standings = sorted(
        standings.items(),
        key=lambda x: (x[1]["points"], x[1]["wins"], x[1]["elo"]),
        reverse=True
    )

    lines = []
    for rank, (user_id, stats) in enumerate(sorted_standings, start=1):
        display_name, elo, naked_laps = await get_user_display_info(int(user_id), league["sport"], interaction.guild)
        lines.append(
            f"**#{rank}** – {display_name}: {stats['points']}pts "
            f"({stats['wins']}W/{stats['losses']}L) ELO: {elo} "
            f"🩲{naked_laps}"
        )

    await interaction.response.send_message(
        f"🏆 **{league_name} League Standings** 🏆\n"
        f"👥 **Format**: {match_data["leagues"][league_name]["team_size"]}v{match_data["leagues"][league_name]["team_size"]}\n" + "\n".join(lines)
    )


@tree.command(
    name="league_matches",
    description="Show matches for a specific week in a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(
    league_name="Name of the league",
    week="Week number (optional, shows current week if not specified)"
)
async def league_matches(interaction: discord.Interaction, league_name: str, week: int = None):
    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    
    if week is None:
        week = league["current_week"]
    
    if week not in match_data["league_matches"][league_name]:
        await interaction.response.send_message(
            f"❌ No matches found for week {week}.", ephemeral=True
        )
        return

    matches = match_data["league_matches"][league_name][week]
    
    if not matches:
        await interaction.response.send_message(
            f"❌ No matches scheduled for week {week}.", ephemeral=True
        )
        return

    lines = []
    for match in matches:
        if match["player2"] is None:  # Bye
            try:
                player1 = await client.fetch_user(match["player1"])
                lines.append(f"🆓 **{player1.display_name}** has a BYE this week")
            except:
                lines.append(f"🆓 **Unknown User ({match['player1']})** has a BYE this week")
        else:
            try:
                player1 = await client.fetch_user(match["player1"])
                player2 = await client.fetch_user(match["player2"])
                
                status_emoji = {
                    "scheduled": "⏰",
                    "completed": "✅",
                    "forfeited": "❌"
                }
                
                status = status_emoji.get(match["status"], "❓")
                lines.append(
                    f"{status} **{player1.display_name}** vs **{player2.display_name}** "
                    f"({match['status'].title()})"
                )
            except:
                lines.append(f"❓ **Unknown User** vs **Unknown User** ({match['status'].title()})")

    await interaction.response.send_message(
        f"📅 **{league_name} - Week {week} Matches** 📅\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n" + "\n".join(lines)
    )


@tree.command(
    name="list_leagues",
    description="List all available leagues",
    guild=discord.Object(id=GUILD_ID),
)
async def list_leagues(interaction: discord.Interaction):
    if not match_data["leagues"]:
        await interaction.response.send_message(
            "📭 No leagues have been created yet."
        )
        return

    lines = []
    for name, league in match_data["leagues"].items():
        status_emoji = {
            "signup": "📝",
            "active": "🏃‍♂️",
            "completed": "🏆"
        }
        
        signup_count = len(match_data["league_signups"].get(name, []))
        lines.append(
            f"{status_emoji.get(league['status'], '❓')} **{name}** "
            f"({league['sport'].title()}) - {league['team_size']}v{league['team_size']} - {league['status'].title()} "
            f"[{signup_count} participants]"
        )

    await interaction.response.send_message(
        "🏆 **Available Leagues** 🏆\n" + "\n".join(lines)
    )


@tree.command(
    name="league_match_status",
    description="Check the status and confirmation of league matches",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(
    league_name="Name of the league",
    week="Week number (optional, shows current week if not specified)"
)
async def league_match_status(interaction: discord.Interaction, league_name: str, week: int = None):
    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    
    if week is None:
        week = league["current_week"]
    
    if week not in match_data["league_matches"][league_name]:
        await interaction.response.send_message(
            f"❌ No matches found for week {week}.", ephemeral=True
        )
        return

    matches = match_data["league_matches"][league_name][week]
    
    if not matches:
        await interaction.response.send_message(
            f"❌ No matches scheduled for week {week}.", ephemeral=True
        )
        return

    lines = []
    for match in matches:
        if match["player2"] is None:  # Bye
            try:
                player1 = await client.fetch_user(match["player1"])
                lines.append(f"🆓 **{player1.display_name}** has a BYE this week")
            except:
                lines.append(f"🆓 **Unknown User ({match['player1']})** has a BYE this week")
        else:
            try:
                player1 = await client.fetch_user(match["player1"])
                player2 = await client.fetch_user(match["player2"])
                
                status_emoji = {
                    "scheduled": "⏰",
                    "completed": "✅",
                    "forfeited": "❌"
                }
                
                status = status_emoji.get(match["status"], "❓")
                
                if match["status"] == "scheduled":
                    lines.append(
                        f"{status} **{player1.display_name}** vs **{player2.display_name}**\n"
                        f"   📋 Status: {match['status'].title()} - Waiting for both players to confirm"
                    )
                else:
                    lines.append(
                        f"{status} **{player1.display_name}** vs **{player2.display_name}**\n"
                        f"   📋 Status: {match['status'].title()}"
                    )
            except:
                lines.append(f"❓ **Unknown User** vs **Unknown User** ({match['status'].title()})")

    await interaction.response.send_message(
        f"📅 **{league_name} - Week {week} Match Status** 📅\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n" + "\n".join(lines)
    )


@tree.command(
    name="league_match_history",
    description="Show detailed match history and BYE distribution for a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league")
async def league_match_history(interaction: discord.Interaction, league_name: str):
    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    matches = match_data["league_matches"].get(league_name, {})
    
    if not matches:
        await interaction.response.send_message(
            "❌ No matches found for this league yet.", ephemeral=True
        )
        return

    # Get match history
    match_history = get_match_history(league_name)
    bye_history = get_bye_history(league_name)
    
    # Show BYE distribution and naked laps
    bye_lines = []
    for user_id in league["participants"]:
        display_name, elo, naked_laps = await get_user_display_info(user_id, league["sport"], interaction.guild)
        byes = bye_history.get(user_id, 0)
        bye_lines.append(f"• **{display_name}**: {byes} BYE(s) 🩲{naked_laps}")
    
    # Show repeated matchups
    repeat_lines = []
    for (player1_id, player2_id), count in match_history.items():
        if count > 1:  # Only show if they've played more than once
            try:
                player1 = await client.fetch_user(player1_id)
                player2 = await client.fetch_user(player2_id)
                repeat_lines.append(f"• **{player1.display_name}** vs **{player2.display_name}**: {count} times")
            except:
                repeat_lines.append(f"• **Unknown User ({player1_id})** vs **Unknown User ({player2_id})**: {count} times")
    
    # Show weekly match summary
    week_lines = []
    for week_num in sorted(matches.keys()):
        week_matches = matches[week_num]
        completed = sum(1 for m in week_matches if m["status"] == "completed")
        forfeited = sum(1 for m in week_matches if m["status"] == "forfeited")
        scheduled = sum(1 for m in week_matches if m["status"] == "scheduled")
        byes = sum(1 for m in week_matches if m["status"] == "bye")
        
        week_lines.append(f"**Week {week_num}**: {completed} completed, {forfeited} forfeited, {scheduled} scheduled, {byes} BYE(s)")
    
    await interaction.response.send_message(
        f"📊 **{league_name} Match History & Analysis** 📊\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n\n"
        f"🏆 **BYE Distribution** (should be even):\n" + "\n".join(bye_lines) + "\n\n"
        f"🔄 **Repeated Matchups** (should be minimized):\n" + 
        ("\n".join(repeat_lines) if repeat_lines else "✅ No repeated matchups!") + "\n\n"
        f"📅 **Weekly Summary**:\n" + "\n".join(week_lines)
    )


@tree.command(
    name="league_stats",
    description="Show detailed statistics for a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league")
async def league_stats(interaction: discord.Interaction, league_name: str):
    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    standings = match_data["league_standings"].get(league_name, {})
    matches = match_data["league_matches"].get(league_name, {})
    
    # Calculate statistics
    total_matches = 0
    completed_matches = 0
    forfeited_matches = 0
    
    for week_matches in matches.values():
        for match in week_matches:
            total_matches += 1
            if match["status"] == "completed":
                completed_matches += 1
            elif match["status"] == "forfeited":
                forfeited_matches += 1
    
    # Calculate average ELO
    if standings:
        avg_elo = sum(stats["elo"] for stats in standings.values()) / len(standings)
        highest_elo = max(stats["elo"] for stats in standings.values())
        lowest_elo = min(stats["elo"] for stats in standings.values())
    else:
        avg_elo = highest_elo = lowest_elo = 0
    
    # Calculate completion rate
    completion_rate = (completed_matches / total_matches * 100) if total_matches > 0 else 0
    
    status_emoji = {
        "signup": "📝",
        "active": "🏃‍♂️",
        "completed": "🏆"
    }
    
    await interaction.response.send_message(
        f"{status_emoji.get(league['status'], '❓')} **{league_name} Statistics**\n"
        f"🎯 **Sport**: {league['sport'].title()}\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n"
        f"📅 **Season Length**: {league['season_length']} weeks\n"
        f"🔄 **Status**: {league['status'].title()}\n"
        f"📊 **Current Week**: {league['current_week']}\n"
        f"👥 **Participants**: {len(league['participants'])}\n\n"
        f"📈 **Match Statistics**:\n"
        f"• Total Matches: {total_matches}\n"
        f"• Completed: {completed_matches}\n"
        f"• Forfeited: {forfeited_matches}\n"
        f"• Completion Rate: {completion_rate:.1f}%\n\n"
        f"🏆 **ELO Statistics**:\n"
        f"• Average ELO: {avg_elo:.1f}\n"
        f"• Highest ELO: {highest_elo:.1f}\n"
        f"• Lowest ELO: {lowest_elo:.1f}"
    )


@tree.command(
    name="extend_signup",
    description="(Admin only) Extend the signup deadline for a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(
    league_name="Name of the league",
    new_deadline="New signup deadline (YYYY-MM-DD)"
)
async def extend_signup(interaction: discord.Interaction, league_name: str, new_deadline: str):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to extend signup deadlines.", ephemeral=True
        )
        return

    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    league = match_data["leagues"][league_name]
    if league["status"] != "signup":
        await interaction.response.send_message(
            f"❌ Cannot extend deadline for **{league_name}**. League has already started.", ephemeral=True
        )
        return

    try:
        # Validate date format
        datetime.strptime(new_deadline, "%Y-%m-%d")
    except ValueError:
        await interaction.response.send_message(
            "❌ Invalid date format. Use YYYY-MM-DD.", ephemeral=True
        )
        return

    old_deadline = league["signup_deadline"]
    league["signup_deadline"] = new_deadline
    save_data()

    await interaction.response.send_message(
        f"⏰ **Signup deadline extended for {league_name}**\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n"
        f"📅 **Old deadline**: {old_deadline}\n"
        f"📅 **New deadline**: {new_deadline}"
    )


@tree.command(
    name="delete_league",
    description="(Admin only) Delete a league and all its data",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league to delete")
async def delete_league(interaction: discord.Interaction, league_name: str):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to delete leagues.", ephemeral=True
        )
        return

    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    # Remove all league data
    del match_data["leagues"][league_name]
    if league_name in match_data["league_signups"]:
        del match_data["league_signups"][league_name]
    if league_name in match_data["league_matches"]:
        del match_data["league_matches"][league_name]
    if league_name in match_data["league_standings"]:
        del match_data["league_standings"][league_name]
    
    save_data()
    
    await interaction.response.send_message(
        f"🗑️ **League {league_name} has been deleted** along with all its data.\n"
        f"👥 **Format**: {match_data['leagues'][league_name]['team_size']}v{match_data['leagues'][league_name]['team_size']}"
    )


@tree.command(
    name="league_signups",
    description="Show current signups for a league",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(league_name="Name of the league")
async def league_signups(interaction: discord.Interaction, league_name: str):
    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return
    
    league = match_data["leagues"][league_name]
    signups = match_data["league_signups"][league_name]
    
    if not signups:
        await interaction.response.send_message(
            f"📭 No one has signed up for **{league_name}** yet."
        )
        return
    
    # Get participant names, ELO, and naked laps
    participant_lines = []
    for user_id in signups:
        display_name, elo, naked_laps = await get_user_display_info(user_id, league["sport"], interaction.guild)
        participant_lines.append(f"• **{display_name}** (ELO: {elo}) 🩲{naked_laps}")
    
    status_emoji = {
        "signup": "📝",
        "active": "🏃‍♂️",
        "completed": "🏆"
    }
    
    await interaction.response.send_message(
        f"{status_emoji.get(league['status'], '❓')} **{league_name} Signups**\n"
        f"🎯 **Sport**: {league['sport'].title()}\n"
        f"👥 **Format**: {league['team_size']}v{league['team_size']}\n"
        f"📅 **Season Length**: {league['season_length']} weeks\n"
        f"⏰ **Signup Deadline**: {league['signup_deadline']}\n"
        f"📆 **Match Day**: {league['match_day']}\n"
        f"🔄 **Status**: {league['status'].title()}\n"
        f"👥 **Participants**: {len(signups)}\n\n"
        f"**Current Signups**:\n" + "\n".join(participant_lines)
    )


@tree.command(
    name="my_leagues",
    description="Show leagues you're signed up for",
    guild=discord.Object(id=GUILD_ID),
)
async def my_leagues(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_leagues = []
    
    for league_name, signups in match_data["league_signups"].items():
        if user_id in signups:
            league = match_data["leagues"][league_name]
            status_emoji = {
                "signup": "📝",
                "active": "🏃‍♂️",
                "completed": "🏆"
            }
            
            user_leagues.append(
                f"{status_emoji.get(league['status'], '❓')} **{league_name}** "
                f"({league['sport'].title()}) - {league['team_size']}v{league['team_size']} - {league['status'].title()}"
            )
    
    if not user_leagues:
        await interaction.response.send_message(
            "📭 You're not signed up for any leagues."
        )
        return
    
    await interaction.response.send_message(
        "🏆 **Your Leagues** 🏆\n" + "\n".join(user_leagues)
    )


@tree.command(
    name="record_league_result",
    description="(Admin only) Manually record a league match result",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(
    league_name="Name of the league",
    week="Week number",
    player1="First player",
    player2="Second player",
    winner="Winner of the match",
    score="Match score (e.g., 2-1)"
)
async def record_league_result_cmd(
    interaction: discord.Interaction,
    league_name: str,
    week: int,
    player1: discord.Member,
    player2: discord.Member,
    winner: discord.Member,
    score: str
):
    # Admin-only check
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to record league results.", ephemeral=True
        )
        return

    if league_name not in match_data["leagues"]:
        await interaction.response.send_message(
            "❌ League not found.", ephemeral=True
        )
        return

    if winner not in [player1, player2]:
        await interaction.response.send_message(
            "❌ Winner must be one of the two players in the match.", ephemeral=True
        )
        return

    if record_league_match_result(league_name, week, player1.id, player2.id, winner.id, score):
        await interaction.response.send_message(
            f"✅ League match result recorded!\n"
            f"👥 **Format**: {match_data['leagues'][league_name]['team_size']}v{match_data['leagues'][league_name]['team_size']}\n"
            f"**{winner.display_name}** defeated **{(player2 if winner == player1 else player1).display_name}** "
            f"in Week {week} of {league_name}."
        )
    else:
        await interaction.response.send_message(
            f"❌ Failed to record league match result. Check if the match exists and hasn't been completed.",
            ephemeral=True
        )


# ------------------------------------------
# Admin Management Commands
# ------------------------------------------

@tree.command(
    name="admin_add",
    description="(Owner only) Add a user as an admin",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(user="User to make admin")
async def admin_add(interaction: discord.Interaction, user: discord.Member):
    # Check if the user is the bot owner (you can customize this)
    # For now, we'll use the first admin in the list as the owner
    admins = get_admins()
    if not admins:
        # If no admins exist, allow the first user to add themselves
        if add_admin(interaction.user.id):
            await interaction.response.send_message(
                f"✅ You've been added as the first admin!", ephemeral=True
            )
        return
    
    # Check if the user is already an admin
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to add other admins.", ephemeral=True
        )
        return
    
    # Check if the target user is already an admin
    if is_admin(user.id):
        await interaction.response.send_message(
            f"⚠️ **{user.display_name}** is already an admin.", ephemeral=True
        )
        return
    
    # Add the user as admin
    if add_admin(user.id):
        await interaction.response.send_message(
            f"✅ **{user.display_name}** has been added as an admin!"
        )
    else:
        await interaction.response.send_message(
            f"❌ Failed to add **{user.display_name}** as admin.", ephemeral=True
        )


@tree.command(
    name="admin_remove",
    description="(Owner only) Remove a user's admin status",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(user="User to remove admin status from")
async def admin_remove(interaction: discord.Interaction, user: discord.Member):
    # Check if the user is an admin
    if not is_admin(interaction.user.id):
        await interaction.response.send_message(
            "⛔ You must be an admin to remove other admins.", ephemeral=True
        )
        return
    
    # Check if the target user is an admin
    if not is_admin(user.id):
        await interaction.response.send_message(
            f"⚠️ **{user.display_name}** is not an admin.", ephemeral=True
        )
        return
    
    # Prevent removing the last admin
    admins = get_admins()
    if len(admins) == 1 and user.id in admins:
        await interaction.response.send_message(
            "❌ Cannot remove the last admin. Add another admin first.", ephemeral=True
        )
        return
    
    # Remove admin status
    if remove_admin(user.id):
        await interaction.response.send_message(
            f"✅ **{user.display_name}** has been removed as an admin."
        )
    else:
        await interaction.response.send_message(
            f"❌ Failed to remove **{user.display_name}** as admin.", ephemeral=True
        )


@tree.command(
    name="admin_list",
    description="Show current admin users",
    guild=discord.Object(id=GUILD_ID),
)
async def admin_list(interaction: discord.Interaction):
    admins = get_admins()
    
    if not admins:
        await interaction.response.send_message(
            "📭 No admins have been set up yet."
        )
        return
    
    admin_lines = []
    for admin_id in admins:
        try:
            user = await client.fetch_user(admin_id)
            admin_lines.append(f"• **{user.display_name}** ({user.mention})")
        except:
            admin_lines.append(f"• **Unknown User** ({admin_id})")
    
    await interaction.response.send_message(
        "👑 **Current Admins** 👑\n" + "\n".join(admin_lines)
    )


@tree.command(
    name="admin_check",
    description="Check if you have admin permissions",
    guild=discord.Object(id=GUILD_ID),
)
async def admin_check(interaction: discord.Interaction):
    if is_admin(interaction.user.id):
        await interaction.response.send_message(
            "✅ You have admin permissions!", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ You do not have admin permissions.", ephemeral=True
        )


# Helper function to send week matches to participants
async def send_week_matches(league_name: str, week: int):
    """Send match notifications to participants for a specific week"""
    if league_name not in match_data["leagues"] or week not in match_data["league_matches"][league_name]:
        return
    
    league = match_data["leagues"][league_name]
    matches = match_data["league_matches"][league_name][week]
    
    # Get the channel where the league was created (you might want to store this in league data)
    # For now, we'll try to send to the first available guild channel
    
    try:
        guild = client.get_guild(GUILD_ID)
        if guild:
            # Try to find a general channel or the first text channel
            channel = guild.system_channel or guild.text_channels[0]
            
            match_lines = []
            for match in matches:
                if league.get("team_size", 1) == 2:
                    # 2v2 rendering
                    if match.get("team2") is None and match.get("team1"):
                        try:
                            t1_names = ", ".join([(await client.fetch_user(uid)).display_name for uid in match["team1"]])
                            match_lines.append(f"🆓 **{t1_names}** have a BYE this week")
                        except:
                            match_lines.append(f"🆓 **Team** has a BYE this week")
                    else:
                        try:
                            t1_users = [await client.fetch_user(uid) for uid in match["team1"]]
                            t2_users = [await client.fetch_user(uid) for uid in match["team2"]]
                            t1_mentions = ", ".join([u.mention for u in t1_users])
                            t2_mentions = ", ".join([u.mention for u in t2_users])
                            t1_names = ", ".join([u.display_name for u in t1_users])
                            t2_names = ", ".join([u.display_name for u in t2_users])
                            match_lines.append(
                                f"⚔️ **{t1_names}** vs **{t2_names}**"
                            )
                            view = LeagueMatchResultView2v2(league_name, week, match["team1"], match["team2"])
                            await channel.send(
                                f"🏆 **{league_name} - Week {week}**\n"
                                f"👥 **Team 1**: {t1_mentions}\n"
                                f"👥 **Team 2**: {t2_mentions}\n"
                                f"Both teams must have all players confirm the result using the buttons below:",
                                view=view
                            )
                        except Exception as e:
                            print(f"Error sending 2v2 match notification: {e}")
                else:
                    # 1v1 rendering (existing)
                    if match["player2"] is None:  # Bye
                        try:
                            player1 = await client.fetch_user(match["player1"])
                            match_lines.append(f"🆓 **{player1.display_name}** has a BYE this week")
                        except:
                            match_lines.append(f"🆓 **Unknown User ({match['player1']})** has a BYE this week")
                    else:
                        try:
                            player1 = await client.fetch_user(match["player1"])
                            player2 = await client.fetch_user(match["player2"])
                            
                            match_lines.append(
                                f"⚔️ **{player1.display_name}** vs **{player2.display_name}**"
                            )
                            
                            # Send individual match notifications with result buttons
                            view = LeagueMatchResultView(league_name, week, match["player1"], match["player2"])
                            await channel.send(
                                f"🏆 **{league_name} - Week {week}**\n"
                                f"⚔️ **{player1.mention}** vs **{player2.mention}**\n"
                                f"Both players must confirm the result using the buttons below:",
                                view=view
                            )
                        except Exception as e:
                            print(f"Error sending match notification: {e}")
            
            # Send general week announcement
            if match_lines:
                await channel.send(
                    f"📅 **{league_name} - Week {week} Matches** 📅\n"
                    f"👥 **Format**: {league['team_size']}v{league['team_size']}\n" + "\n".join(match_lines)
                )
    except Exception as e:
        print(f"Error sending week matches: {e}")


async def resend_incomplete_matches(league_name: str, week: int, incomplete_matches: List[Dict]):
    """Resend incomplete matches for a specific week"""
    if not incomplete_matches:
        return
    
    try:
        guild = client.get_guild(GUILD_ID)
        if guild:
            # Try to find a general channel or the first text channel
            channel = guild.system_channel or guild.text_channels[0]
            
            # Send a header message
            await channel.send(
                f"🔄 **{league_name} - Week {week} - Resending Incomplete Matches** 🔄\n"
                f"👥 **Format**: {match_data['leagues'][league_name]['team_size']}v{match_data['leagues'][league_name]['team_size']}\n"
                f"These matches still need to be completed:"
            )
            
            # Resend each incomplete match
            for match in incomplete_matches:
                if match.get("team1") or match.get("team2"):
                    # 2v2
                    if match.get("team2") is None and match.get("team1"):
                        try:
                            t1_names = ", ".join([(await client.fetch_user(uid)).display_name for uid in match["team1"]])
                            await channel.send(
                                f"🆓 **{t1_names}** have a BYE this week"
                            )
                        except:
                            await channel.send(
                                f"🆓 **Team** has a BYE this week"
                            )
                    else:
                        try:
                            t1_users = [await client.fetch_user(uid) for uid in match["team1"]]
                            t2_users = [await client.fetch_user(uid) for uid in match["team2"]]
                            t1_mentions = ", ".join([u.mention for u in t1_users])
                            t2_mentions = ", ".join([u.mention for u in t2_users])
                            view = LeagueMatchResultView2v2(league_name, week, match["team1"], match["team2"])
                            await channel.send(
                                f"🏆 **{league_name} - Week {week} (Resent)**\n"
                                f"👥 **Team 1**: {t1_mentions}\n"
                                f"👥 **Team 2**: {t2_mentions}\n"
                                f"Both teams must have all players confirm the result using the buttons below:",
                                view=view
                            )
                        except Exception as e:
                            print(f"Error resending 2v2 match notification: {e}")
                else:
                    # 1v1
                    if match["player2"] is None:  # Bye
                        try:
                            player1 = await client.fetch_user(match["player1"])
                            await channel.send(
                                f"🆓 **{player1.display_name}** has a BYE this week"
                            )
                        except:
                            await channel.send(
                                f"🆓 **Unknown User ({match['player1']})** has a BYE this week"
                            )
                    else:
                        try:
                            player1 = await client.fetch_user(match["player1"])
                            player2 = await client.fetch_user(match["player2"])
                            view = LeagueMatchResultView(league_name, week, match["player1"], match["player2"])
                            await channel.send(
                                f"🏆 **{league_name} - Week {week} (Resent)**\n"
                                f"⚔️ **{player1.mention}** vs **{player2.mention}**\n"
                                f"Both players must confirm the result using the buttons below:",
                                view=view
                            )
                        except Exception as e:
                            print(f"Error resending match notification: {e}")
            
            # Send a footer message
            await channel.send(
                f"📋 **{len(incomplete_matches)} incomplete matches have been resent.**\n"
                f"Please complete these matches before the week ends!"
            )
            
    except Exception as e:
        print(f"Error resending incomplete matches: {e}")


# Helper function to send league completion summary
async def send_league_completion_summary(league_name: str):
    """Sends a summary message when a league completes."""
    if league_name not in match_data["leagues"]:
        return
    
    league = match_data["leagues"][league_name]
    standings = match_data["league_standings"].get(league_name, {})
    
    # Sort standings by points, then wins, then ELO
    sorted_standings = sorted(
        standings.items(),
        key=lambda x: (x[1]["points"], x[1]["wins"], x[1]["elo"]),
        reverse=True
    )

    final_lines = []
    for rank, (user_id, stats) in enumerate(sorted_standings, start=1):
        display_name, elo, naked_laps = await get_user_display_info(int(user_id), league["sport"], guild)
        final_lines.append(
            f"**#{rank}** – {display_name}: {stats['points']}pts "
            f"({stats['wins']}W/{stats['losses']}L) ELO: {elo} 🩲{naked_laps}"
        )

    final_message = f"🏆 **{league_name} League Completed!** 🏆\n"
    final_message += f"👥 **Format**: {league['team_size']}v{league['team_size']}\n\n"
    final_message += "**Final Standings:**\n" + "\n".join(final_lines) + "\n\n"

    # Calculate average ELO for the league
    if standings:
        avg_elo = sum(stats["elo"] for stats in standings.values()) / len(standings)
        final_message += f"**Average ELO for {league_name}:** {avg_elo:.1f}\n"

    # Calculate total matches played
    total_matches = 0
    for week_matches in match_data["league_matches"].get(league_name, {}).values():
        for match in week_matches:
            if match["status"] in ["completed", "forfeited"]:
                total_matches += 1
    final_message += f"**Total Matches Played in {league_name}:** {total_matches}\n"

    # Calculate completion rate
    completion_rate = (total_matches / (league["season_length"] * len(league["participants"])) * 100) if league["season_length"] * len(league["participants"]) > 0 else 0
    final_message += f"**Completion Rate for {league_name}:** {completion_rate:.1f}%\n"

    # Delete league data after completion
    del match_data["leagues"][league_name]
    if league_name in match_data["league_signups"]:
        del match_data["league_signups"][league_name]
    if league_name in match_data["league_matches"]:
        del match_data["league_matches"][league_name]
    if league_name in match_data["league_standings"]:
        del match_data["league_standings"][league_name]
    
    save_data()

    try:
        guild = client.get_guild(GUILD_ID)
        if guild:
            channel = guild.system_channel or guild.text_channels[0]
            await channel.send(final_message)
    except Exception as e:
        print(f"Error sending league completion summary: {e}")


client.run(TOKEN)
