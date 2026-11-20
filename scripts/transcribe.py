"""
Видеодон текст чыгаруу (faster-whisper).
Кыргыз тилин Whisper билбейт, ошондуктан казак тили (kk) менен таанытабыз.
Натыйжа: текст/<видеонун аты>.txt жана .srt — аларды кыргызчага ӨЗҮҢҮЗ оңдойсуз.

Колдонуу:
    python scripts/transcribe.py видео/менин_видеом.mp4
    python scripts/transcribe.py видео/менин_видеом.mp4 --model medium
"""
import argparse
from pathlib import Path

from faster_whisper import WhisperModel


def ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--model", default="small", help="tiny / base / small / medium / large-v3")
    args = p.parse_args()

    video = Path(args.video)
    out_dir = Path(__file__).resolve().parent.parent / "текст"
    out_dir.mkdir(exist_ok=True)

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(video), language="kk", word_timestamps=True, vad_filter=True)

    srt, txt = [], []
    for i, seg in enumerate(segments, 1):
        text = seg.text.strip()
        srt.append(f"{i}\n{ts(seg.start)} --> {ts(seg.end)}\n{text}\n")
        txt.append(text)
        print(f"[{ts(seg.start)}] {text}")

    (out_dir / f"{video.stem}.srt").write_text("\n".join(srt), encoding="utf-8")
    (out_dir / f"{video.stem}.txt").write_text("\n".join(txt), encoding="utf-8")
    print(f"\nДаяр: {out_dir / (video.stem + '.srt')}")
    print("Эми текстти кыргызчага оңдоп, мага «текст даяр» деп айтыңыз.")


if __name__ == "__main__":
    main()
