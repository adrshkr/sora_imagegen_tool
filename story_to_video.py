#!/usr/bin/env python3
"""
story_to_video.py
Generate a sequence of images from a story and compile them into a video using OpenAI’s GPT-Image-1 model.
Adds: progress bars (tqdm), parallel generation (threads), interactive API key prompt if missing,
preflight checks (Black and Ruff), fail-fast error guards, and optional one-shot smoke test.
"""

import argparse
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import subprocess

from openai import OpenAI
from moviepy.video.io.ImageSequenceClip import ImageSequenceClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from tqdm import tqdm  # progress bars

# OpenAI client (initialized after we have a key)
client = None


# --------- Error classifiers ---------
def _safe_str(exc: Exception) -> str:
    try:
        return str(exc).lower()
    except Exception:
        return ""


def _is_hard_limit_error(exc: Exception) -> bool:
    s = _safe_str(exc)
    return ("billing hard limit" in s) or ("billing_hard_limit_reached" in s)


def _is_auth_error(exc: Exception) -> bool:
    s = _safe_str(exc)
    return ("invalid api key" in s) or ("unauthorized" in s) or ("401" in s)


def _is_forbidden_needs_verification(exc: Exception) -> bool:
    s = _safe_str(exc)
    # e.g., “Your organization must be verified to use the model `gpt-image-1`.”
    return ("403" in s and "must be verified" in s) or ("access denied" in s)


def _is_bad_request(exc: Exception) -> bool:
    # e.g., bad size param, empty prompt, etc. (exclude rate limit wording)
    s = _safe_str(exc)
    return (("bad request" in s) or ("400" in s)) and ("rate limit" not in s)


# -------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate images from a story and compile them into a video.")
    parser.add_argument("--story", type=str, required=True, help="Narrative brief.")
    parser.add_argument("--style", type=str, required=True, help="Art style applied to prompts.")
    parser.add_argument("--max-images", type=int, default=12, help="Maximum number of images.")
    parser.add_argument("--aspect", type=str, default="16:9", help="Aspect ratio (video metadata only).")
    parser.add_argument("--size", type=str, default="1024x1024", help="Image resolution for generation.")
    parser.add_argument("--fps", type=int, default=3, help="Frames per second for output video.")
    parser.add_argument("--output-file", type=str, default="output.mp4", help="Output video file name.")
    parser.add_argument(
        "--prompts-file",
        type=str,
        default="prompts.json",
        help="Path to JSON file containing prompts.",
    )
    parser.add_argument(
        "--frames-dir",
        type=str,
        default="frames",
        help="Directory to save generated images.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip image generation if frame already exists.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress console INFO/DEBUG logs.")
    parser.add_argument("--kenburns", action="store_true", help="Placeholder for Ken Burns effect.")
    parser.add_argument("--audio", type=str, default=None, help="Optional audio file for video.")
    parser.add_argument(
        "--threads",
        type=int,
        default=multiprocessing.cpu_count(),
        help="Number of parallel image generations. Defaults to CPU core count.",
    )
    # NEW: preflight + smoke test flags
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip running preflight.py (Black and Ruff) before generation.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Do a 1-shot 256x256 test render before queueing all scenes.",
    )
    return parser.parse_args()


def setup_logging(quiet: bool) -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.DEBUG)
    console_level = logging.INFO if quiet else logging.DEBUG
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)
    file_handler = logging.FileHandler("../story-to-video/run.log", mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(file_handler)


def load_prompts(prompts_path: str) -> list:
    with open(prompts_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)
    if not isinstance(scenes, list):
        raise ValueError("prompts.json must contain a list of scenes")
    return scenes


def ensure_api_key() -> None:
    """Check for API key in env, load from local.env if available, or prompt interactively."""
    global client

    # Try loading from local.env file if it exists
    env_file_path = Path(__file__).parent / "local.env"
    if env_file_path.exists():
        with open(env_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value

    # Now check OPENAI_API_KEY
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        api_key = input("Enter your OpenAI API Key: ").strip()
        if not api_key:
            raise ValueError("No API key provided.")
        os.environ["OPENAI_API_KEY"] = api_key

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ---------- Preflight runner ----------
def run_preflight(script_dir: Path) -> None:
    """Run preflight.py (Black and Ruff). Abort if it fails."""
    preflight = script_dir / "preflight.py"
    if not preflight.exists():
        logging.warning("preflight.py not found. Skipping pre-flight checks.")
        return
    # preflight.py currently runs only Black for formatting and Ruff for linting.
    # Tests and type checks live elsewhere.
    logging.info("Running pre-flight checks (Black and Ruff)…")
    cmd = f'"{sys.executable}" "{preflight}"'
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        raise SystemExit("Pre-flight checks failed. Fix issues and re-run.")


# -------------------------------------


# ---------- Optional 1-shot smoke test ----------
def smoke_test() -> None:
    """Try a tiny generation to catch auth/billing/access errors before full run."""
    logging.info("Running smoke test (one 256x256 render)…")
    prompt = "a single red cube on a clean white background, studio lighting"
    try:
        r = client.images.generate(model="gpt-image-1", prompt=prompt, size="256x256", n=1)
        # Touch the base64 only to ensure response structure is valid:
        _ = base64.b64decode(r.data[0].b64_json)
        logging.info("Smoke test OK.")
    except Exception as exc:
        if _is_hard_limit_error(exc):
            logging.error("❌ Billing hard limit reached during smoke test. Aborting.")
            raise SystemExit(1)
        if _is_auth_error(exc):
            logging.error("❌ Authentication error during smoke test. Check OPENAI_API_KEY. Aborting.")
            raise SystemExit(1)
        if _is_forbidden_needs_verification(exc):
            logging.error(
                "❌ Access denied for gpt-image-1 during smoke test. Verify org/billing/model access. Aborting."
            )
            raise SystemExit(1)
        if _is_bad_request(exc):
            logging.error(f"❌ Bad request during smoke test: {exc}")
            raise SystemExit(1)
        logging.error(f"❌ Unexpected error during smoke test: {exc}")
        raise SystemExit(1)


# -----------------------------------------------


def generate_image(prompt: str, size: str, index: int, frames_dir: Path) -> Path:
    """Send a prompt to GPT-Image-1 API and save result."""
    backoff = 1.0
    while True:
        try:
            logging.debug(f"Sending request for frame {index} with size {size}")
            response = client.images.generate(model="gpt-image-1", prompt=prompt, size=size, n=1)
            break  # success
        except Exception as exc:
            # Hard stop cases — don't retry
            if _is_hard_limit_error(exc):
                logging.error(
                    "❌ Billing hard limit reached. "
                    "Increase your monthly limit, wait for cycle reset, or use another key. Aborting."
                )
                raise SystemExit(1)
            if _is_auth_error(exc):
                logging.error("❌ Authentication error calling OpenAI. Check OPENAI_API_KEY. Aborting.")
                raise SystemExit(1)
            if _is_forbidden_needs_verification(exc):
                logging.error(
                    "❌ Access denied for gpt-image-1.\n"
                    "- Verify your organization and enable billing for this project.\n"
                    "- Ensure the API key belongs to a project with model access.\n"
                    "- Optionally set OPENAI_ORG_ID / OPENAI_PROJECT.\n"
                    "Aborting."
                )
                raise SystemExit(1)
            if _is_bad_request(exc):
                logging.error(
                    f"❌ Bad request for frame {index}: {exc}\n"
                    "Check your 'size' (e.g., 1024x1024) and prompt contents. Aborting."
                )
                raise

            # Otherwise: assume transient (429/5xx/network) → retry with backoff
            logging.warning(f"Error while requesting image for frame {index}: {exc}. Retrying in {backoff:.1f}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    b64_data = response.data[0].b64_json
    img_bytes = base64.b64decode(b64_data)
    frame_path = frames_dir / f"frame_{index:03d}.png"
    with open(frame_path, "wb") as f:
        f.write(img_bytes)
    logging.info(f"Frame {index} saved to {frame_path}")
    return frame_path


def make_video(
    frame_paths: list,
    output_file: str,
    fps: int,
    kenburns: bool,
    audio_path: str | None,
) -> None:
    if not frame_paths:
        raise ValueError("No frame paths provided to make video")
    clip = ImageSequenceClip([str(p) for p in frame_paths], fps=fps)
    if audio_path:
        try:
            audio_clip = AudioFileClip(audio_path)
            clip = clip.set_audio(audio_clip)
        except Exception as exc:
            logging.warning(f"Failed to load audio {audio_path}: {exc}")
    clip.write_videofile(output_file, fps=fps)
    logging.info(f"Video written to {output_file}")


def main() -> None:
    args = parse_args()
    setup_logging(args.quiet)
    logging.debug(f"Parsed arguments: {args}")

    script_dir = Path(__file__).resolve().parent
    if not args.no_preflight:
        run_preflight(script_dir)

    ensure_api_key()

    if args.smoke_test:
        smoke_test()

    frames_dir = Path(args.frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    scenes = load_prompts(args.prompts_file)
    # Guard against missing index before comparing to max_images
    scenes = [
        s for s in scenes
        if s.get("index") is not None and s["index"] <= args.max_images
    ][: args.max_images]

    frame_paths: list[Path] = []

    # Submit image generation jobs with a progress bar
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_to_idx = {}
        for scene in tqdm(scenes, desc="Queueing scenes", unit="scene"):
            idx = scene.get("index")
            if idx is None:
                raise ValueError("Each scene must contain an 'index' field")
            title = scene.get("title", f"Scene {idx}")
            role = scene.get("narrative_role", "")
            prompt = scene.get("prompt_text")
            if not prompt:
                raise ValueError(f"Scene {idx} is missing a 'prompt_text'")
            logging.info(f"Queueing image {idx}: {title} ({role})")
            logging.debug(f"Prompt for scene {idx}: {prompt}")
            frame_file = frames_dir / f"frame_{idx:03d}.png"
            if args.skip_existing and frame_file.exists():
                logging.info(f"Skipping existing frame for scene {idx} at {frame_file}")
                frame_paths.append(frame_file)
                continue
            future = executor.submit(generate_image, prompt, args.size, idx, frames_dir)
            future_to_idx[future] = idx

        # Completion progress bar
        with tqdm(total=len(future_to_idx), desc="Generating images", unit="img") as pbar:
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    frame_path = future.result()
                    frame_paths.append(frame_path)
                except Exception as exc:
                    logging.error(f"Image generation failed for scene {idx}: {exc}")
                    raise
                finally:
                    pbar.update(1)

    # Sort frame paths to ensure correct order
    frame_paths_sorted = sorted(frame_paths, key=lambda p: p.name)

    print("\nAssembling video…")
    make_video(frame_paths_sorted, args.output_file, args.fps, args.kenburns, args.audio)


if __name__ == "__main__":
    main()
