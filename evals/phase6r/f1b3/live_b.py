"""Run the approved frozen Investigation B requests with the existing audit ledger."""

import argparse
import json
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values
from investigation_a import HERE, TIMEOUT_SECONDS, digest
from live_a import REPO, ApprovedLedger, send


def trial_slots(manifest):
    for repeat in (1, 2):
        for page in manifest["pages"]:
            name = Path(page["pdf"]).stem
            order = manifest["orders"][name.split("-")[0].capitalize()][repeat - 1]
            for arm in order:
                yield f"{name}/{repeat}/{arm}", page["requests"][arm]["body_sha256"]


def run(bundle, work):
    manifest_path = HERE / "b-preflight.json"
    if (bundle / "manifest.json").read_bytes() != manifest_path.read_bytes():
        raise ValueError("Frozen manifest differs from approved manifest")
    manifest = json.loads(manifest_path.read_bytes())
    trials = []
    for slot, sha in trial_slots(manifest):
        name, _, arm = slot.split("/")
        body = (bundle / f"{name}-{arm}.json").read_bytes()
        if digest(body) != sha:
            raise ValueError("Frozen request digest differs")
        trials.append((slot, arm, body, sha))
    if len(trials) != 12 or len({trial[0] for trial in trials}) != 12:
        raise ValueError("Expected twelve unique approved slots")
    work.mkdir(mode=0o700, exist_ok=True)
    if work.is_symlink() or work.resolve().is_relative_to(REPO) or work.stat().st_mode & 0o077:
        raise ValueError("Private audit directory required")
    ledger = ApprovedLedger(work, {"pages": [], "arm_orders": []})
    ledger.allowed = {slot: sha for slot, _, _, sha in trials}
    key = os.getenv("OPENAI_API_KEY") or dotenv_values(REPO / ".env").get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OpenAI API credential unavailable")
    with httpx.Client(
        trust_env=False,
        follow_redirects=False,
        timeout=TIMEOUT_SECONDS,
        transport=httpx.HTTPTransport(retries=0, trust_env=False),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    ) as client:
        for slot, arm, body, sha in trials:
            result = send(client, ledger, slot, arm, body, sha)
            if result.get("http_status") in {400, 401, 403, 404, 429}:
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--approval", required=True, choices=["F1B3-B-12-USD6.60"])
    args = parser.parse_args()
    run(args.bundle, args.work)
