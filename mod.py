import requests
import pandas as pd
import logging
import demjson3 as demjson
import time
import numpy as np
import ast

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tennis_scraper.log'),
        logging.StreamHandler()
    ]
)

def init_session():
    """Initialize session with more complete headers"""
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }
    session.headers.update(headers)
    return session


def make_request(session, url, retries=3, delay=2):
    """Make HTTP request with improved error handling and validation"""
    for attempt in range(retries):
        try:
            if attempt > 0:
                time.sleep(delay * (attempt))
            
            response = session.get(url, timeout=30)
            
            # Check if response is valid
            if response.status_code == 200:
                # Verify that we got actual content
                if len(response.text) > 0:
                    # Check if it's the player page we expect
                    if 'player-classic.cgi' in url:
                        if 'No player found' in response.text:
                            logging.warning("Player not found in database")
                            return None
                        elif 'matchmx' in response.text:
                            return response
                        else:
                            logging.warning("Unexpected content in player page")
                            continue
                    else:
                        return response
            else:
                logging.warning(f"Request failed with status code: {response.status_code}")
                
        except requests.RequestException as e:
            logging.error(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
            if attempt == retries - 1:
                raise
            
    raise Exception(f"Failed to get valid response after {retries} attempts")


def create_matches_dataframe(matches):
    """Create a DataFrame from matches data with essential columns only"""
    # Define column positions and names mapping
    essential_columns = {
        0: 'date',          # Date of match
        1: 'tourn',         # Tournament name
        2: 'surf',          # Surface
        4: 'wl',           # Win/Loss
        8: 'round',        # Tournament round
        9: 'score',        # Match score
        11: 'opp',          # Opponent name
        12: 'orank',        # Opponent's rank
        21: 'aces',         # Aces
        22: 'dfs',          # Double faults
        23: 'pts',          # Service points
        24: 'firsts',       # First serves in
        25: 'fwon',         # First serve points won
        26: 'swon',         # Second serve points won
        27: 'games',        # Service games
        28: 'saved',        # Break points saved
        29: 'chances',      # Break points faced
        30: 'oaces',        # Opponent's aces
        31: 'odfs',         # Opponent's double faults
        32: 'opts',         # Opponent's service points
        33: 'ofirsts',      # Opponent's first serves in
        34: 'ofwon',        # Opponent's first serve points won
        35: 'oswon',        # Opponent's second serve points won
        36: 'ogames',       # Opponent's service games
        37: 'osaved',       # Opponent's break points saved
        38: 'ochances',     # Opponent's break points faced
    }
    
    # Create DataFrame with numeric columns first
    df = pd.DataFrame(matches)
    
    # Select and rename only the columns we need
    df = df[essential_columns.keys()].rename(columns=essential_columns)
    
    # Convert date to datetime
    df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
    
    # Sort by date ascending
    df = df.sort_values('date')
    
    return df

def parse_matches_from_html(html_content):
    """Extract matches data from HTML content with improved parsing"""
    try:
        # Look for the matchmx array in a different way
        start_marker = 'var matchmx = ['
        end_marker = '];'
        
        # Find all script tags content
        import re
        script_contents = re.findall(r'<script[^>]*>(.*?)</script>', html_content, re.DOTALL)
        
        matches_data = None
        for script in script_contents:
            if 'var matchmx = [' in script:
                start_pos = script.find(start_marker) + len(start_marker)
                end_pos = script.find(end_marker, start_pos)
                if end_pos != -1:
                    matches_data = script[start_pos:end_pos]
                    break
        
        if matches_data is None:
            logging.warning("Could not find matchmx variable in HTML scripts")
            return None
            
        # Clean up the data
        matches_data = matches_data.strip()
        if matches_data.endswith(','):
            matches_data = matches_data[:-1]
            
        # Convert to proper Python list format
        matches_data = '[' + matches_data + ']'
        matches_data = matches_data.replace('null', 'None')
        
        # Parse the string into a Python object
        try:
            matches = ast.literal_eval(matches_data)
            return matches
        except:
            # Try using demjson if ast.literal_eval fails
            try:
                matches = demjson.decode(matches_data)
                return matches
            except Exception as e:
                logging.error(f"Failed to parse matches data with both ast and demjson: {str(e)}")
                return None
                
    except Exception as e:
        logging.error(f"Error parsing matches from HTML: {str(e)}")
        return None



def parse_matches_from_js(js_content):
    """Parse matches data from JavaScript content"""
    try:
        # Extract the matches array
        if 'matchmx = [' in js_content:
            matches_str = js_content.split('matchmx = [')[1].split('];')[0]
            # Add brackets back for proper JSON parsing
            matches_str = '[' + matches_str + ']'
            return demjson.decode(matches_str)
        return []
    except Exception as e:
        logging.error(f"Error parsing matches from JS: {str(e)}")
        return []


def get_player_matches(player_name, base_url="https://www.tennisabstract.com"):
    """Get all matches for a player with improved error handling"""
    try:
        session = init_session()
        all_matches = []
        
        logging.info(f"Fetching matches for player: {player_name}")

        # Try HTML page first (male players)
        html_url = f'{base_url}/cgi-bin/player-classic.cgi?p={player_name}'
        try:
            response = make_request(session, html_url)
            content = response.text
            
            if "Benoit Paire" in content[:100]:
                logging.info(f"Redirected to Benoit Paire's page, trying JS files for {player_name}")
            elif "No player found" in content:
                logging.error(f"Player {player_name} not found")
                return None
            else:
                matches = parse_matches_from_html(content)
                if matches:
                    all_matches.extend(matches)
                    logging.info(f"Found {len(matches)} matches in HTML for {player_name}")

        except Exception as e:
            logging.warning(f"Could not get matches from HTML for {player_name}: {str(e)}")

        # Try JS files if needed
        if not all_matches:
            js_urls = [
                f"{base_url}/jsmatches/{player_name}.js",
                f"{base_url}/jsmatches/{player_name}Career.js"
            ]
            for url in js_urls:
                try:
                    response = make_request(session, url)
                    matches = parse_matches_from_js(response.text)
                    if matches:
                        all_matches.extend(matches)
                        logging.info(f"Found {len(matches)} matches in JS file: {url}")
                except Exception as e:
                    logging.warning(f"Could not get matches from {url}: {str(e)}")

        if all_matches:
            df = create_matches_dataframe(all_matches)
            logging.info(f"Successfully created DataFrame with {len(df)} matches")
            return df
        
        logging.warning(f"No matches found for {player_name}")
        return None

    except Exception as e:
        logging.error(f"Error getting player matches: {str(e)}")
        return None


def calculate_yearly_stats(df):
    """
    Calculate advanced tennis statistics by year using sums of raw numbers
    Only includes matches where serving stats are available
    """
    # Create stats DataFrame with only matches that have serve stats
    # Convert relevant columns to numeric, replacing empty strings with NaN
    numeric_columns = ['pts', 'aces', 'dfs', 'firsts', 'fwon', 'swon', 'saved', 
                      'chances', 'games', 'ogames', 'osaved', 'ochances', 'orank']
    
    stats_df = df.copy()
    stats_df['year'] = stats_df['date'].dt.year
    # clean out walkovers
    stats_df=stats_df[stats_df['score']!='W/O']
    for col in numeric_columns:
        stats_df[col] = pd.to_numeric(stats_df[col], errors='coerce')
    
    # Calculate win-loss record for all matches (including those without stats)
    wl_record = stats_df.groupby('year')['wl'].agg(
        wins=lambda x: sum(x == 'W'),
        losses=lambda x: sum(x == 'L')
    )
    wl_record['total'] = wl_record['wins'] + wl_record['losses']
    wl_record['win%'] = (wl_record['wins'] / wl_record['total'] * 100).round(1)
    wl_record['W-L'] = wl_record.apply(lambda x: f"{int(x['wins'])}-{int(x['losses'])}", axis=1)
    
    # Filter for matches with stats
    stats_df = stats_df[stats_df['pts'].notna()]
    
    # First get yearly sums of raw numbers
    yearly_sums = stats_df.groupby('year').agg({
        'aces': 'sum',
        'dfs': 'sum',
        'pts': 'sum',          
        'firsts': 'sum',       
        'fwon': 'sum',         
        'swon': 'sum',         
        'saved': 'sum',        
        'chances': 'sum',      
        'games': 'sum',        
        'ogames': 'sum',       
        'osaved': 'sum',       
        'ochances': 'sum',     
        'orank': 'mean',       
    }).fillna(0).sort_values(by='year',ascending=True)  # Replace NaN with 0 for calculations
    
    # Calculate percentages from the sums
    yearly_stats = pd.DataFrame(index=yearly_sums.index)
    
    # Add win-loss records first
    yearly_stats['W-L'] = wl_record['W-L']
    yearly_stats['win%'] = wl_record['win%']
    
    # Only calculate percentages where denominator is not zero
    yearly_stats['ace%'] = (yearly_sums['aces'] / yearly_sums['pts'] * 100).round(2)
    yearly_stats['df%'] = (yearly_sums['dfs'] / yearly_sums['pts'] * 100).round(2)
    yearly_stats['1st_in%'] = (yearly_sums['firsts'] / yearly_sums['pts'] * 100).round(1)
    yearly_stats['1st_win%'] = (yearly_sums['fwon'] / yearly_sums['firsts'] * 100).round(1)
    
    # Handle potential division by zero
    second_serves = yearly_sums['pts'] - yearly_sums['firsts']
    yearly_stats['2nd_win%'] = (yearly_sums['swon'] / second_serves * 100).round(1)
    
    # Break point calculations
    yearly_stats['bp_saved%'] = (yearly_sums['saved'] / yearly_sums['chances'] * 100).round(1)
    
    # Calculate hold% and break%
    total_service_games = yearly_sums['games']
    yearly_stats['hold%'] = 100 - ((yearly_sums['chances'] - yearly_sums['saved']) / total_service_games * 100).round(1)
    
    total_return_games = yearly_sums['ogames']
    yearly_stats['break%'] = ((yearly_sums['ochances'] - yearly_sums['osaved']) / total_return_games * 100).round(1)
    
    # Add mean opponent rank
    yearly_stats['avg_opp_rank'] = yearly_sums['orank'].round(1)
    
    # Add count of matches
    yearly_stats['matches_with_stats%'] = (stats_df.groupby('year').size()/wl_record['total']*100).round(1)
    # yearly_stats['total_matches'] = df.groupby('year').size()
    
    # # Add total aces and double faults
    # yearly_stats['total_aces'] = yearly_sums['aces']
    # yearly_stats['total_dfs'] = yearly_sums['dfs']
    
    # Replace NaN and inf with 0
    yearly_stats = yearly_stats.replace([np.inf, -np.inf], np.nan)
    yearly_stats = yearly_stats.fillna(0)
    
    # Reorder columns to put W-L record and win% first
    cols = yearly_stats.columns.tolist()
    cols = ['W-L', 'win%'] + [col for col in cols if col not in ['W-L', 'win%']]
    yearly_stats = yearly_stats[cols]
    
    return yearly_stats

def calculate_career_stats(df):
    """
    Calculate career tennis statistics using aggregate numbers
    Only includes matches where serving stats are available
    """
    # Create stats DataFrame with only matches that have serve stats
    stats_df = df.copy()
    
    # Convert relevant columns to numeric
    numeric_columns = ['pts', 'aces', 'dfs', 'firsts', 'fwon', 'swon', 'saved', 
                      'chances', 'games', 'ogames', 'osaved', 'ochances', 'orank']
    
    for col in numeric_columns:
        stats_df[col] = pd.to_numeric(stats_df[col], errors='coerce')
    
    # Clean out walkovers
    stats_df = stats_df[stats_df['score']!='W/O']
    
    # Calculate overall win-loss record
    total_matches = len(stats_df)
    wins = sum(stats_df['wl'] == 'W')
    losses = total_matches - wins
    win_pct = round((wins / total_matches * 100),1)
    wl_record = f"{wins}-{losses}"
    
    # Filter for matches with stats
    matches_with_stats = stats_df[stats_df['pts'].notna()]
    stats_pct = round((len(matches_with_stats) / total_matches * 100),1)
    
    # Calculate career aggregates
    career_sums = matches_with_stats.agg({
        'aces': 'sum',
        'dfs': 'sum',
        'pts': 'sum',          
        'firsts': 'sum',       
        'fwon': 'sum',         
        'swon': 'sum',         
        'saved': 'sum',        
        'chances': 'sum',      
        'games': 'sum',        
        'ogames': 'sum',       
        'osaved': 'sum',       
        'ochances': 'sum',     
        'orank': 'mean',       
    }).fillna(0)
    
    # Create career stats DataFrame
    career_stats = pd.DataFrame({
        'W-L': wl_record,
        'win%': win_pct,
        'ace%': (career_sums['aces'] / career_sums['pts'] * 100).round(2),
        'df%': (career_sums['dfs'] / career_sums['pts'] * 100).round(2),
        '1st_in%': (career_sums['firsts'] / career_sums['pts'] * 100).round(1),
        '1st_win%': (career_sums['fwon'] / career_sums['firsts'] * 100).round(1),
        '2nd_win%': (career_sums['swon'] / (career_sums['pts'] - career_sums['firsts']) * 100).round(1),
        'bp_saved%': (career_sums['saved'] / career_sums['chances'] * 100).round(1),
        'hold%': 100 - ((career_sums['chances'] - career_sums['saved']) / career_sums['games'] * 100).round(1),
        'break%': ((career_sums['ochances'] - career_sums['osaved']) / career_sums['ogames'] * 100).round(1),
        'avg_opp_rank': career_sums['orank'].round(1),
        'matches_with_stats%': stats_pct
    }, index=['career'])
    
    # Replace any invalid values with 0
    career_stats = career_stats.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    return career_stats

def compare(p1,p2,year=2024):
    try:
        p1_data = pd.DataFrame(calculate_yearly_stats(get_player_matches(p1.replace(' ',''))).loc[year]).rename(columns={year:p1}).iloc[:-1]
        p2_data = pd.DataFrame(calculate_yearly_stats(get_player_matches(p2.replace(' ',''))).loc[year]).rename(columns={year:p2}).iloc[:-1]
    except KeyError:
        return f'Please make sure that the player names and year are correct.'
    # Combine the DataFrames
    result = pd.concat([p1_data, p2_data], axis=1)
    return result

def career(p1):
    try:
        data = pd.DataFrame(calculate_yearly_stats(get_player_matches(p1.replace(' ',''))))
        data_career = pd.DataFrame(calculate_career_stats(get_player_matches(p1.replace(' ',''))))
        data_full = pd.concat([data,data_career])
    except KeyError:
        return f'{p1} not found in data. Please use a valid player name.'
    return data_full

def format_h2h_matches(matches_df, player1, player2):
    """
    Transform head-to-head matches into winner/loser format with running H2H score
    """
    # Create a copy of the filtered DataFrame with selected columns
    h2h_matches = matches_df[matches_df['opp']==player2][['date','tourn','wl','surf','score','round']].copy()
    
    # Create winner and loser columns
    h2h_matches.loc[:, 'winner_name'] = np.where(h2h_matches['wl']=='W', 
                                                player1, 
                                                player2)
    h2h_matches.loc[:, 'loser_name'] = np.where(h2h_matches['wl']=='W', 
                                               player2, 
                                               player1)
    
    # Select and reorder columns, rename them in one step
    formatted_h2h = h2h_matches[['date', 'tourn', 'winner_name', 'loser_name', 'score', 'round']].rename(columns={
        'date': 'match_date',
        'tourn': 'tournament'
    })
    
    # Convert date to date format
    formatted_h2h['match_date'] = pd.to_datetime(formatted_h2h['match_date'],format='%Y-%m-%d').apply(lambda x: x.date())
    
    # Extract player names from the first match
    first_match = formatted_h2h.iloc[0]
    player1_name = first_match['winner_name']
    player2_name = first_match['loser_name']
    # Calculate H2H record
    h2h_record = {player1: 0, player2: 0}
    h2h_column = []

    for _, row in formatted_h2h.iterrows():
        if row['winner_name'] == player1_name:
            h2h_record[player1_name] += 1
        else:
            h2h_record[player2_name] += 1
        h2h_column.append(f"{h2h_record[player1_name]}-{h2h_record[player2_name]}")

    formatted_h2h['h2h'] = h2h_column
    
    # Ensure columns are in the correct order
    formatted_h2h = formatted_h2h[['match_date', 'tournament', 'winner_name', 'loser_name', 'score', 'round', 'h2h']]
    
    return formatted_h2h
