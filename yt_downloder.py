import subprocess
import re
import os
import json
from tqdm import tqdm
from datetime import datetime

YT_DLP_PATH = "yt-dlp"
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Youtube Downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def format_file_size(size_in_bytes):
    """Convert bytes to a human-readable format (KB, MB, GB)."""
    try:
        size_in_bytes = int(size_in_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_in_bytes < 1024.0:
                return f"{size_in_bytes:.2f} {unit}"
            size_in_bytes /= 1024.0
    except ValueError:
        return "Unknown Size"
    return "Unknown Size"


def get_video_info(video_url):
    """Retrieve video metadata using yt-dlp in one call."""
    command = [YT_DLP_PATH, "--dump-json", video_url]
    process = subprocess.run(command, capture_output=True, text=True)

    if process.returncode != 0:
        print("❌ Failed to retrieve video info.")
        return None

    try:
        info = json.loads(process.stdout)
        upload_date = (
            datetime.strptime(info["upload_date"], "%Y%m%d").strftime("%Y-%m-%d")
            if "upload_date" in info else "Unknown Date"
        )
        return {
            "title": info.get("title", "Unknown Title"),
            "duration": info.get("duration_string", "Unknown Duration"),
            "filesize": format_file_size(info.get("filesize_approx", 0)),
            "upload_date": upload_date,
            "resolution": info.get("resolution", "Unknown"),
        }
    except json.JSONDecodeError:
        print("❌ Error parsing video metadata.")
        return None


def get_video_formats(video_url):
    """Fetch available formats for a YouTube video."""
    command = [YT_DLP_PATH, "-F", video_url]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        print("❌ Error:", result.stderr)
        return None

    print("\n📜 Available Formats:\n")
    print(f"{'ID':<8} {'Ext':<6} {'Resolution':<12} {'FPS':<6} {'Size':<10} {'Type'}")
    print("=" * 60)

    format_lines = result.stdout.strip().split("\n")
    for line in format_lines[3:]:
        match = re.match(r"(\d+)\s+(\S+)\s+([\w\d]+(?:x[\w\d]+)?)?\s*(\d+fps)?\s*(\~?\d+\.\d+[KMG]iB)?\s*(.+)", line)
        if match:
            format_id, ext, resolution, fps, size, desc = match.groups()
            print(f"{format_id:<8} {ext:<6} {resolution or 'N/A':<12} {fps or 'N/A':<6} {size or 'N/A':<10} {desc}")

    return result.stdout


def download_with_progress(command, output_path, total_size):
    """Download with real-time progress update."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    progress_bar = tqdm(total=total_size, unit="B", unit_scale=True, ncols=80, desc="Downloading", dynamic_ncols=True)

    downloaded_size = 0
    for line in process.stdout:
        match = re.search(r"(\d{1,3}(?:\.\d+)?)%", line)
        if match:
            percent = float(match.group(1))
            new_size = int((percent / 100) * total_size)
            progress_bar.update(new_size - downloaded_size)
            downloaded_size = new_size

    process.wait()
    progress_bar.close()
    return process.returncode


def sanitize_filename(title):
    """Ensure safe filenames by replacing special characters."""
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in title)


def download_video(video_url, format_id):
    """Download video and rename it with resolution."""
    video_info = get_video_info(video_url)
    safe_title = sanitize_filename(video_info["title"])
    video_output = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp4")

    total_size = int(video_info["filesize"].split()[0]) if video_info["filesize"] != "Unknown Size" else 0

    command = [
        YT_DLP_PATH, "-f", format_id, "-o", video_output, video_url,
        "--embed-subs", "--sub-lang", "en"
    ]

    result = download_with_progress(command, video_output, total_size)
    if result == 0:
        new_filename = f"{safe_title}_{video_info['resolution']}.mp4"
        new_path = os.path.join(DOWNLOAD_DIR, new_filename)
        os.rename(video_output, new_path)
        print(f"\n✅ Video downloaded successfully as:\n{new_filename}")
    else:
        print("\n❌ Video download failed.")


def download_audio(video_url, audio_format_id):
    """Download audio-only file."""
    video_info = get_video_info(video_url)
    safe_title = sanitize_filename(video_info["title"])
    audio_output = os.path.join(DOWNLOAD_DIR, f"{safe_title}.m4a")

    total_size = int(video_info["filesize"].split()[0]) if video_info["filesize"] != "Unknown Size" else 0

    command = [YT_DLP_PATH, "-f", audio_format_id, "-o", audio_output, video_url]
    result = download_with_progress(command, audio_output, total_size)
    if result == 0:
        print(f"\n✅ Audio downloaded successfully as:\n{os.path.basename(audio_output)}")
    else:
        print("\n❌ Audio download failed.")


def download_and_merge(video_url, video_format_id, audio_format_id):
    """Download & merge video + audio with embedded subtitles."""
    video_info = get_video_info(video_url)

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in video_info["title"])

    # Get video resolution from formats
    resolution = "UnknownRes"
    format_details = get_video_formats(video_url).split("\n")
    for line in format_details:
        if line.startswith(video_format_id):
            match = re.search(r"(\d{3,4}x\d{3,4})", line)
            if match:
                resolution = match.group(1)

    download_title = f"{safe_title}_({resolution})"
    video_output = os.path.join(DOWNLOAD_DIR, f"{download_title}.mp4")

    # Convert file size properly
    try:
        total_size = float(video_info["filesize"].split()[0]) * 1024 * 1024 if "MB" in video_info["filesize"] else \
            float(video_info["filesize"].split()[0]) * 1024 * 1024 * 1024 if "GB" in video_info["filesize"] else 0
    except ValueError:
        total_size = 0

    command = [
        YT_DLP_PATH, "-f", f"{video_format_id}+{audio_format_id}", "-o", video_output, video_url,
        "--embed-subs", "--sub-lang", "en"
    ]

    print(f"\n🚀 Downloading: {download_title}.mp4")

    result = download_with_progress(command, video_output, int(total_size))  # Convert to int for tqdm
    if result == 0:
        print(f"\n✅ Merged video downloaded successfully as:\n{os.path.basename(video_output)}")
    else:
        print("\n❌ Merge failed.")


def main():
    video_url = input("🔗 Enter YouTube video URL: ")
    video_info = get_video_info(video_url)

    print("\n🎥 Video Details:")
    for key, value in video_info.items():
        print(f"   {key.capitalize()}: {value}")

    formats = get_video_formats(video_url)
    if not formats:
        print("❌ Could not fetch formats. Exiting.")
        return

    choice = input("\n📌 Choose download type (1=Video, 2=Audio, 3=Merge): ").strip()
    if choice == "1":
        download_video(video_url, input("🎥 Enter VIDEO format ID: ").strip())
    elif choice == "2":
        download_audio(video_url, input("🎵 Enter AUDIO format ID: ").strip())
    elif choice == "3":
        download_and_merge(video_url, input("🎥 Video ID: "), input("🎵 Audio ID: "))
    else:
        print("❌ Invalid choice! Please enter 1, 2, or 3.")


main()
