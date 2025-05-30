import re
from datetime import datetime
import os
import json
from urllib.parse import urlparse, parse_qs
import shutil
from tqdm import tqdm

data_path = "./mydata-xxxxxx"
memories_history_path = "./json/memories_history.json"
chat_history_path = "./mydata-xxxxxx/json/chat_history.json"
OUTPUT_PATH = f"./{datetime.now().strftime("%Y-%m-%d at %H-%M")} Snapchat Data Export"
PHOTO_SUFFIX = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff'}
VIDEO_SUFFIX = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
DATE_FILE_NAME_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
IGNORE_FILES = {".DS_Store", ".gitkeep", ".gitignore", "Thumbs.db", "desktop.ini"}


def safe_move(src_path: str, dst_dir: str, move: bool = True) -> str:
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Path does not exists: {src_path}")

    base_name = os.path.basename(src_path)
    name, ext = os.path.splitext(base_name)
    dst_path = os.path.join(dst_dir, base_name)
    counter = 1

    while os.path.exists(dst_path):
        if os.path.isdir(src_path):
            new_name = f"{name} ({counter})"
            dst_path = os.path.join(dst_dir, new_name)
        else:
            new_name = f"{name} ({counter}){ext}"
            dst_path = os.path.join(dst_dir, new_name)
        counter += 1

    if not move:
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)
    else:
        shutil.move(src_path, dst_path)

    return str(dst_path)


def get_all_file_paths(path) -> list[str]:
    file_names = []
    for root, dirs, files in os.walk(path):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            file_names.append(file_path)
    return file_names


def to_found(file_path) -> str:
    found_path = f"{OUTPUT_PATH}/found_files"
    os.makedirs(found_path, exist_ok=True)
    return safe_move(file_path, found_path)


def to_not_found(file_path) -> str:
    found_path = f"{OUTPUT_PATH}/not_found_files"
    os.makedirs(found_path, exist_ok=True)
    return safe_move(file_path, found_path)


def to_passed(file_path, sub_dir: str) -> str:
    found_path = f"{OUTPUT_PATH}/passed_files/{sub_dir}"
    os.makedirs(found_path, exist_ok=True)
    return safe_move(file_path, found_path)


def to_manual_check(file_path, sub_dir, matching_dates=None, found_in_messages=None) -> str:
    found_path = os.path.join(OUTPUT_PATH, "manual_check", sub_dir)
    os.makedirs(found_path, exist_ok=True)
    destination_path = safe_move(file_path, found_path)

    message_map = {
        "date_not_matching_file_name_date": (
            "The oldest found date does not match the date in the file name.\n"
            "The oldest date and time which are in the filename and in the json files will be used"
            "If no date in the json files found which matching the filename date the oldest found date will be used.\n"
            "Please check which date is correct.\n\n"
        ),
        "older_date_than_file_name_date_found": (
            "Found a date in the JSON files which is older than the date in the filename.\n"
            "The oldest date and time which are in the filename and in the json files will be used"
            "If no date in the json files found which matching the filename date the oldest found date will be used.\n"
            "Please check which date is correct.\n\n"
        )
    }

    if sub_dir in message_map:
        with open(destination_path + ".txt", "w", encoding="utf-8") as f:
            f.write(message_map[sub_dir])
            if matching_dates:
                for i in range(len(matching_dates)):
                    f.write(f"{matching_dates[i]} {found_in_messages[i]} \n")

    return destination_path


def check_for_pass_file(file_path) -> bool:
    """
    True if the file was passed
    False if the file was not passed
    """
    if "overlay" in file_path:
        to_passed(file_path, "overlays")
        return True
    if "thumbnail" in file_path:
        to_passed(file_path, "thumbnails")
        return True
    if "metadata" in file_path:
        to_passed(file_path, "metadata")
        return True
    if ("." + file_path.split(".")[-1] not in PHOTO_SUFFIX) and ("." + file_path.split(".")[-1] not in VIDEO_SUFFIX):
        to_passed(file_path, "other_files")
        return True
    return False


def read_all_ids_from_json() -> list[dict[str, str | list[str]]]:
    with open(memories_history_path, "r", encoding="utf-8") as f1, \
         open(chat_history_path, "r", encoding="utf-8") as f2:
        memories_history = json.load(f1)
        chat_history = json.load(f2)

    ids: list[dict[str, str | list[str]]] = []

    for index, entry in enumerate(memories_history.get("Saved Media", [])):
        params = parse_qs(urlparse(entry["Download Link"]).query)
        extracted_ids = [params.get(k, [None])[0] for k in ("sid", "mid", "uid", "sig")]
        ids.append({"date": entry["Date"], "ids": extracted_ids, "found_message": f"Found in memories_history.json at entry: {index}"})

    for messages in chat_history.values():
        for msg in messages:
            if msg.get("Media Type") == "MEDIA" and msg["Media IDs"] != "":
                media_ids = msg.get("Media IDs")
                media_ids = media_ids if isinstance(media_ids, list) else [media_ids]
                # TODO what if msg["Created"] is empty
                ids.append({"date": msg["Created"], "ids": media_ids, "found_message": f"Found in chat_history.json in chat with {msg.get('From')}"})

    return ids


def get_matching_dates(file_path, ids) -> tuple[list[str], datetime | None, datetime | None, list[str]]:
    matching_dates: list[str] = [entry["date"] for entry in ids
                      if any(media_id in file_path for media_id in entry["ids"])]
    found_in_messages: list[str] = [entry["found_message"] for entry in ids
                                 if any(media_id in file_path for media_id in entry["ids"])]

    parsed_dates: list[datetime] = [datetime.strptime(d.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
                    for d in matching_dates]
    if len(matching_dates) == 0:
        return [], None, None, []

    oldest_date = min(parsed_dates)
    file_date = get_datetime_from_file_path(file_path).date()

    same_day_matches = [d for d in parsed_dates if d.date() == file_date]
    oldest_same_day = min(same_day_matches) if same_day_matches else None

    return matching_dates, oldest_date, oldest_same_day, found_in_messages


def handle_found_date(file_path, matching_dates, oldest_date, oldest_same_day, found_in_messages):
    date_from_file_name = get_datetime_from_file_path(file_path)
    if oldest_date.date() != date_from_file_name.date():
        if oldest_same_day is None:
            destination_path = to_manual_check(file_path, "date_not_matching_file_name_date", matching_dates, found_in_messages)
        else:
            destination_path = to_manual_check(file_path, "older_date_than_file_name_date_found", matching_dates, found_in_messages)
        timestamp = oldest_same_day.timestamp() if oldest_same_day is not None else oldest_date.timestamp()
        os.utime(destination_path, (timestamp, timestamp))
    else:
        destination_path = to_found(file_path)
        os.utime(destination_path, (oldest_date.timestamp(), oldest_date.timestamp()))


def get_datetime_from_file_path(file_path: str):
    match = DATE_FILE_NAME_PATTERN.match(os.path.basename(file_path))
    if match:
        year, month, day = map(int, match.groups())
        date = datetime(year, month, day)
        return date
    return None


def remove_copied_folder(copied_data_path):
    remaining_files_found = False
    for root, dirs, files in os.walk(copied_data_path):
        considered_files = [f for f in files if f not in IGNORE_FILES]
        if considered_files:
            print(f"Found remaining file in {root}: {considered_files}")
            remaining_files_found = True
    if remaining_files_found:
        print(f"The copied data folder: '{copied_data_path}' contains remaining files. \n"
              f"These files wasn't considered: Please check them")
    else:
        shutil.rmtree(copied_data_path)


def save_readme():
    with open(f"{OUTPUT_PATH}/README.txt", "w", encoding="utf-8") as f:
        f.write("TODO")  # TODO add readme content (Folder structure)


def calc(copied_data_path: str):
    ids: list[dict[str, str | list[str]]] = read_all_ids_from_json()

    all_file_paths = get_all_file_paths(copied_data_path)

    for file_path in tqdm(all_file_paths):
        if ".DS_Store" in file_path:
            continue
        if check_for_pass_file(file_path):
            continue
        matching_dates, oldest_date, oldest_same_day, found_in_message = get_matching_dates(file_path, ids)

        if len(matching_dates) == 0:
            destination_path = to_not_found(file_path)
            timestamp = get_datetime_from_file_path(destination_path).timestamp()
            os.utime(destination_path, (timestamp, timestamp))
            continue

        handle_found_date(file_path, matching_dates, oldest_date, oldest_same_day, found_in_message)


def main():
    copied_data_path = safe_move(data_path, os.path.dirname(data_path), False)
    calc(copied_data_path)
    remove_copied_folder(copied_data_path)
    save_readme()


if __name__ == '__main__':
    main()
