# Discord Sports Bot

A Discord bot for managing sports matches, ELO ratings, and competitive leagues.

## Features

### Core Sports Management
- Create and manage sports with configurable team sizes (1v1 or 2v2)
- Record match results with automatic ELO calculations
- Track player statistics and match history
- "Naked lap" tracking for players who lose without scoring

### League System 🆕
- **League Creation**: Admins can create leagues with customizable season length and signup deadlines
- **Automatic Matchmaking**: Weekly matches are automatically generated for all participants
- **Forfeit Handling**: Players who don't complete matches lose maximum ELO
- **Separate Tracking**: League results are tracked separately from regular matches
- **Standings**: Real-time league standings with points, wins, and losses
- **Admin Controls**: Full administrative control over league progression

## Commands

### Sports Management
- `/create_sport <name> <team_size>` - Create a new sport (Admin only)
- `/match <sport> <winner1> [winner2] <loser1> [loser2> [score]` - Record a match result
- `/leaderboard <sport>` - Show ELO rankings for a sport
- `/match_history <user>` - View match history for a user
- `/show_naked_laps` - See who's doing naked laps (0-point losses)
- `/clear_naked_lap <user>` - Remove a naked lap from a user (Admin only)

### League Management 🆕
- `/create_league <name> <sport> <season_length> <signup_deadline> <match_day> <team_size>` - Create a new league (Admin only)
- `/start_league <name>` - Start a league and generate first week matches (Admin only)
- `/advance_week <name>` - Advance to the next week in a league (Admin only)
- `/resend_matches <name>` - Resend incomplete matches for current week (Admin only) 🆕
- `/complete_league <name>` - Manually complete a league and send final summary (Admin only) 🆕
- `/extend_signup <name> <new_deadline>` - Extend signup deadline (Admin only)
- `/delete_league <name>` - Delete a league and all its data (Admin only)

### League Information 🆕
- `/list_leagues` - List all available leagues
- `/league_info <name>` - Get detailed information about a league
- `/league_signups <name>` - Show current signups for a league
- `/league_standings <name>` - Show current standings for a league
- `/league_matches <name> [week]` - Show matches for a specific week
- `/league_match_status <name> [week]` - Check match confirmation status 🆕
- `/league_match_history <name>` - Show match history and BYE distribution 🆕
- `/league_stats <name>` - Show detailed statistics for a league
- `/my_leagues` - Show leagues you're signed up for

### League Results 🆕
- `/record_league_result <league> <week> <player1> <player2> <winner> <score>` - Manually record a league match result (Admin only)

### Admin Management 🆕
- `/admin_add @user` - Add a user as an admin (Admin only)
- `/admin_remove @user` - Remove a user's admin status (Admin only)
- `/admin_list` - Show current admin users
- `/admin_check` - Check if you have admin permissions

## League System Details

### How It Works
1. **League Creation**: Admin creates a league with sport, season length, signup deadline, and match day
2. **Signup Period**: Players can sign up using interactive buttons until the deadline
3. **League Start**: Admin starts the league, generating first week matches
4. **Weekly Progression**: Admin advances weeks manually, processing forfeits and generating new matches
5. **Result Recording**: Players report results using interactive buttons or admins record manually
6. **Automatic Forfeits**: Unplayed matches result in both players losing maximum ELO

### League States
- **📝 Signup**: Accepting new participants
- **🏃‍♂️ Active**: League is running with weekly matches
- **🏆 Completed**: Season has finished - final rankings sent and data cleaned up automatically

### Match Types
- **Scheduled**: Match is waiting to be played
- **Completed**: Match result has been recorded
- **Forfeited**: Match wasn't played, both players lose ELO
- **Bye**: Player has no opponent this week (when odd number of participants)

### ELO System
- League matches affect overall ELO ratings
- Forfeited matches result in maximum ELO loss (K_FACTOR = 32)
- League standings track both league performance and current ELO

### Advanced Matchmaking System 🆕
The league system uses sophisticated algorithms to create fair and engaging matchups:

#### **Minimized Repeated Matchups**
- Tracks how many times each pair of players has faced each other
- Prioritizes new matchups over repeated ones
- Uses a scoring system that heavily penalizes repeated matchups (1000x penalty)

#### **Balanced BYE Distribution**
- Rotates BYEs evenly among all participants
- Players with fewer BYEs get priority for future BYEs
- Prevents any single player from getting multiple BYEs in a row

#### **Match Count Balancing**
- Considers how many matches each player has completed
- Players with fewer matches get priority for new matchups
- Ensures all players get similar playing opportunities

#### **Smart Pairing Algorithm**
- Uses a greedy algorithm to find optimal pairings
- Calculates scores based on repeat penalties and balance penalties
- Automatically adjusts as the season progresses

### Automatic League Completion 🆕
When a league reaches its final week, the system automatically:

1. **Sends Final Rankings**: Comprehensive final standings with points, wins, and losses
2. **Season Summary**: Includes average ELO, total matches played, and completion rate
3. **Data Cleanup**: Automatically removes league data from the system
4. **Channel Notification**: Sends the final summary to the Discord channel

#### **Manual Completion**
Admins can also manually complete leagues early using `/complete_league <name>` if needed.

#### **Completion Message Example**
```
🏆 Summer Tennis League Completed! 🏆

Final Standings:
#1 – Sarah: 9pts (3W/0L) ELO: 1218
#2 – Mike: 6pts (2W/1L) ELO: 1182  
#3 – John: 3pts (1W/2L) ELO: 1200

Average ELO for Summer Tennis: 1200.0
Total Matches Played in Summer Tennis: 6
Completion Rate for Summer Tennis: 100.0%
```

The system is designed to make competitive play smooth and efficient.

### Team Size Support 🆕
Leagues now support both **1v1** and **2v2** formats:

#### **1v1 Leagues (Individual)**
- Single players compete against each other
- Standard matchmaking with BYE rotation
- Individual ELO tracking and standings

#### **2v2 Leagues (Team)**
- Players form teams of 2
- Advanced matchmaking prevents same teammates
- Team-based ELO and standings
- BYEs distributed more intelligently

#### **Creating Different Formats**
```
# 1v1 League
/create_league name:"Tennis Singles" sport:tennis season_length:8 signup_deadline:2024-06-01 match_day:Saturday team_size:1

# 2v2 League  
/create_league name:"Basketball Doubles" sport:basketball season_length:10 signup_deadline:2024-06-01 match_day:Sunday team_size:2
```

### Match Resending 🆕
Admins can resend incomplete matches for the current week using `/resend_matches <league_name>`. This is useful when:

- **Matches were sent to wrong channel** - Resend to the correct location
- **Messages got lost** - Players can't find their match notifications
- **Reminder needed** - Week is ending and matches aren't completed
- **Channel issues** - Bot couldn't send to the intended channel

#### **What Gets Resent**
- Only **incomplete matches** (status: "scheduled")
- **BYE notifications** for players with no opponent
- **Match result buttons** for players to confirm outcomes
- **Clear labeling** that these are resent matches

#### **Resend Process**
1. Admin runs `/resend_matches Summer Tennis`
2. Bot checks current week for incomplete matches
3. Bot sends header: "Resending Incomplete Matches"
4. Each incomplete match gets resent with fresh buttons
5. Bot sends footer with count of resent matches
6. Players can now complete their matches

## Setup

1. Install Python 3.8+
2. Install dependencies: `pip install discord.py python-dotenv`
3. Create a `.env` file with your Discord bot token and guild ID:
   ```
   TOKEN=your_bot_token_here
   GUILD_ID=your_guild_id_here
   ADMIN_IDS=your_user_id_here,other_admin_id_here  # Optional: set initial admins
   ```
4. Run the bot: `python bot.py`
5. **Set up your first admin**: Use `/admin_add @yourself` to become the first admin
6. **Create sports**: Use `/create_sport <name> <team_size>` to set up sports
7. **Create leagues**: Use `/create_league` with `team_size:1` for 1v1 or `team_size:2` for 2v2

## Data Storage

All data is stored in `match_data.json` including:
- Sports configuration
- Player ELO ratings
- Match history
- League information
- League signups and standings
- League match results

## Admin Requirements

League management commands require **custom admin permissions**:
- Creating leagues
- Starting leagues
- Advancing weeks
- Recording results
- Deleting leagues
- Extending deadlines

### Admin Management 🆕
- `/admin_add @user` - Add a user as an admin
- `/admin_remove @user` - Remove a user's admin status
- `/admin_list` - Show current admin users
- `/admin_check` - Check if you have admin permissions

### Setting Up Admins
1. **First Time Setup**: The first user to run `/admin_add @themselves` becomes the first admin
2. **Add More Admins**: Existing admins can add other users as admins
3. **Environment Variable**: You can also set initial admins in your `.env` file:
   ```
   ADMIN_IDS=123456789,987654321,555666777
   ```
4. **Remove Admins**: Use `/admin_remove @user` (cannot remove the last admin)

## Example Usage

### Creating a League
```
# 1v1 League
/create_league name:"Summer Tennis" sport:tennis season_length:8 signup_deadline:2024-06-01 match_day:Saturday team_size:1

# 2v2 League
/create_league name:"Basketball League" sport:basketball season_length:10 signup_deadline:2024-06-01 match_day:Sunday team_size:2
```

### Starting a League
```
/start_league name:"Summer Tennis"
```

### Advancing to Next Week
```
/advance_week name:"Summer Tennis"
```

### Checking Standings
```
/league_standings name:"Summer Tennis"
```

## Notes

- League matches are separate from regular matches but affect the same ELO system
- Forfeited matches automatically deduct maximum ELO from both players
- The bot will attempt to send match notifications to the first available channel
- League data is persistent and survives bot restarts
- All dates should be in YYYY-MM-DD format

### **Interactive Buttons (Primary Method)**
When a new week starts, the bot automatically sends individual match notifications to the Discord channel with **result reporting buttons**:

```
🏆 Summer Tennis - Week 1
⚔️ @Player1 vs @Player2
Both players must confirm the result using the buttons below:
[Player 1 Won] [Player 2 Won]
```

**Both players must click the same button** to confirm the result. Once both confirm, the match is automatically recorded. This ensures fair play and prevents disputes!

| Aspect | League Matches | Regular Matches |
|--------|----------------|-----------------|
| **Reporting** | Interactive buttons | Command + confirmation |
| **Who Can Report** | Both players | Anyone (with loser confirmation) |
| **Confirmation** | Both players must confirm | Requires loser confirmation |
| **Score** | Simple win/loss | Full score recorded |
| **Integration** | Affects league standings + ELO | Only affects ELO |

