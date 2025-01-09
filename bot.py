import telebot
from telebot import types
import time
import pandas as pd
from mod import get_player_matches,calculate_yearly_stats,career,format_h2h_matches

from datetime import datetime
import dataframe_image as dfi


from io import BytesIO
from PIL import Image

import logging
# Set up logging
logging.basicConfig(filename='error.log', level=logging.ERROR)

# Replace TOKEN with your bot token
bot = telebot.TeleBot("6119046013:AAEClU2GTQmAakINMV-kem03ToGbiz-rNpg")

YOUR_USER_ID = 311855459 # Replace this with your actual user ID

YOUR_USERNAME = 'fifatyoma' # Replace this with your actual Telegram username

@bot.message_handler(commands=['start'])
def start_command(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add('/help', '/compare', '/h2h', '/career')
    bot.send_message(message.chat.id, "Please choose a command:", reply_markup=keyboard)

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """Here are the available commands:

/compare - Compare two players' statistics for a specific year
/h2h - View the head-to-head record between two players
/career - View a player's career statistics

For each command, you'll be prompted to enter the required information."""
    
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['compare'])
def compare_command(message):
    msg = bot.send_message(message.chat.id, 'Please enter the first player name:')
    bot.register_next_step_handler(msg, process_compare_player1_step)

def process_compare_player1_step(message):
    try:
        p1 = message.text
        msg = bot.send_message(message.chat.id, 'Please enter the second player name:')
        bot.register_next_step_handler(msg, lambda m: process_compare_player2_step(m, p1))
    except Exception as e:
        bot.reply_to(message, 'An error occurred while processing the first player name.')

def process_compare_player2_step(message, p1):
    try:
        p2 = message.text
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add('2024', '2023', '2022', 'Other')
        msg = bot.send_message(message.chat.id, 'Please choose a year:', reply_markup=keyboard)
        bot.register_next_step_handler(msg, lambda m: process_compare_year_step(m, p1, p2))
    except Exception as e:
        bot.reply_to(message, 'An error occurred while processing the second player name.')

def process_compare_year_step(message, p1, p2):
    try:
        year_text = message.text
        if year_text == 'Other':
            years = [str(y) for y in range(2000, 2022)[::-1]]
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for y in years:
                keyboard.add(y)
            msg = bot.send_message(message.chat.id, 'Please choose a year:', reply_markup=keyboard)
            bot.register_next_step_handler(msg, lambda m: process_compare_year_step(m, p1, p2))
            return

        # Get comparison data and create image
        year = int(year_text)
        p1_data = pd.DataFrame(calculate_yearly_stats(get_player_matches(p1.replace(' ',''))).loc[year]).iloc[:-1]
        p2_data = pd.DataFrame(calculate_yearly_stats(get_player_matches(p2.replace(' ',''))).loc[year]).iloc[:-1]
        
        comparison = pd.concat([p1_data, p2_data], axis=1)
        comparison.columns = [p1, p2]

        # Create and send image
        create_and_send_table_image(comparison, message.chat.id)
        
        # Show command menu
        show_command_menu(message.chat.id)
    except Exception as e:
        bot.reply_to(message, 'An error occurred while processing the comparison.')

@bot.message_handler(commands=['h2h'])
def h2h_command(message):
    msg = bot.send_message(message.chat.id, "Please enter the first player name:")
    bot.register_next_step_handler(msg, process_h2h_player1_step)

def process_h2h_player1_step(message):
    try:
        p1 = message.text
        msg = bot.send_message(message.chat.id, "Please enter the second player name:")
        bot.register_next_step_handler(msg, lambda m: process_h2h_player2_step(m, p1))
    except Exception as e:
        bot.reply_to(message, 'An error occurred while processing the first player name.')

def process_h2h_player2_step(message, p1):
    try:
        p2 = message.text
        # Get H2H data
        matches_df = get_player_matches(p1.replace(' ',''))
        h2h_data = format_h2h_matches(matches_df, p1, p2)
            # Apply styles to the table
        h2h_data1 = h2h_data.style.hide(axis='index').set_table_styles(
        [{'selector': 'th', 'props': [('text-align', 'left')]},
         {'selector': 'td', 'props': [('text-align', 'left')]}]
        )
        
        # Create and send image
        create_and_send_table_image(h2h_data1, message.chat.id)
        
        # Send H2H summary
        send_h2h_summary(h2h_data, p1, p2, message.chat.id)
        
        # Show command menu
        show_command_menu(message.chat.id)
    except Exception as e:
        bot.reply_to(message, 'An error occurred while processing the H2H comparison.')

@bot.message_handler(commands=['career'])
def career_command(message):
    msg = bot.send_message(message.chat.id, 'Please enter the player name:')
    bot.register_next_step_handler(msg, process_career_step)

def process_career_step(message):
    try:
        player_name = message.text
        # Get career stats
        career_stats = career(player_name).iloc[:,:-1]
        
        # Create and send image
        create_and_send_table_image(career_stats, message.chat.id)
        
        # Show command menu
        show_command_menu(message.chat.id)
    except Exception as e:
        bot.reply_to(message, 'An error occurred while processing the career statistics.')

# Helper functions
def create_and_send_table_image(data, chat_id):
    
    img_data = BytesIO()
    dfi.export(data, img_data)
    img_data.seek(0)
    
    # Add padding
    padding = 20
    img = Image.open(img_data)
    padded_img = Image.new('RGB', (img.width + 2*padding, img.height + 2*padding), (255, 255, 255))
    padded_img.paste(img, (padding, padding))
    
    # Send image
    padded_img_data = BytesIO()
    padded_img.save(padded_img_data, format='PNG')
    padded_img_data.seek(0)
    bot.send_photo(chat_id, photo=padded_img_data)

def show_command_menu(chat_id):
    """Show the command menu keyboard"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add('/help', '/compare', '/h2h', '/career')
    bot.send_message(chat_id, 'Please choose a command:', reply_markup=keyboard)

def send_h2h_summary(h2h_data, p1, p2, chat_id):
    """Send H2H summary message"""
    p1_wins = len(h2h_data[h2h_data.winner_name == p1])
    p2_wins = len(h2h_data[h2h_data.winner_name == p2])
    last_match = h2h_data.iloc[-1]
    last_tournament = f"{last_match['tournament']} {last_match['match_date'].year}"
    # Create main H2H summary
    if p1_wins > p2_wins:
        txt = f"{p1} leads H2H {p1_wins}-{p2_wins}"
    elif p2_wins > p1_wins:
        txt = f"{p2} leads H2H {p2_wins}-{p1_wins}"
    else:
        txt = f"H2H is tied at {p1_wins}-{p2_wins}"
    
    txt += f", last played at {last_tournament}"
    bot.send_message(chat_id, txt)
    

while True:
    try:
        bot.polling(none_stop=True, timeout=90)
    except Exception as e:
        print(e)
        time.sleep(5)
        continue
