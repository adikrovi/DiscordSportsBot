# 🏆 Discord Sports Bot

A powerful Discord bot for managing competitive matches, calculating ELO ratings, tracking zero-point loss punishments ("naked laps"), and providing interactive slash commands.

---

## 🔧 Features

- Create 1v1 or 2v2 sports
- Record matches with loser confirmation
- Automatic ELO updates using the Elo rating system
- Track naked laps (0-point losses)
- View leaderboards and match history
- Admin command to clear naked laps
- Slash command autocomplete for sport names

---


💬 Commands Overview
/create_sport — Create a sport.

name: Name of the sport

team_size: Either 1 (1v1) or 2 (2v2)

/match — Record a match result.

sport: Sport name (autocompletes)

winner1, winner2: Winning players

loser1, loser2: Losing players

score: Match score (e.g., 2-0)

✅ Requires confirmation from one of the losing players before finalizing

/leaderboard — Show ELO leaderboard for a sport.

/match_history — View a user's recent matches.

/show_naked_laps — See who has the most 0-point losses.

/clear_naked_lap — Admin-only command to remove one naked lap from a user.


📂 Data Format
All data is saved in match_data.json:

{
  "sports": {},
  "elo": {},
  "matches": []
  "naked_laps":{}
}

🧠 Behind the Scenes
ELO Rating System: Players’ scores are updated using the Elo system with a K-factor of 32.

Naked Laps: If a team loses with 0 points (e.g. 2-0), each player on that team gets a naked lap.

Match Confirmation: A match only finalizes after at least one losing player confirms it via an interactive button.

