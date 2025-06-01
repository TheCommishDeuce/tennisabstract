import telebot
from telebot import types
import time
import pandas as pd
from mod import get_player_matches,calculate_yearly_stats,career,format_h2h_matches

from datetime import datetime
import dataframe_image as dfi


from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
# pandas is already imported as pd
import os
import sys # Should already be there but ensure it is
import re
# requests is already imported
import requests # Added for clarity, though it might be implicitly available via other imports
import pycountry
# from io import BytesIO # Already imported
# time is already imported
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

import logging
# Set up logging
logging.basicConfig(filename='error.log', level=logging.ERROR)

# --- Configuration ---
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1080
IMAGE_DIRECTORY = "images" # Assuming player images are here
BACKGROUND_DIRECTORY = "backgrounds"

# --- Background Effects ---
BACKGROUND_OPACITY = 255 # 0 (transparent) to 255 (opaque)
BACKGROUND_BLUR_RADIUS = 2 # Gaussian blur radius (0 for no blur)

# --- Player Image Sizing & Positioning ---
PLAYER_AREA_WIDTH = OUTPUT_WIDTH // 2
PLAYER_AREA_HEIGHT = int(OUTPUT_HEIGHT * 0.7) # Adjust this percentage as needed
PLAYER_BOTTOM_PADDING = 0 # Space below the bottom of the player image area
PLAYER_PASTE_Y = OUTPUT_HEIGHT - PLAYER_AREA_HEIGHT - PLAYER_BOTTOM_PADDING

# --- Font Configuration ---
PLAYER_NAME_FONT_PATH = "fonts/Sansation-Bold.ttf" # Example: Bold font for names
PLAYER_NAME_FONT_SIZE = 32

UNSPLASH_ACCESS_KEY = "J93tzT2fih6dpCn2z85sSElaGoWNcWoeM4MuFGq53eU" # Replace with your actual key if different

# Load fonts
try:
    player_name_font = ImageFont.truetype(PLAYER_NAME_FONT_PATH, PLAYER_NAME_FONT_SIZE)
except IOError as e:
    print(f"ERROR: Failed to load one or more fonts: {e}. Check paths. Exiting.", file=sys.stderr)
    # In a bot context, sys.exit(1) might be too harsh. Consider logging and using a default font.
    # For now, we'll keep the print and rely on a fallback or error handling later in create_graphic.
    player_name_font = ImageFont.load_default() # Fallback font

# --- Unified Text Box Configuration ---
TEXT_BOX_CONFIG = {
    "text_color": (255, 255, 255, 255),  # White RGBA
    "player_box_width": 350,   # fixed width in px
    "player_box_height": 140,  # fixed height in px
    "bg_color": (0, 0, 0),               # Black RGB
    "bg_opacity": 190,                   # Opacity for background box
    "bg_padding_x": 12,                  # Horizontal padding inside the box
    "bg_padding_y": 15,                  # Vertical padding inside the box
    "bg_radius": 10,                     # Rounded corners for background
    "line_spacing": 8,                   # Spacing between lines
    "shadow_offset": (2, 2),             # Text shadow offset
    "shadow_color": (0, 0, 0, 165),      # Text shadow color
    "x_margin": 40,                      # Horizontal margin
    "align": "left",                     # Default text alignment
    "player_box_position": "bottom"      # "bottom", "middle", or "top"
}

# Replace TOKEN with your bot token
bot = telebot.TeleBot("6119046013:AAEClU2GTQmAakINMV-kem03ToGbiz-rNpg")

YOUR_USER_ID = 311855459 # Replace this with your actual user ID

YOUR_USERNAME = 'fifatyoma' # Replace this with your actual Telegram username

def download_image(url, save_path):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"Saved image to {save_path}")
        return True
    else:
        print("Failed to download image.")
        return False

def get_best_wta_player_image_url(profile_soup):
    # Find the <picture> block
    picture_tag = profile_soup.find('picture', class_='player-headshot__photo')
    if picture_tag and picture_tag.img:
        return picture_tag.img['src']
    else:
        print("No <picture> tag or <img> in it found.")
        return None

def get_player_image_from_wta(player_name, save_dir="images"):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--headless")
    # Ensure chromedriver is in PATH or specify its location:
    # driver = webdriver.Chrome(executable_path='/path/to/chromedriver', options=chrome_options)
    driver = webdriver.Chrome(options=chrome_options) # Assumes chromedriver is in PATH
    wait = WebDriverWait(driver, 10)

    try:
        driver.get("https://www.wtatennis.com/players")
        time.sleep(2) # Allow page to load

        found = False
        for attempt in range(6): # Try up to 6 "Load More" clicks
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")
            player_div = None

            # Search logic based on provided snippet
            search_classes = ["players-list__item js-player-item-favourite"]
            if attempt > 0: # After first attempt, also check 'no-filter' if that's relevant
                search_classes.append("players-list__item js-player-item-favourite no-filter")

            for div_class in search_classes:
                for div in soup.find_all("div", class_=div_class):
                    if div.get("data-player-name", "").strip().lower() == player_name.strip().lower():
                        player_div = div
                        break
                if player_div:
                    break

            if player_div:
                player_id = player_div["data-player-id"]
                player_name_actual = player_div["data-player-name"] # Use actual name for slug
                slug = player_name_actual.lower().replace(" ", "-").replace(".","") # Basic slugify
                profile_url = f"https://www.wtatennis.com/players/{player_id}/{slug}"
                print(f"Found player: {player_name_actual} at {profile_url}")
                found = True
                break

            # Try to click "Load More"
            try:
                load_more_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(), 'Load More')]")))
                driver.execute_script("arguments[0].click();", load_more_button)
                print("Clicked 'Load More'. Pausing...")
                time.sleep(2) # Wait for new content
            except Exception as e_click:
                print(f"No more 'Load More' button or unable to click: {e_click}")
                break # Exit loop if no more button

        if not found:
            print(f"Player {player_name} not found after loading.")
            driver.quit()
            return None

        driver.get(profile_url)
        time.sleep(2) # Allow profile page to load
        profile_soup = BeautifulSoup(driver.page_source, "html.parser")

        img_url = get_best_wta_player_image_url(profile_soup)

        if img_url:
            print(f"Found image URL: {img_url}")
            # Basic extension extraction, improve if needed
            try:
                ext = img_url.split("?")[0].split(".")[-1]
                if len(ext) > 4 or len(ext) < 2: # Basic sanity check for extension
                    ext = "jpg"
            except:
                ext = "jpg" # Default extension

            save_path = os.path.join(save_dir, f"{normalize_name(player_name)}.{ext}")
            os.makedirs(save_dir, exist_ok=True)

            if download_image(img_url, save_path):
                driver.quit()
                return save_path
            else:
                print(f"Failed to download image for {player_name} from {img_url}")
                driver.quit()
                return None
        else:
            print(f"Player image URL not found on profile page for {player_name}.")
            driver.quit()
            return None
    except Exception as e:
        print(f"Error in get_player_image_from_wta for {player_name}: {e}")
        if 'driver' in locals() and driver:
            driver.quit()
        return None

def fetch_city_background_unsplash_api(city_name, save_dir="backgrounds", access_key=None):
    import requests, os # Ensure these are available

    if not access_key:
        print("No Unsplash API key provided.")
        return None
    if not city_name:
        print("No city name provided for Unsplash search.")
        return None

    queries = [
        f"{normalize_name(city_name)} cityscape",
        f"{normalize_name(city_name)} city",
        normalize_name(city_name)
    ]
    search_url = "https://api.unsplash.com/search/photos"

    for query in queries:
        params = {
            "query": query,
            "orientation": "landscape", # Changed to landscape as typically better for backgrounds
            "per_page": 1,
            "client_id": access_key
        }
        print(f"Querying Unsplash API for: {params['query']}")
        try:
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        except requests.exceptions.RequestException as e:
            print(f"Unsplash API request failed for query '{query}': {e}")
            continue

        data = response.json()
        if data.get("results"):
            img_url = data["results"][0]["urls"]["regular"] # 'regular' size is good for most uses
            print(f"Image URL found: {img_url}")

            normalized_city = normalize_name(city_name)
            ext = ".jpg" # Unsplash typically provides JPEGs
            save_path = os.path.join(save_dir, f"{normalized_city}{ext}")
            os.makedirs(save_dir, exist_ok=True)

            if download_image(img_url, save_path):
                return save_path
            else:
                print(f"Download failed for {img_url}, trying next query...")
        else:
            print(f"No Unsplash results for query: {query}")

    print(f"No Unsplash API results for any query related to '{city_name}'.")
    return None

def find_or_fetch_background_image(city_name, search_dir="backgrounds", access_key=None, file_types=('.png', '.jpg', '.jpeg', '.webp', '.gif')):
    if not city_name or not isinstance(city_name, str): # Added type check
        print("INFO: No valid city name provided for background search.")
        return None

    os.makedirs(search_dir, exist_ok=True) # Ensure directory exists

    normalized_search = normalize_name(city_name)
    if not normalized_search: # Handle empty string after normalization
        print(f"Warning: City name '{city_name}' normalized to empty string. Cannot search locally.")
        # Still proceed to fetch if access_key is available, as Unsplash might handle it

    print(f"Searching for background matching normalized term '{normalized_search}' in '{search_dir}'...")
    found_files = []
    for filename in os.listdir(search_dir):
        base_name, ext = os.path.splitext(filename)
        if ext.lower() in file_types:
            # Normalize filename without extension for comparison
            if normalize_name(base_name) == normalized_search:
                found_files.append(filename)

    if found_files:
        found_files.sort(key=len) # Prefer shorter, exact matches
        full_path = os.path.join(search_dir, found_files[0])
        print(f"Found background image: {os.path.basename(full_path)}")
        return full_path

    print(f"No local background image found matching '{normalized_search}'. Attempting to fetch from Unsplash API...")
    if access_key: # Only try to fetch if an access key is provided
        fetched_path = fetch_city_background_unsplash_api(city_name, save_dir=search_dir, access_key=access_key)
        if fetched_path:
            return fetched_path
    else:
        print("INFO: No Unsplash access key provided. Skipping API fetch.")

    default_path = os.path.join(search_dir, "default.jpg") # Or default.png
    if os.path.exists(default_path):
        print("INFO: Using default background image.")
        return default_path

    print("No background image found, fetched, or default available. Returning None.")
    return None

def alpha3_to_alpha2(code):
    try:
        country = pycountry.countries.get(alpha_3=code.upper())
        return country.alpha_2.lower() if country else None
    except Exception as e: # More specific exception handling if possible
        print(f"Could not convert country code '{code}': {e}")
        return None

def reduce_opacity(img, opacity):
    assert 0 <= opacity <= 255
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    alpha = img.split()[3]
    alpha = alpha.point(lambda p: int(p * opacity / 255)) # Ensure integer for point
    img.putalpha(alpha)
    return img

def get_flag_image(country_code, width=160):
    if not country_code or not isinstance(country_code, str): # Added type check
        print("Invalid country code provided for flag.")
        return None

    code = country_code.strip().lower()
    # Ensure it's a 2-letter code for flagcdn
    if len(code) != 2:
        print(f"Invalid country code format for flagcdn: '{code}'. Must be alpha-2.")
        return None

    url = f"https://flagcdn.com/w{width}/{code}.png"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content)).convert("RGBA")
        else:
            print(f"Flag not found for {country_code} (HTTP {response.status_code}) at {url}")
    except requests.exceptions.RequestException as e: # More specific exception
        print(f"Error fetching flag for {country_code}: {e}")
    except IOError as e: # PIL specific error
        print(f"Error opening flag image for {country_code}: {e}")
    return None

def format_stat(value, default="N/A"):
    if value is not None and str(value).strip() != "" and pd.notna(value): # Ensure string conversion for strip
        return str(value)
    return default

def get_surname(full_name):
    if not full_name or not isinstance(full_name, str): return "" # Added type check
    return full_name.split()[-1]

def normalize_name(name):
    if not name or not isinstance(name, str): return "" # Added type check
    name = re.sub(r' (atp|wta) ', '', name, flags=re.IGNORECASE) # Corrected regex
    name = name.lower()
    name = re.sub(r'[\s\.\-_●]+', '', name) # Added ● to common punctuation
    name = name.strip()
    return name

def find_player_image(normalized_player_name, search_dir=IMAGE_DIRECTORY, file_types=('.png', '.jpg', '.jpeg', '.webp', '.gif')):
    # This function expects a pre-normalized player name for searching
    if not normalized_player_name:
        print("ERROR: Cannot search for player with empty normalized name.", file=sys.stderr)
        return None
    if not os.path.isdir(search_dir):
        # Try to create it, useful for first run
        try:
            os.makedirs(search_dir, exist_ok=True)
            print(f"INFO: Created image directory: {search_dir}")
        except OSError as e:
            print(f"ERROR: Player image directory not found and could not be created: {search_dir}. Error: {e}", file=sys.stderr)
            return None

    print(f"Searching for player image matching '{normalized_player_name}' in '{search_dir}'...")
    found_files = []
    # Search for files whose basename (normalized) matches normalized_player_name
    for filename in os.listdir(search_dir):
        base, ext = os.path.splitext(filename)
        if ext.lower() in file_types:
            if normalize_name(base) == normalized_player_name:
                found_files.append(filename)

    if not found_files:
        print(f"INFO: No player image file found for '{normalized_player_name}'.")
        return None
    elif len(found_files) > 1:
        found_files.sort(key=len)
        print(f"WARNING: Multiple files found for '{normalized_player_name}': {found_files}. Using: '{found_files[0]}'")

    full_path = os.path.join(search_dir, found_files[0])
    print(f"Found player image: {os.path.basename(full_path)}")
    return full_path

def get_player_image_path(player_name, images_dir="images"): # player_name is full name
    normalized_p_name = normalize_name(player_name)
    if not normalized_p_name:
        print(f"ERROR: Cannot get image path for invalid player name: {player_name}")
        return None

    # Search using the fully normalized name (e.g. "coco gauff" -> "cocogauff")
    local_path = find_player_image(normalized_p_name, search_dir=images_dir)
    if local_path:
        return local_path

    # If not found, try fetching from WTA (which uses the original player_name for search)
    print(f"Local image for '{normalized_p_name}' not found. Trying to fetch from WTA for '{player_name}'...")
    fetched_path = get_player_image_from_wta(player_name, save_dir=images_dir)
    if fetched_path:
        return fetched_path

    print(f"ERROR: Could not find or fetch image for {player_name} (normalized: {normalized_p_name})")
    return None

def process_image_to_fill(img, target_width, target_height):
    original_width, original_height = img.size
    if original_width == 0 or original_height == 0:
        print("ERROR: Input image has zero dimension.", file=sys.stderr)
        return Image.new('RGBA', (target_width, target_height), (255,0,0,255)) # Return a red error image

    target_ratio = target_width / target_height
    original_ratio = original_width / original_height

    if original_ratio > target_ratio: # Image is wider than target aspect ratio
        new_height = target_height
        new_width = int(original_ratio * new_height)
    else: # Image is taller than target aspect ratio (or same)
        new_width = target_width
        new_height = int(new_width / original_ratio)

    # Ensure new dimensions are positive
    if new_width <= 0 or new_height <= 0:
        print(f"Warning: Calculated resize dimension non-positive ({new_width}x{new_height}). Resizing to target directly.")
        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    try:
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    except ValueError: # Should be rare with positive new_width/new_height
        print(f"Warning: ValueError resizing image. Resizing to target directly.")
        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Center crop
    left = max(0, (new_width - target_width) / 2)
    top = max(0, (new_height - target_height) / 2)
    # Ensure right and bottom are not less than left and top
    right = min(new_width, left + target_width)
    bottom = min(new_height, top + target_height)

    crop_box = (int(left), int(top), int(right), int(bottom))

    # Validate crop box before cropping
    if crop_box[0] >= crop_box[2] or crop_box[1] >= crop_box[3]:
        print(f"Warning: Invalid crop box {crop_box}. Returning resized image without crop, fitting to target.")
        return img_resized.resize((target_width, target_height), Image.Resampling.LANCZOS)

    img_cropped = img_resized.crop(crop_box)

    # Final resize to ensure exact dimensions if crop had minor deviations
    if img_cropped.size != (target_width, target_height):
        img_cropped = img_cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

    return img_cropped

# These variables will be used by draw_text_box and create_graphic
# They are defined globally here for simplicity in this context,
# but ideally would be encapsulated in a class or passed around.
text_layer = None
draw = None

def draw_text_box(
    text,
    font,
    position,
    box_type="corner", # "player" or "corner"
    align="left",
    flag_img=None
):
    global text_layer, draw # Crucial: make sure these are the global ones initialized in create_graphic
    cfg = TEXT_BOX_CONFIG # Assumes TEXT_BOX_CONFIG is globally defined in bot.py
    x, y = position

    # Calculate text bounding box first to determine dynamic size if not 'player' type
    # For multiline text, bbox needs to be calculated on the drawing object
    # Create a temporary draw object on a temp image if draw is None (should not happen if called from create_graphic)
    current_draw_obj = draw if draw else ImageDraw.Draw(Image.new("RGBA", (1,1)))

    # Calculate text metrics
    # Note: textbbox might not support 'spacing' directly for all Pillow versions.
    # If issues arise, consider line-by-line drawing and height calculation.
    lines = text.split('\n')
    max_line_width = 0
    total_text_height = 0
    line_heights = []

    for i, line in enumerate(lines):
        line_bbox = current_draw_obj.textbbox((0,0), line, font=font)
        line_width = line_bbox[2] - line_bbox[0]
        line_height = line_bbox[3] - line_bbox[1]
        max_line_width = max(max_line_width, line_width)
        total_text_height += line_height
        line_heights.append(line_height)
        if i < len(lines) - 1:
            total_text_height += cfg["line_spacing"]


    if box_type == "player":
        bg_width = cfg.get("player_box_width")
        bg_height = cfg.get("player_box_height")
        half_width = PLAYER_AREA_WIDTH # Assumes PLAYER_AREA_WIDTH is global

        # Player boxes are centered within their half (left or right)
        # The 'x' in position for player boxes refers to the start of their half (0 for left, PLAYER_AREA_WIDTH for right)
        bg_container_x_start = x
        bg_left = bg_container_x_start + (half_width - bg_width) // 2

        text_x_offset = cfg["bg_padding_x"]
        # Text alignment within the player box
        if align == "center": # Example, if you want to center short player names
             # This simple centering works if text_width is known and less than bg_width - 2*padding
             # For multiline, it's more complex; for now, sticking to align for multiline_text
             pass # Defaulting to left/right as per multiline_text align param

        text_x = bg_left + text_x_offset
        bg_top = y # y is the absolute y position for the top of the box
        text_y = bg_top + cfg["bg_padding_y"]

    else:  # "corner" or fallback: dynamic sizing
        text_width = max_line_width
        text_actual_height = total_text_height

        bg_width = text_width + 2 * cfg["bg_padding_x"]
        bg_height = text_actual_height + 2 * cfg["bg_padding_y"]

        if align == "right":
            # x in position for corner text is the right margin from the edge of the canvas (OUTPUT_WIDTH)
            bg_left = OUTPUT_WIDTH - x - bg_width # x is margin from right edge
            text_x = bg_left + cfg["bg_padding_x"]
        else: # align == "left"
            # x in position for corner text is the left margin from the edge of the canvas
            bg_left = x # x is margin from left edge
            text_x = bg_left + cfg["bg_padding_x"]
        bg_top = y # y is the absolute y position for the top of the box (margin from top)
        text_y = bg_top + cfg["bg_padding_y"]

    # Draw background box
    bg_color_rgb = Image.new("RGB", (1,1), cfg["bg_color"]).getpixel((0,0)) # Convert named color to RGB tuple
    bg_color_rgba = bg_color_rgb + (cfg["bg_opacity"],)
    bg_box_coords = (bg_left, bg_top, bg_left + bg_width, bg_top + bg_height)

    # Ensure text_layer and draw are initialized (should be by create_graphic)
    if text_layer is None or draw is None:
        print("ERROR: text_layer or draw not initialized before draw_text_box", file=sys.stderr)
        return

    draw.rounded_rectangle(
        bg_box_coords,
        radius=cfg["bg_radius"],
        fill=bg_color_rgba
    )

    if flag_img:
        try:
            # Resize flag to fit, maintaining aspect, then place it appropriately
            # Example: Place flag to the left of text, or as part of background
            # This is a simplified version, might need more sophisticated placement logic
            flag_max_height = bg_height - 2 * cfg["bg_padding_y"] # Max height for flag inside padding
            flag_aspect_ratio = flag_img.width / flag_img.height

            resized_h = int(flag_max_height * 0.6) # Make flag smaller than box text part
            resized_w = int(resized_h * flag_aspect_ratio)

            if resized_w > (bg_width - 2 * cfg["bg_padding_x"])*0.3: # Limit width to 30% of box
                resized_w = int((bg_width - 2 * cfg["bg_padding_x"])*0.3)
                resized_h = int(resized_w / flag_aspect_ratio)

            if resized_h > 0 and resized_w > 0 :
                flag_to_paste = flag_img.resize((resized_w, resized_h), Image.Resampling.LANCZOS)

                # Paste flag inside the box, e.g., top-right or integrated into design
                # This example pastes it into the background, blurred and with opacity
                flag_bg_resized = flag_img.resize((int(bg_width), int(bg_height)), Image.Resampling.LANCZOS)
                flag_bg_blurred = flag_bg_resized.filter(ImageFilter.GaussianBlur(radius=3)) # More blur
                flag_bg_transparent = reduce_opacity(flag_bg_blurred, 70) # More transparent

                # Create a mask for rounded corners for the flag background
                flag_mask = Image.new("L", (int(bg_width), int(bg_height)), 0)
                mask_draw = ImageDraw.Draw(flag_mask)
                mask_draw.rounded_rectangle((0, 0, bg_width, bg_height), radius=cfg["bg_radius"], fill=255)

                # Paste flag background onto text_layer, not canvas, then text over it
                text_layer.paste(flag_bg_transparent, (int(bg_left), int(bg_top)), mask=flag_mask)
            else:
                print(f"Warning: Calculated flag dimensions too small or invalid: {resized_w}x{resized_h}")

        except Exception as e:
            print(f"Warning: Could not process or paste flag image: {e}")


    # Draw text outline (for sharpness/emphasis) - optional
    # This can make text look bolder or have a slight border
    # outline_color = (0,0,0,128) # Semi-transparent black
    # for ox_outline in [-1, 1]:
    #     for oy_outline in [-1, 1]:
    #         draw.multiline_text(
    #             (text_x + ox_outline, text_y + oy_outline),
    #             text, font=font, fill=outline_color,
    #             spacing=cfg["line_spacing"], align=align
    #         )

    # Draw text shadow
    shadow_x = text_x + cfg["shadow_offset"][0]
    shadow_y = text_y + cfg["shadow_offset"][1]
    draw.multiline_text(
        (shadow_x, shadow_y),
        text,
        font=font,
        fill=cfg["shadow_color"],
        spacing=cfg["line_spacing"],
        align=align
    )

    # Main text
    draw.multiline_text(
        (text_x, text_y),
        text,
        font=font,
        fill=cfg["text_color"],
        spacing=cfg["line_spacing"],
        align=align
    )
    print(f"INFO: {box_type.capitalize()} text box drawn for text starting with '{text.splitlines()[0][:30]}...' at approx ({int(bg_left)}, {int(bg_top)})")


def create_graphic(
    player1_info: dict,
    player2_info: dict,
    corner_text: str, # This is the H2H and last match info
    city_name: str,   # City of the tournament for background
    output_filename="match_preview.png"
):
    global text_layer, draw, player_name_font # Ensure player_name_font is accessible (loaded globally)

    player1_name = player1_info.get("name", "Player 1")
    player2_name = player2_info.get("name", "Player 2")

    print(f"--- Starting Graphic Generation for {output_filename} ---")
    print(f"P1: {player1_name}, P2: {player2_name}, City: {city_name}")
    # print(f"Corner Text Content:
{corner_text}") # Can be long

    # --- 1. Prepare Background ---
    canvas = None
    background_img_path = None
    if city_name and isinstance(city_name, str) and city_name.strip():
        background_img_path = find_or_fetch_background_image(city_name, search_dir=BACKGROUND_DIRECTORY, access_key=UNSPLASH_ACCESS_KEY)

    if background_img_path:
        try:
            print(f"Loading background: {os.path.basename(background_img_path)}")
            background_img = Image.open(background_img_path).convert("RGB") # Convert to RGB first
            canvas_background = process_image_to_fill(background_img, OUTPUT_WIDTH, OUTPUT_HEIGHT)

            if BACKGROUND_BLUR_RADIUS > 0:
                print(f"Applying Gaussian blur (radius: {BACKGROUND_BLUR_RADIUS})...")
                canvas_background = canvas_background.filter(ImageFilter.GaussianBlur(radius=BACKGROUND_BLUR_RADIUS))

            canvas_background = canvas_background.convert("RGBA") # Convert to RGBA for opacity

            if BACKGROUND_OPACITY < 255:
                print(f"Applying opacity ({BACKGROUND_OPACITY}/255)...")
                # canvas_background = reduce_opacity(canvas_background, BACKGROUND_OPACITY) # reduce_opacity can be used here
                alpha = Image.new('L', canvas_background.size, color=BACKGROUND_OPACITY)
                canvas_background.putalpha(alpha)

            canvas = canvas_background
            print("Background image processed and set.")
        except FileNotFoundError:
            print(f"ERROR: Background image file not found at '{background_img_path}'. Using default.", file=sys.stderr)
            canvas = None
        except Exception as e:
            print(f"ERROR: Failed to load/process background image '{background_img_path}': {e}", file=sys.stderr)
            canvas = None

    if canvas is None:
        print("Using default white background.")
        canvas = Image.new('RGBA', (OUTPUT_WIDTH, OUTPUT_HEIGHT), (255, 255, 255, 255))

    # --- 2. Load and Process Player Images ---
    # These paths should come from get_player_image_path which normalizes and tries to fetch
    player1_img_path = get_player_image_path(player1_name, images_dir=IMAGE_DIRECTORY)
    player2_img_path = get_player_image_path(player2_name, images_dir=IMAGE_DIRECTORY)

    if not player1_img_path:
        print(f"ERROR: Could not find or fetch image for Player 1 ({player1_name}). Aborting graphic generation for this player.", file=sys.stderr)
        # Optionally, use a placeholder image for P1
    if not player2_img_path:
        print(f"ERROR: Could not find or fetch image for Player 2 ({player2_name}). Aborting graphic generation for this player.", file=sys.stderr)
        # Optionally, use a placeholder image for P2

    # Initialize processed images to None or placeholders
    img1_processed = None
    img2_processed = None

    try:
        if player1_img_path:
            img1 = Image.open(player1_img_path).convert("RGBA")
            img1_processed = process_image_to_fill(img1, PLAYER_AREA_WIDTH, PLAYER_AREA_HEIGHT)
            print(f"Player 1 image ({player1_name}) processed.")
        if player2_img_path:
            img2 = Image.open(player2_img_path).convert("RGBA")
            img2_processed = process_image_to_fill(img2, PLAYER_AREA_WIDTH, PLAYER_AREA_HEIGHT)
            print(f"Player 2 image ({player2_name}) processed.")
    except FileNotFoundError as fnf_e:
        print(f"ERROR: Player image file not found during open: {fnf_e}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Failed to load or process player images: {e}", file=sys.stderr)
        # Depending on desired behavior, you might want to return False or continue with placeholders

    # --- 3. Paste Player Images (Bottom Aligned) ---
    if img1_processed:
        print(f"Pasting Player 1 image at Y={PLAYER_PASTE_Y}...")
        canvas.paste(img1_processed, (0, PLAYER_PASTE_Y), img1_processed) # Use RGBA mask from image itself
    else:
        print(f"Skipping paste for Player 1 ({player1_name}) due to missing image.")

    if img2_processed:
        print(f"Pasting Player 2 image at Y={PLAYER_PASTE_Y}...")
        canvas.paste(img2_processed, (PLAYER_AREA_WIDTH, PLAYER_PASTE_Y), img2_processed)
    else:
        print(f"Skipping paste for Player 2 ({player2_name}) due to missing image.")

    # --- 4. Prepare Text Layer ---
    # text_layer and draw are now global, initialized here for each graphic
    text_layer = Image.new('RGBA', canvas.size, (0,0,0,0)) # Transparent layer for text
    draw = ImageDraw.Draw(text_layer) # Drawing context for the text layer

    # --- 5. Add Text Elements ---
    print("Adding text elements...")
    try:
        p1_details = player1_info.get("details", {})
        p2_details = player2_info.get("details", {})

        p1_country_code_orig = p1_details.get('country') # This is likely alpha-3 from tennisabstract
        p2_country_code_orig = p2_details.get('country')

        def get_valid_flag_code(country_code_alpha3_or_2):
            if not country_code_alpha3_or_2: return None
            code = str(country_code_alpha3_or_2).strip().upper()
            if len(code) == 3:
                # Specific common mappings before pycountry, if needed
                if code == 'GER': return 'de'
                # Add other common non-standard codes if tennisabstract uses them
                return alpha3_to_alpha2(code) # alpha3_to_alpha2 returns lowercase alpha-2 or None
            elif len(code) == 2:
                return code.lower() # Already alpha-2, ensure lowercase
            print(f"Cannot determine valid alpha-2 code from: {country_code_alpha3_or_2}")
            return None

        p1_flag_code_alpha2 = get_valid_flag_code(p1_country_code_orig)
        p2_flag_code_alpha2 = get_valid_flag_code(p2_country_code_orig)

        p1_flag_img = get_flag_image(p1_flag_code_alpha2) if p1_flag_code_alpha2 else None
        p2_flag_img = get_flag_image(p2_flag_code_alpha2) if p2_flag_code_alpha2 else None

        p1_elo = format_stat(p1_details.get('elo_rank'), 'N/A')
        p1_season_wl = format_stat(player1_info.get('season_wl'), 'N/A') # From main player_info dict

        p2_elo = format_stat(p2_details.get('elo_rank'), 'N/A')
        p2_season_wl = format_stat(player2_info.get('season_wl'), 'N/A')

        # Player text construction
        # p1_text = f"{player1_name.upper()} {('(' + p1_country_code_orig + ')' if p1_country_code_orig else '')}\nELO: {p1_elo} | Rank: {p1_details.get('rank_text', 'N/A')}\nSeason W/L: {p1_season_wl}"
        # p2_text = f"{player2_name.upper()} {('(' + p2_country_code_orig + ')' if p2_country_code_orig else '')}\nELO: {p2_elo} | Rank: {p2_details.get('rank_text', 'N/A')}\nSeason W/L: {p2_season_wl}"
        p1_text = f"{player1_name.upper()}\nELO: {p1_elo} | Season: {p1_season_wl}"
        p2_text = f"{player2_name.upper()}\nELO: {p2_elo} | Season: {p2_season_wl}"


        player_box_y_position_setting = TEXT_BOX_CONFIG.get("player_box_position", "bottom")
        player_box_fixed_height = TEXT_BOX_CONFIG.get("player_box_height", 100) # Default if not set

        # Y position calculation for player info boxes
        if player_box_y_position_setting == "bottom":
            # Place box relative to the bottom of the image, above player image if player image is very tall
            # Or fixed offset from overall image bottom if player image area is not full height
            player_info_y = OUTPUT_HEIGHT - player_box_fixed_height - PLAYER_BOTTOM_PADDING - 20 # 20px margin from bottom
        elif player_box_y_position_setting == "top":
            # Place box relative to the top of the player image area
            player_info_y = PLAYER_PASTE_Y + 20 # 20px margin from top of player image area
        elif player_box_y_position_setting == "middle":
            # Center of the player image area, adjusted by box height
            player_info_y = PLAYER_PASTE_Y + (PLAYER_AREA_HEIGHT // 2) - (player_box_fixed_height // 2)
        else: # Default to bottom
            player_info_y = OUTPUT_HEIGHT - player_box_fixed_height - PLAYER_BOTTOM_PADDING - 20

        print(f"Positioning player info boxes at Y={player_info_y} (mode: {player_box_y_position_setting})")

        # Player 1 Info Box
        draw_text_box(
            text=p1_text, font=player_name_font,
            position=(0, player_info_y), # X=0 for left half
            box_type="player", align="left", # Align text inside the box
            flag_img=p1_flag_img
        )
        # Player 2 Info Box
        draw_text_box(
            text=p2_text, font=player_name_font,
            position=(PLAYER_AREA_WIDTH, player_info_y), # X=PLAYER_AREA_WIDTH for right half
            box_type="player", align="left",
            flag_img=p2_flag_img
        )

        # Corner Text (H2H info, etc.)
        if corner_text and corner_text.strip():
            print("Adding Corner text (H2H, etc.)...")
            # Position from top-right corner. (margin_x_from_right, margin_y_from_top)
            corner_x_margin = TEXT_BOX_CONFIG.get("x_margin", 40)
            corner_y_margin = 30 # Fixed top margin for corner text
            draw_text_box(
                corner_text, player_name_font, # Potentially use a smaller font for corner text
                position=(corner_x_margin, corner_y_margin),
                box_type="corner", align="right" # Aligns box to the right based on x_margin
            )
        else:
            print("INFO: Corner text is empty. Skipping.")

    except Exception as e:
        print(f"ERROR: Failed during text drawing: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc() # Print full traceback for debugging

    # --- 6. Composite Text Layer onto Canvas ---
    print("Compositing text layer onto canvas...")
    canvas = Image.alpha_composite(canvas, text_layer)

    # --- 7. Save Final Image ---
    output_format = output_filename.split('.')[-1].upper()
    save_image = canvas
    if output_format in ('JPG', 'JPEG'): # Handle JPEG conversion which doesn't support alpha
        print("Converting to RGB for JPEG output.")
        # Create a new RGB image and paste the RGBA canvas onto it using alpha channel as mask
        final_rgb = Image.new("RGB", canvas.size, (255, 255, 255)) # White background
        final_rgb.paste(canvas, (0,0), canvas) # Paste using RGBA's alpha
        save_image = final_rgb

    try:
        print(f"Saving final graphic as {output_filename}...")
        # Ensure output directory exists if filename includes path
        output_dir = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        save_image.save(output_filename)
        print(f"--- Graphic created successfully: {output_filename} ---")
        return output_filename # Return path to the created graphic
    except Exception as e:
        print(f"ERROR: Failed to save image '{output_filename}': {e}", file=sys.stderr)
        return None # Return None if saving failed

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
        keyboard.add('2025','2024', '2023', 'Other')
        msg = bot.send_message(message.chat.id, 'Please choose a year:', reply_markup=keyboard)
        bot.register_next_step_handler(msg, lambda m: process_compare_year_step(m, p1, p2))
    except Exception as e:
        bot.reply_to(message, 'An error occurred while processing the second player name.')

def process_compare_year_step(message, p1, p2):
    try:
        year_text = message.text
        if year_text == 'Other':
            years = [str(y) for y in range(2000, 2023)[::-1]]
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
    p2 = message.text
    chat_id = message.chat.id
    bot.send_message(chat_id, f"Fetching H2H data for {p1} vs {p2}. This might take a moment...")
    try:
        # 1. Fetch H2H data and player details
        matches_df = get_player_matches(p1.replace(' ','')) # Main player for match fetching
        
        # Try to get details for both players from tennis_abstract via mod.py functions
        # These functions should ideally return a dictionary or allow easy conversion
        # For now, assuming get_player_matches also fetches some details or we have another way
        
        # Placeholder for full player details (name, country, elo, etc.)
        # These would ideally be fetched from a more comprehensive source or tennis_abstract if available
        # For the graphic, we need: name, country (for flag), elo_rank, season_wl
        # Assuming get_player_matches for p1 might return some of p1's details
        # And we might need a similar call for p2 if not in matches_df comprehensively

        # Simplified: try to get some basic info for graphic
        # This part needs robust data fetching for player details.
        # Using placeholder data structure for player_info dicts.
        
        # Attempt to get details for Player 1
        p1_matches_df = get_player_matches(p1.replace(' ',''))
        p1_career_stats = calculate_yearly_stats(p1_matches_df)
        p1_latest_year_stats = p1_career_stats.iloc[-1] if not p1_career_stats.empty else pd.Series()

        # Attempt to get details for Player 2
        p2_matches_df = get_player_matches(p2.replace(' ',''))
        p2_career_stats = calculate_yearly_stats(p2_matches_df)
        p2_latest_year_stats = p2_career_stats.iloc[-1] if not p2_career_stats.empty else pd.Series()

        player1_info = {
            "name": p1,
            "details": { # These would come from a more detailed player profile fetch
                "country": p1_latest_year_stats.get("country_id", "USA"), # Default or placeholder
                "elo_rank": p1_latest_year_stats.get("current_elo_rank", "N/A"),
                # Add other details if available, like current_rank_text
            },
            "season_wl": f"{p1_latest_year_stats.get('wins', 0)}-{p1_latest_year_stats.get('losses', 0)}"
        }

        player2_info = {
            "name": p2,
            "details": {
                "country": p2_latest_year_stats.get("country_id", "CAN"), # Default or placeholder
                "elo_rank": p2_latest_year_stats.get("current_elo_rank", "N/A"),
            },
            "season_wl": f"{p2_latest_year_stats.get('wins', 0)}-{p2_latest_year_stats.get('losses', 0)}"
        }

        # 2. Format H2H matches and determine summary text
        h2h_data = format_h2h_matches(matches_df, p1, p2) # This is for p1 vs p2

        if h2h_data.empty:
            bot.send_message(chat_id, f"No H2H matches found between {p1} and {p2}.")
            show_command_menu(chat_id)
            return

        p1_wins = len(h2h_data[h2h_data.winner_name == p1])
        p2_wins = len(h2h_data[h2h_data.winner_name == p2])

        last_match = h2h_data.iloc[-1]
        last_tournament_name = last_match['tournament']
        # Ensure match_date is datetime to extract year
        if isinstance(last_match['match_date'], str):
            last_match_year = pd.to_datetime(last_match['match_date']).year
        else: # Assuming it's already datetime or Timestamp
            last_match_year = last_match['match_date'].year

        last_tournament_full = f"{last_tournament_name} {last_match_year}"

        # Determine city for background - from last H2H match tournament city if available
        # Needs city info in your 'tournaments.csv' or similar, and loaded by mod.py
        # For now, using a placeholder or trying to extract from tournament name.
        city_name_for_background = "DefaultCity" # Placeholder
        if 'city' in last_match and pd.notna(last_match['city']):
            city_name_for_background = last_match['city']
        else: # Basic extraction attempt if city column not present or NaN
            parts = last_tournament_name.split(" ")
            if len(parts) > 0 : city_name_for_background = parts[0] # Often city is first word

        h2h_summary_text = ""
        if p1_wins > p2_wins:
            h2h_summary_text = f"{p1} leads H2H {p1_wins}-{p2_wins}"
        elif p2_wins > p1_wins:
            h2h_summary_text = f"{p2} leads H2H {p2_wins}-{p1_wins}"
        else:
            h2h_summary_text = f"H2H is tied {p1_wins}-{p2_wins}"

        corner_text = f"{h2h_summary_text}\nLast meeting: {last_tournament_full}"

        # 3. Create the graphic
        # Generate a unique filename to avoid conflicts if multiple users use concurrently
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        normalized_p1 = normalize_name(p1)
        normalized_p2 = normalize_name(p2)
        output_filename = f"h2h_{normalized_p1}_vs_{normalized_p2}_{timestamp}.png"

        bot.send_message(chat_id, "Generating H2H graphic... 🎨")

        graphic_path = create_graphic(
            player1_info=player1_info,
            player2_info=player2_info,
            corner_text=corner_text,
            city_name=city_name_for_background,
            output_filename=output_filename
        )

        # 4. Send the graphic and cleanup
        if graphic_path and os.path.exists(graphic_path):
            try:
                with open(graphic_path, 'rb') as photo_file:
                    bot.send_photo(chat_id, photo_file)
                bot.send_message(chat_id, f"H2H graphic for {p1} vs {p2} generated!")
            except Exception as send_e:
                bot.send_message(chat_id, f"Error sending graphic: {send_e}")
            finally:
                try:
                    os.remove(graphic_path)
                    print(f"Cleaned up image file: {graphic_path}")
                except OSError as remove_e:
                    print(f"Error removing image file {graphic_path}: {remove_e}")
        else:
            bot.send_message(chat_id, "Sorry, there was an error creating the H2H graphic.")

        show_command_menu(chat_id)

    except Exception as e:
        logging.error(f"Error in process_h2h_player2_step for {p1} vs {p2}: {e}", exc_info=True)
        bot.reply_to(message, f"An error occurred while processing H2H for {p1} vs {p2}: {e}. Please try again or contact support if the issue persists.")
        show_command_menu(chat_id)

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
