# ScriptsPY

This repository contains Python utilities for handling video subtitles.

## BazzarPost.py

`BazzarPost.py` processes a video and its subtitle files. If `<video>.en.srt` is not present, the script attempts to extract the embedded English subtitles from the video using `ffmpeg`.

### Requirements

- Python 3
- `ffmpeg` must be installed and available in your `PATH`.

### Usage

```bash
python BazzarPost.py path/to/video.mkv
```

The script will look for `path/to/video.en.srt`. If it doesn't exist, it will use `ffmpeg` to extract English subtitles from `path/to/video.mkv`.
