"""Record reproducible dashboard screenshots and actual replay output as a narrated MP4.

Optional Windows authoring dependencies: Playwright with Edge, PowerShell
System.Speech, and ffmpeg. Start the Streamlit dashboard before recording.
"""

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NARRATION = [
    "This is the archived Gemini experiment. Thirty-one Python bugs, four repair systems, and three runs give three hundred seventy-two attempts. Each result links to a saved agent trace.",
    "Select maximum sublist sum, the multi-agent system, and run zero. The candidate passed all three visible examples. One of the three held-out examples failed.",
    "Open the final reviewer message. It approves the change and specifically endorses the handling of negative numbers. The specification allows the empty slice, whose sum is zero.",
    "Now execute the saved candidate again. The negative list returns minus four. The expected answer is zero. Independent execution reproduces the error without making a new model call.",
]


def main():
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:18185")
    ap.add_argument("--out", type=Path, default=ROOT / "docs/phase3/demo.mp4")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as dirname:
        work = Path(dirname)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            pg = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            pg.goto(args.url)
            boxes = pg.get_by_role("combobox")
            boxes.first.click()
            pg.get_by_role("option", name=re.compile("quixbugs_gemini")).click()
            pg.get_by_text("31 bugs, 372 attempts").wait_for()
            pg.get_by_role("heading", name="Outcomes per system").wait_for()
            pg.wait_for_timeout(1200)
            pg.screenshot(path=work / "0.png")

            def choose(index, option):
                boxes.nth(index).click()
                boxes.nth(index).fill(option)
                pg.get_by_role("option", name=option, exact=False).first.click()

            choose(1, "quixbugs/max_sublist_sum")
            choose(2, "S2 multi-agent")
            pg.get_by_text("held-out 2/3", exact=False).wait_for()
            pg.get_by_role("heading", name="Inspect one attempt").evaluate(
                "e => e.scrollIntoView({block:'start'})"
            )
            pg.wait_for_timeout(400)
            pg.screenshot(path=work / "1.png")
            review = pg.locator("details").filter(has_text=re.compile("reviewer", re.I)).last
            review.locator("summary").click()
            review.evaluate("e => e.scrollIntoView({block:'center'})")
            pg.wait_for_timeout(400)
            pg.screenshot(path=work / "2.png")
            output = subprocess.check_output(
                [sys.executable, str(ROOT / "scripts/demo_phase3.py")], text=True
            )
            counts = output[output.index("Re-executed visible tests:") :]
            candidate = output.split("Final candidate\n", 1)[1].split("Final reviewer response", 1)[0].strip()
            pg.set_content(
                "<style>body{margin:64px;background:#102d36;color:white;font:25px Segoe UI,sans-serif}"
                "h1{font:600 44px Segoe UI;margin:0 0 10px}p{color:#9fdcd3}pre{font:24px Consolas,monospace;line-height:1.35}"
                ".result{color:#b5eee3;font-weight:bold}</style><h1>Replay the archived patch</h1>"
                "<p>python scripts/demo_phase3.py</p><pre>" + html.escape(candidate) + "</pre><hr>"
                "<pre class='result'>" + html.escape(counts) + "</pre>"
            )
            pg.screenshot(path=work / "3.png")
            browser.close()
        (work / "lines.json").write_text(json.dumps(NARRATION), encoding="utf-8")
        speech = """
Add-Type -AssemblyName System.Speech
$speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$speaker.Rate = 0
$lines = Get-Content -Raw lines.json | ConvertFrom-Json
for ($i=0; $i -lt $lines.Count; $i++) {
    $speaker.SetOutputToWaveFile((Join-Path (Get-Location) "$i.wav"))
    $speaker.Speak($lines[$i])
    $speaker.SetOutputToNull()
}
$speaker.Dispose()
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", speech], cwd=work, check=True, capture_output=True
        )
        for i in range(len(NARRATION)):
            with wave.open(str(work / f"{i}.wav"), "rb") as sound:
                length = sound.getnframes() / sound.getframerate() + 0.8
            subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-y",
                    "-loop",
                    "1",
                    "-framerate",
                    "12",
                    "-i",
                    f"{i}.png",
                    "-i",
                    f"{i}.wav",
                    "-t",
                    f"{length:.2f}",
                    "-af",
                    "apad",
                    "-c:v",
                    "libx264",
                    "-tune",
                    "stillimage",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    f"{i}.mp4",
                ],
                cwd=work,
                check=True,
            )
        (work / "playlist.txt").write_text("".join(f"file '{i}.mp4'\n" for i in range(len(NARRATION))))
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "playlist.txt",
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(args.out.resolve()),
            ],
            cwd=work,
            check=True,
        )


if __name__ == "__main__":
    main()
