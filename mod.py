import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import demjson3 as demjson
import time
import numpy as np
import re
import ast


def init_session():
    """Initialize session with headers"""
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    session.headers.update(headers)
    return session

def make_request(session, url, retries=3, delay=1):
    """Make HTTP request with retry logic and delay"""
    for attempt in range(retries):
        try:
            time.sleep(delay * (attempt + 1))  # Exponential backoff
            response = session.get(url)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logging.error(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
            if attempt == retries - 1:
                raise
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
    """Extract matches data from HTML content (for male players)"""
    try:
        # Find the start of matchmx array
        start_marker = 'var matchmx = ['
        end_marker = '];'
        
        # Get the start position
        start_pos = html_content.find(start_marker)
        if start_pos == -1:
            logging.warning("Could not find matchmx variable in HTML")
            return None
            
        # Add length of start marker to get to actual data
        start_pos += len(start_marker) - 1  # -1 to keep the first [
        
        # Find the end position
        end_pos = html_content.find(end_marker, start_pos)
        if end_pos == -1:
            logging.warning("Could not find end of matchmx array")
            return None
            
        # Extract the array string
        matches_str = html_content[start_pos:end_pos + 1]
        
        # Clean up and parse
        matches_str = matches_str.replace('null', 'None')
        matches = ast.literal_eval(matches_str)
        
        return matches
        
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
    """Get all matches for a player regardless of gender"""
    try:
        session = init_session()
        all_matches = []

        # Try HTML page first (male players)
        try:
            html_url = f'{base_url}/cgi-bin/player-classic.cgi?p={player_name}'
            response = make_request(session, html_url)
            
            # Check if page redirected to Benoit Paire (indicating wrong player/female player)
            if "Benoit Paire" in response.text[:100]:
                logging.info(f"Redirected to Benoit Paire's page, trying JS files for {player_name}")
            else:
                # Check if page indicates player not found
                if "No player found" in response.text:
                    logging.error(f"Player {player_name} not found")
                    return None
                    
                matches = parse_matches_from_html(response.text)
                if matches:
                    all_matches.extend(matches)
                    logging.info(f"Found matches in HTML for {player_name}")

        except Exception as e:
            logging.warning(f"Could not get matches from HTML for {player_name}: {str(e)}")

        # If no matches found in HTML or redirected to Benoit Paire, try JS files (female players)
        if not all_matches or "BenoitPaire" in response.text:
            js_urls = [
                f"{base_url}/jsmatches/{player_name}.js",
                f"{base_url}/jsmatches/{player_name}Career.js"
            ]
            for url in js_urls:
                try:
                    response = make_request(session, url)
                    if response.status_code == 200:  # Only process if file exists
                        matches = parse_matches_from_js(response.text)
                        if matches:
                            all_matches.extend(matches)
                            logging.info(f"Found matches in JS file: {url}")
                except Exception as e:
                    logging.warning(f"Could not get matches from {url}: {str(e)}")

        # Create DataFrame if matches were found
        if all_matches:
            df = create_matches_dataframe(all_matches)
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
