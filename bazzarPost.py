import subprocess
import json
from pathlib import Path


def extract_english_subtitles(video_path):
    """Extract English subtitles from video using ffprobe/ffmpeg."""
    video = Path(video_path)
    srt_path = video.with_suffix(video.suffix + '.en.srt')
    if srt_path.exists():
        return srt_path
    try:
        result = subprocess.run([
            'ffprobe',
            '-v', 'error',
            '-select_streams', 's',
            '-show_entries', 'stream=index:stream_tags=language',
            '-of', 'json',
            str(video)
        ], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return srt_path if srt_path.exists() else None
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError:
        return srt_path if srt_path.exists() else None

    index = None
    for stream in info.get('streams', []):
        lang = stream.get('tags', {}).get('language', '')
        if lang.lower().startswith('eng'):
            index = stream.get('index')
            break
    if index is None:
        return srt_path if srt_path.exists() else None

    try:
        subprocess.run([
            'ffmpeg',
            '-y',
            '-i', str(video),
            '-map', f'0:s:{index}',
            '-c:s', 'srt',
            str(srt_path)
        ], check=True)
    except (OSError, subprocess.CalledProcessError):
        pass
    return srt_path if srt_path.exists() else None


def has_english_subtitles(video_path):
    srt_path = extract_english_subtitles(video_path)
    return srt_path is not None and srt_path.exists()


if __name__ == '__main__':
    import sys
    for video in sys.argv[1:]:
        if has_english_subtitles(video):
            print(f'English subtitles available for {video}')
        else:
            print(f'No English subtitles found for {video}')

