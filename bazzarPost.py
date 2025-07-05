import sys
from pathlib import Path
from ai_sync_subtitles import smart_sync_subs


def main():
    video_path = Path(sys.argv[1])
    base = video_path.with_suffix("")

    ar_path = base.with_suffix(".ar.srt")
    en_path = base.with_suffix(".en.srt")
    output_path = base.with_name(base.stem + ".ar.synced.srt")

    if not ar_path.exists() or not en_path.exists():
        print("\u274c Arabic or English subtitle missing.")
        return

    smart_sync_subs(en_path, ar_path, output_path)


if __name__ == "__main__":
    main()
