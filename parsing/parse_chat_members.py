"""
============================================================
            Parse Chat Members (parse_chat_members.py)
============================================================
Purpose:
  Parses members (username, name, bio) from specified Telegram
  channels/groups using a randomly selected handler account.
  Saves results to a CSV file.

Key Features:
  - Uses a randomly selected account with a _SESSION_HANDLER session.
  - Loads target chat usernames/links from data/chats_to_parse.txt.
  - Handles proxy configurations (direct SOCKS5 or via HTTP bridge).
  - Parses participants using GetParticipantsRequest with search filter.
  - Fetches user bios using GetFullUserRequest (with limits).
  - Implements increased delays and FloodWaitError handling for safety.
  - Limits number of chats processed per run.
  - Limits number of bios fetched per run.
  - Saves results to data/parsed_users.csv (deduplicated).
  - Includes basic entity caching.

Configuration:
  - .env file: ACCOUNTS list, and for the selected account:
               API_ID, API_HASH, PHONE, _SESSION_HANDLER, PROXY (optional).
               Optional: PARSING_* variables for delays, limits, ports.
  - data/chats_to_parse.txt: List of target chat usernames or links.

Usage:
  python parsing/parse_chat_members.py
============================================================
"""

import asyncio
import os
import random
import time
import logging
import re
import sys
import subprocess
import atexit
import dotenv
import csv
from typing import List, Tuple, Set, Optional, Dict, Any, Union
from tqdm import tqdm # For progress bar

# --- Telethon Imports ---
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import ChannelParticipantsSearch, User, Channel, Chat # Specific types
from telethon.errors import (
    FloodWaitError, UserDeactivatedBanError, AuthKeyError, ChannelPrivateError,
    ChatAdminRequiredError, UserNotParticipantError, UserPrivacyRestrictedError
)

# --- Environment Setup ---
try:
    import python_socks
except ImportError:
    try: import socks
    except ImportError:
        print("ERROR: python-socks or pysocks library is not found. Please install using: pip install pysocks")
        sys.exit(1)

# --- Load .env ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
dotenv.load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, '.env'))

# --- Paths ---
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
SESSIONS_DIR = os.path.join(PROJECT_ROOT, 'sessions')
BRIDGE_SCRIPT_PATH = os.path.join(SCRIPT_DIR, "simple_http_socks_bridge.py")

# --- Configuration ---
def _get_int_env(key: str, default: int) -> int:
    try: return int(os.getenv(key, default))
    except (ValueError, TypeError): return default
def _get_float_env(key: str, default: float) -> float:
    try: return float(os.getenv(key, default))
    except (ValueError, TypeError): return default

CHAT_LIST_FILE = os.path.join(DATA_DIR, "chats_to_parse.txt")
OUTPUT_CSV_FILE = os.path.join(DATA_DIR, "parsed_users.csv")
SESSION_SUFFIX_VAR = "_SESSION_HANDLER" # Use handler sessions

# Delays and Limits (Increased defaults for safety)
GET_ENTITY_DELAY_MIN = _get_float_env("PARSING_ENTITY_DELAY_MIN", 3.0)
GET_ENTITY_DELAY_MAX = _get_float_env("PARSING_ENTITY_DELAY_MAX", 8.0)
ITER_PARTICIPANTS_DELAY_MIN = _get_float_env("PARSING_ITER_PART_DELAY_MIN", 1.0)
ITER_PARTICIPANTS_DELAY_MAX = _get_float_env("PARSING_ITER_PART_DELAY_MAX", 3.5)
GET_BIO_DELAY_MIN = _get_float_env("PARSING_BIO_DELAY_MIN", 1.5)
GET_BIO_DELAY_MAX = _get_float_env("PARSING_BIO_DELAY_MAX", 4.0)
INTER_CHAT_DELAY_MIN = _get_float_env("PARSING_INTER_CHAT_DELAY_MIN", 15.0) # Delay between chats
INTER_CHAT_DELAY_MAX = _get_float_env("PARSING_INTER_CHAT_DELAY_MAX", 45.0)
FLOOD_WAIT_BUFFER = _get_float_env("PARSING_FLOOD_WAIT_BUFFER", 10.0) # Increased buffer

MAX_CHATS_PER_RUN = _get_int_env("PARSING_MAX_CHATS_PER_RUN", 10) # Limit chats per run
MAX_BIOS_PER_RUN = _get_int_env("PARSING_MAX_BIOS_PER_RUN", 500) # Limit bios fetched per run

# Proxy Settings
PARSING_SOCKS_BASE_PORT = int(os.getenv("PARSING_SOCKS_BASE_PORT", "9080"))
USE_PROXIES_PARSING = os.getenv("USE_PROXIES", "false").strip().lower() in ("true", "1", "yes", "on")

# --- Logging ---
log_level_str = "DEBUG" if os.getenv("DEBUG_MODE", "false").lower() == "true" else "INFO"
log_level = logging.getLevelName(log_level_str.upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(account_phone)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger('telethon').setLevel(logging.WARNING)
logger = logging.getLogger("ParseMembers")

# --- Global ---
running_bridge_processes_parser: List[Tuple[subprocess.Popen, int, str]] = []
entity_cache: Dict[str, Optional[Union[Channel, Chat]]] = {} # Cache for get_entity results

# ============================================================
# SECTION: Proxy Bridge Management
# ============================================================
def start_simple_bridge_process_parser(remote_http_proxy_url: str, local_listen_port: int) -> Optional[subprocess.Popen]:
    """Launches the simple_http_socks_bridge.py script."""
    adapter = logging.LoggerAdapter(logger, {'account_phone': 'System'})
    if not os.path.exists(BRIDGE_SCRIPT_PATH):
        adapter.error(f"Bridge script not found: {BRIDGE_SCRIPT_PATH}")
        return None
    command = [ sys.executable, BRIDGE_SCRIPT_PATH, '--listen-port', str(local_listen_port), '--remote-proxy', remote_http_proxy_url ]
    if log_level <= logging.DEBUG: command.append('--verbose')
    adapter.info(f"Launching bridge process: {' '.join(command)}")
    try:
        process = subprocess.Popen( command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8' )
        time.sleep(3.0); exit_code = process.poll()
        if exit_code is not None:
            stderr_output = process.stderr.read()
            adapter.error(f"Bridge process on port {local_listen_port} exited immediately (code: {exit_code}). Stderr: {stderr_output.strip()}")
            return None
        else:
            adapter.info(f"Bridge process running: 127.0.0.1:{local_listen_port} -> {remote_http_proxy_url} (PID: {process.pid})")
            return process
    except Exception as e:
        adapter.error(f"Exception launching bridge process for {remote_http_proxy_url}: {e}", exc_info=log_level <= logging.DEBUG)
        return None

def cleanup_bridge_processes_parser():
    """Stops all running bridge subprocesses."""
    global running_bridge_processes_parser
    if not running_bridge_processes_parser: return
    adapter = logging.LoggerAdapter(logger, {'account_phone': 'System'})
    adapter.info(f"Stopping {len(running_bridge_processes_parser)} background bridge processes...")
    processes_to_stop = list(running_bridge_processes_parser)
    running_bridge_processes_parser.clear()
    for proc, port, url in processes_to_stop:
        if proc and proc.poll() is None:
            adapter.info(f"Stopping bridge on port {port} (PID: {proc.pid}) for {url}")
            try: proc.terminate(); proc.wait(timeout=3)
            except subprocess.TimeoutExpired: adapter.warning(f"Bridge PID {proc.pid} did not stop gracefully, killing..."); proc.kill(); time.sleep(0.5)
            except Exception as e: adapter.error(f"Error stopping bridge PID {proc.pid}: {e}")
    adapter.info("Bridge process cleanup finished.")

atexit.register(cleanup_bridge_processes_parser)

# ============================================================
# SECTION: Account Loading
# ============================================================
def load_random_handler_account() -> Optional[Dict[str, Any]]:
    """Loads data for a single, randomly selected handler account."""
    adapter = logging.LoggerAdapter(logger, {'account_phone': 'System'})
    account_ids_str = os.getenv("ACCOUNTS", "")
    if not account_ids_str: adapter.error("ACCOUNTS variable not found in .env!"); return None
    all_suffixes = [s.strip() for s in account_ids_str.split(',') if s.strip()]
    if not all_suffixes: adapter.error("No account suffixes found in ACCOUNTS variable."); return None

    random.shuffle(all_suffixes)
    selected_account = None
    for suffix in all_suffixes:
        api_id = os.getenv(f"{suffix}_API_ID"); api_hash = os.getenv(f"{suffix}_API_HASH")
        phone = os.getenv(f"{suffix}_PHONE"); session = os.getenv(f"{suffix}{SESSION_SUFFIX_VAR}")

        if all([api_id, api_hash, phone, session]):
            adapter.info(f"Selected random account for parsing: {suffix} (Phone: {phone})")
            proxy_str = os.getenv(f"{suffix}_PROXY"); proxy_value = None; proxy_type_log = "no"
            if USE_PROXIES_PARSING and proxy_str:
                proxy_str = proxy_str.strip()
                if proxy_str.startswith("socks5://"):
                     proxy_type_log = "socks5"; cleaned = proxy_str.replace("socks5://", ""); match = re.match(r"(?:([\w\-\.%]+):([\w\-\.%!@#$&*]+)@)?([\w\-\.]+):(\d+)", cleaned)
                     if match: user, pwd, host, port_str = match.groups(); port = int(port_str); t = python_socks.ProxyType.SOCKS5 if 'python_socks' in sys.modules else "socks5"; proxy_value = (t, host, port, True, user, pwd) if user and pwd else (t, host, port)
                     else: adapter.warning(f"Invalid SOCKS5 format for '{suffix}'.")
                elif proxy_str.startswith("http"): proxy_type_log = "http(s)"; proxy_value = proxy_str
                else: adapter.warning(f"Unsupported proxy type for '{suffix}'.")
            elif not USE_PROXIES_PARSING and proxy_str: adapter.info("Proxy ignored (USE_PROXIES=false)."); proxy_type_log = "disabled"
            selected_account = { "id": suffix, "session": session, "api_id": int(api_id), "api_hash": api_hash, "phone": phone, "proxy_config": proxy_value }
            adapter.info(f"Account details - Proxy status: {proxy_type_log}")
            break
        else: adapter.debug(f"Account {suffix} skipped (missing handler session or other details).")

    if not selected_account: adapter.error(f"Could not find any valid account with suffix '{SESSION_SUFFIX_VAR}' configured in .env.")
    return selected_account

# ============================================================
# SECTION: Chat and User Parsing Logic
# ============================================================

async def get_chat_entity(client: TelegramClient, chat_identifier: str, phone_number: str) -> Optional[Union[Channel, Chat]]:
    """Safely gets the chat/channel entity, uses cache."""
    global entity_cache
    adapter = logging.LoggerAdapter(logger, {'account_phone': phone_number})
    cache_key = chat_identifier.lower()

    if cache_key in entity_cache:
        adapter.debug(f"Using cached entity for '{chat_identifier}'")
        return entity_cache[cache_key]

    adapter.debug(f"Resolving chat entity for '{chat_identifier}'...")
    entity = None
    try:
        await asyncio.sleep(random.uniform(GET_ENTITY_DELAY_MIN, GET_ENTITY_DELAY_MAX))
        entity = await asyncio.wait_for(client.get_entity(chat_identifier), timeout=30.0)
        if isinstance(entity, (Channel, Chat)):
            adapter.info(f"Found chat: '{getattr(entity, 'title', chat_identifier)}' (ID: {entity.id})")
        else:
            adapter.warning(f"Identifier '{chat_identifier}' resolved to a User, not a chat/channel. Skipping.")
            entity = None
    except FloodWaitError as e: wait_time = e.seconds + FLOOD_WAIT_BUFFER; adapter.warning(f"Flood wait resolving chat '{chat_identifier}'. Waiting {wait_time:.1f}s..."); await asyncio.sleep(wait_time); entity = None
    except (ValueError, errors.UsernameNotOccupiedError, errors.UsernameInvalidError): adapter.error(f"Could not find/resolve chat: '{chat_identifier}'."); entity = None
    except (ChannelPrivateError, ChatAdminRequiredError, UserNotParticipantError): adapter.error(f"Cannot access chat '{chat_identifier}': Private/restricted."); entity = None
    except asyncio.TimeoutError: adapter.error(f"Timeout resolving chat '{chat_identifier}'."); entity = None
    except Exception as e: adapter.error(f"Unexpected error resolving chat '{chat_identifier}': {type(e).__name__}", exc_info=log_level <= logging.DEBUG); entity = None

    entity_cache[cache_key] = entity
    return entity

async def get_user_bio(client: TelegramClient, user_id: int, phone_number: str) -> str:
    """Fetches user bio using GetFullUserRequest with increased delay and error handling."""
    adapter = logging.LoggerAdapter(logger, {'account_phone': phone_number})
    try:
        await asyncio.sleep(random.uniform(GET_BIO_DELAY_MIN, GET_BIO_DELAY_MAX))
        full_user = await asyncio.wait_for(client(GetFullUserRequest(user_id)), timeout=20.0)
        bio = getattr(full_user.full_user, 'about', None)
        # Clean bio: remove newlines and extra spaces for CSV
        return ' '.join(bio.split()) if bio else "N/A"
    except FloodWaitError as e: wait_time = e.seconds + FLOOD_WAIT_BUFFER; adapter.warning(f"Flood wait getting bio for user {user_id}. Waiting {wait_time:.1f}s..."); await asyncio.sleep(wait_time); return "FLOOD_WAIT"
    except errors.UserIdInvalidError: adapter.warning(f"Invalid User ID {user_id} fetching bio."); return "INVALID_ID"
    except UserPrivacyRestrictedError: adapter.debug(f"Bio fetch skipped user {user_id}: Privacy restricted."); return "PRIVACY_RESTRICTED"
    except asyncio.TimeoutError: adapter.warning(f"Timeout getting bio user {user_id}."); return "TIMEOUT"
    except Exception as e:
        log_exc_info = log_level <= logging.DEBUG
        if isinstance(e, (errors.BotMethodInvalidError, errors.UserIsBotError, errors.ReqPmBlockedError, errors.PeerIdInvalidError)): log_exc_info = False
        adapter.warning(f"Error getting bio user {user_id}: {type(e).__name__}", exc_info=log_exc_info); return "ERROR"

async def parse_members(client: TelegramClient, chat_entity: Union[Channel, Chat], chat_identifier: str, bios_remaining_limit: int, phone_number: str) -> Tuple[List[Dict[str, Any]], int]:
    """Parses members, fetches limited bios, returns data and remaining bio limit."""
    adapter = logging.LoggerAdapter(logger, {'account_phone': phone_number})
    adapter.info(f"Starting participant parsing for '{getattr(chat_entity, 'title', chat_identifier)}'...")
    offset = 0
    limit = 200
    parsed_users_batch = [] # Collect results here
    total_participants = None
    try:
        full_chat = await client.get_entity(chat_entity)
        if hasattr(full_chat, 'participants_count'):
            total_participants = full_chat.participants_count
            adapter.info(f"Approximate participants count: {total_participants}")
        else:
            adapter.info("Participants count not available.")
    except Exception as e:
         adapter.warning(f"Could not get participants count: {e}")
         total_participants = None

    tqdm_total = total_participants if isinstance(total_participants, int) and total_participants > 0 else None
    pbar = tqdm(total=tqdm_total,
                desc=f"Parsing @{chat_identifier}", unit=" users", file=sys.stdout, leave=False)
    flood_wait_total_participants = 0
    flood_wait_total_bios = 0

    while True:
        participants_result = None
        try:
            participants_result = await asyncio.wait_for(client(GetParticipantsRequest(
                channel=chat_entity, filter=ChannelParticipantsSearch(''), offset=offset, limit=limit, hash=0
            )), timeout=45.0)

            if not participants_result or not participants_result.users: break

            batch_users = participants_result.users
            adapter.debug(f"Processing batch of {len(batch_users)} participants...")

            for user in batch_users:
                if user.bot or user.deleted:
                    pbar.update(1); continue

                user_id = user.id; username = user.username if user.username else "N/A"
                first_name = user.first_name if user.first_name else "N/A"; last_name = user.last_name if user.last_name else "N/A"
                phone = user.phone if user.phone else "N/A"

                bio = "N/A"
                if bios_remaining_limit > 0:
                    bio = await get_user_bio(client, user.id, phone_number)
                    while bio == "FLOOD_WAIT":
                        flood_wait_total_bios += 1; adapter.warning("Retrying bio fetch after flood wait...")
                        bio = await get_user_bio(client, user.id, phone_number)

                    if bio not in ["FLOOD_WAIT", "INVALID_ID", "TIMEOUT", "ERROR", "PRIVACY_RESTRICTED"]:
                        bios_remaining_limit -= 1 # Decrement limit only on success/valid skip
                else: bio = "N/A (Bio Limit Reached)"

                parsed_users_batch.append({
                    "ID": user_id, "Username": username, "First Name": first_name,
                    "Last Name": last_name, "Phone": phone, "Bio": bio,
                    "Chat Name": f"@{chat_identifier}"
                })
                pbar.update(1)

            offset += len(batch_users)
            await asyncio.sleep(random.uniform(ITER_PARTICIPANTS_DELAY_MIN, ITER_PARTICIPANTS_DELAY_MAX))

        except FloodWaitError as e:
            wait_time = e.seconds + FLOOD_WAIT_BUFFER; adapter.warning(f"Flood wait error fetching participants. Waiting {wait_time:.1f}s...")
            pbar.set_postfix_str(f"FLOOD WAIT {int(wait_time)}s"); flood_wait_total_participants += 1; await asyncio.sleep(wait_time); pbar.set_postfix_str(""); continue
        except (TypeError, ValueError) as e: adapter.error(f"Type/Value error fetching participants: {e}. Stopping parse for this chat."); break
        except asyncio.TimeoutError: adapter.error("Timeout fetching participants batch. Stopping parse for this chat."); break
        except Exception as e: adapter.error(f"Unexpected error fetching participants: {e}. Stopping parse for this chat.", exc_info=log_level <= logging.DEBUG); break

    pbar.close()
    if flood_wait_total_participants > 0: adapter.warning(f"Encountered {flood_wait_total_participants} participant flood waits.")
    if flood_wait_total_bios > 0: adapter.warning(f"Encountered {flood_wait_total_bios} bio flood waits.")
    adapter.info(f"Finished processing for '{getattr(chat_entity, 'title', chat_identifier)}'. Found {len(parsed_users_batch)} valid users.")

    return parsed_users_batch, bios_remaining_limit

# ============================================================
# SECTION: Main Orchestration Logic
# ============================================================
async def main():
    system_adapter = logging.LoggerAdapter(logger, {'account_phone': 'System'})

    # 1. Load target chat list
    if not os.path.exists(CHAT_LIST_FILE): system_adapter.error(f"Chat list file not found: {CHAT_LIST_FILE}"); return
    with open(CHAT_LIST_FILE, "r", encoding="utf-8") as f: target_chats = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    if not target_chats: system_adapter.error(f"No valid chat identifiers found in {CHAT_LIST_FILE}"); return

    # Apply chat limit per run
    system_adapter.info(f"Loaded {len(target_chats)} target chats from {CHAT_LIST_FILE}.")
    if len(target_chats) > MAX_CHATS_PER_RUN:
         system_adapter.info(f"Selecting random {MAX_CHATS_PER_RUN} chats to process due to PARSING_MAX_CHATS_PER_RUN limit.")
         target_chats = random.sample(target_chats, MAX_CHATS_PER_RUN)

    # 2. Select and prepare random account
    account_info = load_random_handler_account();
    if not account_info: return
    phone = account_info["phone"]; parser_adapter = logging.LoggerAdapter(logger, {'account_phone': phone})

    # Prepare proxy
    telethon_proxy_config = None
    if USE_PROXIES_PARSING:
        raw_proxy_setting = account_info.get("proxy_config")
        if isinstance(raw_proxy_setting, str) and raw_proxy_setting.startswith("http"):
             parser_adapter.info("HTTP proxy requires bridge. Starting..."); port = PARSING_SOCKS_BASE_PORT
             bridge_process = start_simple_bridge_process_parser(raw_proxy_setting, port)
             if bridge_process:
                 running_bridge_processes_parser.append((bridge_process, port, raw_proxy_setting)); t = python_socks.ProxyType.SOCKS5 if 'python_socks' in sys.modules else "socks5"
                 telethon_proxy_config = {'proxy_type': t, 'addr': '127.0.0.1', 'port': port, 'rdns': True}; parser_adapter.info(f"Using bridge on 127.0.0.1:{port}")
             else: parser_adapter.error("Failed to start bridge. No proxy used.")
        elif isinstance(raw_proxy_setting, tuple): telethon_proxy_config = raw_proxy_setting; parser_adapter.info(f"Using direct SOCKS5 proxy: {raw_proxy_setting[1]}:{raw_proxy_setting[2]}")
        else: parser_adapter.info("No usable proxy config.")

    # 3. Initialize Client and Connect
    session_file_path = os.path.join(SESSIONS_DIR, f"{account_info['session']}.session")
    client = TelegramClient(session_file_path, account_info['api_id'], account_info['api_hash'], proxy=telethon_proxy_config)

    all_parsed_data = []; processed_chats = set(); current_bio_limit = MAX_BIOS_PER_RUN

    try:
        parser_adapter.info("Connecting to Telegram...")
        await asyncio.wait_for(client.connect(), timeout=60.0)
        if not await client.is_user_authorized():
            parser_adapter.warning("Account requires authorization. Attempting..."); await client.start(phone=lambda: phone)
            if not await client.is_user_authorized(): parser_adapter.error("Authorization failed. Cannot proceed."); return
            parser_adapter.info("Authorization successful.")
        else: parser_adapter.info("Account already authorized.")

        # 4. Iterate through selected chats and parse members
        parser_adapter.info(f"Starting to process {len(target_chats)} selected chats...")
        for chat_identifier in target_chats:
            if chat_identifier.lower() in processed_chats: continue
            chat_entity = await get_chat_entity(client, chat_identifier, phone)
            if chat_entity:
                parsed_data, current_bio_limit = await parse_members(client, chat_entity, chat_identifier.lstrip('@'), current_bio_limit, phone)
                all_parsed_data.extend(parsed_data); processed_chats.add(chat_identifier.lower())
                inter_chat_delay = random.uniform(INTER_CHAT_DELAY_MIN, INTER_CHAT_DELAY_MAX); parser_adapter.info(f"--- Pausing {inter_chat_delay:.1f}s before next chat ---"); await asyncio.sleep(inter_chat_delay)
            else: processed_chats.add(chat_identifier.lower())

    except AuthKeyError: parser_adapter.error("Authorization key error. Delete session and re-auth.")
    except UserDeactivatedBanError: parser_adapter.error("Account banned or deactivated.")
    except asyncio.TimeoutError: parser_adapter.error("Connection timed out during operation.")
    except Exception as e: parser_adapter.error(f"An unexpected error occurred: {type(e).__name__} - {e}", exc_info=True)
    finally:
        if client.is_connected(): parser_adapter.info("Disconnecting client..."); await client.disconnect()

    # 5. Save results to CSV
    if all_parsed_data:
        final_data = []; seen_ids = set()
        for user_dict in all_parsed_data:
            user_id = user_dict.get("ID");
            if user_id not in seen_ids: final_data.append(user_dict); seen_ids.add(user_id)
        system_adapter.info(f"Total unique users parsed: {len(final_data)}. Saving to {OUTPUT_CSV_FILE}...")
        try:
            if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
            with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as file:
                if final_data:
                    writer = csv.DictWriter(file, fieldnames=final_data[0].keys()); writer.writeheader(); writer.writerows(final_data)
                    system_adapter.info(f"✅ Successfully saved data to {OUTPUT_CSV_FILE}")
                else: system_adapter.warning("No data to write to CSV (final list empty).")
        except Exception as e: system_adapter.error(f"Failed to write CSV file {OUTPUT_CSV_FILE}: {e}")
    else: system_adapter.warning("No user data was parsed. CSV file not created.")

# ============================================================
# SECTION: Script Entry Point
# ============================================================
if __name__ == "__main__":
    main_adapter = logging.LoggerAdapter(logger, {'account_phone': 'ParserScript'})
    main_adapter.info("🚀 Starting Telegram Member Parser Script...")
    start_time = time.time()
    try:
        if not os.path.exists(SESSIONS_DIR): main_adapter.info(f"Creating sessions directory: {SESSIONS_DIR}"); os.makedirs(SESSIONS_DIR)
        asyncio.run(main())
    except KeyboardInterrupt: main_adapter.info("\n🛑 Script interrupted by user (Ctrl+C).")
    except Exception as e: main_adapter.critical(f"💥 Unhandled exception in main parser loop: {e}", exc_info=True)
    finally:
        end_time = time.time(); duration = end_time - start_time; main_adapter.info(f"🏁 Parser script finished. Total execution time: {duration:.2f} seconds.")