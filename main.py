import re
from datetime import datetime
import os
import json
from urllib.parse import urlparse, parse_qs
import shutil
from tqdm import tqdm

data_path = "./mydata-xxxxxx"
history_path = "./json/memories_history.json"
OUTPUT_PATH = f"./{datetime.now().strftime("%Y-%m-%d at %H-%M")} Snapchat Data ExΩport"
PHOTO_SUFFIX = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff'}
VIDEO_SUFFIX = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
DATE_FILE_NAME_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
IGNORE_FILES = {".DS_Store", ".gitkeep", ".gitignore", "Thumbs.db", "desktop.ini"}
# TODO check if date does not matches date in filename
# TODO consider json/chat_history.json
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

def to_manual_check(file_path, sub_dir, matching_dates=None) -> str:
    found_path = f"{OUTPUT_PATH}/passed_files/{sub_dir}"
    os.makedirs(found_path, exist_ok=True)
    new_path = "/".join(file_path.split('/')[2:])
    new_path = f"{found_path}/{new_path}"
    destination_path = safe_move(file_path, found_path)
    if type == "many_dates":
        if matching_dates is None or len(matching_dates) <= 1:
            raise ValueError(f"called to_manual_check but matching_dates haven't enough elements \n"
                             f"matching_dates: {matching_dates} \n"
                             f"file_path: {file_path} \n"
                             f"new_path: {new_path}")
        matching_dates = matching_dates.split(',')
        with open(new_path + ".txt", "w", encoding="utf-8") as f:
            f.write("Found more than one date. \n"
                    "The oldest date was set for this file \n \n")
            for date in matching_dates:
                f.write(date + "\n")
    return destination_path

def calc(copied_data_path: str):
    with open(history_path, "r", encoding="utf-8") as file:
        history = json.load(file)

    all_file_paths = get_all_file_paths(copied_data_path)

    for file_path in tqdm(all_file_paths):
        if ".DS_Store" in file_path:
            continue
        if "overlay" in file_path:
            to_passed(file_path, "overlays")
            continue
        if "thumbnail" in file_path:
            to_passed(file_path, "thumbnails")
            continue
        if ("." + file_path.split(".")[-1] not in PHOTO_SUFFIX) and ("." + file_path.split(".")[-1] not in VIDEO_SUFFIX):
            to_passed(file_path, "other_files")
            continue
        matching_dates: list[str] = []
        for entry in history["Saved Media"]:
            date = entry["Date"]

            link = entry["Download Link"]
            query_params = parse_qs(urlparse(link).query)
            sid, uid = query_params.get("sid", [None])[0], query_params.get("uid", [None])[0]
            mid, sig = query_params.get("mid", [None])[0], query_params.get("sig", [None])[0]

            if (sid in file_path) or (uid in file_path) or (mid in file_path) or (sig in file_path):
                matching_dates.append(date)

        if len(matching_dates) == 0:
            destination_path = to_not_found(file_path)
            match = DATE_FILE_NAME_PATTERN.match(os.path.basename(destination_path))
            if match:
                year, month, day = map(int, match.groups())
                date = datetime(year, month, day)
                timestamp = date.timestamp()
                os.utime(destination_path, (timestamp, timestamp))
        elif len(matching_dates) > 1:
            destination_path = to_manual_check(file_path, "many_dates", matching_dates)
            oldest_date = min(
                datetime.strptime(d.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
                for d in matching_dates
            )
            timestamp = oldest_date.timestamp()
            os.utime(destination_path, (timestamp, timestamp))
        else:
            destination_path = to_found(file_path)
            dt_utc = datetime.strptime(matching_dates[0].replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
            timestamp = dt_utc.timestamp()
            os.utime(destination_path, (timestamp, timestamp))

def remove_copied_folder(copied_data_path):
    remaining_files_found = False
    for root, dirs, files in os.walk(copied_data_path):
        considered_files = [f for f in files if f not in IGNORE_FILES]
        if considered_files:
            print(f"Found remaining file in {root}: {considered_files}")
            remaining_files_found = True
    if remaining_files_found:
        print(f"The copied data folder: '{copied_data_path}' contains remaining files. \n"
              f"These files wasn't considered: Please check them")  # TODO automatically check if path is empty
    else:
        shutil.rmtree(copied_data_path)

def save_readme():
    with open(f"{OUTPUT_PATH}/README.txt", "w", encoding="utf-8") as f:
        f.write("TODO") # TODO add readme content (Folder structure)


def main():
    copied_data_path = safe_move(data_path, os.path.dirname(data_path), False)
    calc(copied_data_path)
    remove_copied_folder(copied_data_path)
    save_readme()


if __name__ == '__main__':
    main()
