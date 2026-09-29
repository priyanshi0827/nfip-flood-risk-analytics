"""Download the NFIP bulk parquet files from OpenFEMA.

Claims is ~2.7M rows and downloads in a few minutes. Policies is ~74.7M rows
and is a large file - budget time and disk. Use --skip-policies for a first
pass if you just want the claims side working.

FEMA's site sits behind Akamai, which bot-filters on the full request header
set, not just User-Agent. Every request here sends a coherent browser header
set. If Akamai still blocks urllib (403/406/429), we fall back to curl.exe,
which has a different TLS/HTTP fingerprint and gets through more reliably.

Resumable: an existing complete file is left alone, a partial .part file is
resumed with a Range request (urllib path) or curl's -C - (curl path).

Every completed download is verified as real parquet (PAR1 magic bytes at
both ends of the file) before being accepted - an HTML error/interstitial
page saved with a .parquet extension is the dangerous silent failure here.
"""
import argparse
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "https://www.fema.gov/about/reports-and-data/openfema/v3"
API_BASE = "https://www.fema.gov/api/open/v1"
DATA = pathlib.Path(__file__).resolve().parents[1] / "data"

FILES = {
    "claims": (f"{BASE}/NfipClaimsV3.parquet", "NfipClaimsV3.parquet"),
    "policies": (f"{BASE}/NfipPoliciesV3.parquet", "NfipPoliciesV3.parquet"),
    "multiloss": (f"{API_BASE}/NfipMultipleLossProperties.parquet",
                  "NfipMultipleLossProperties.parquet"),
}

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": "https://www.fema.gov/",
    "Connection": "keep-alive",
}

PARQUET_MAGIC = b"PAR1"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def is_valid_parquet(path: pathlib.Path) -> bool:
    size = path.stat().st_size
    if size < 8:
        return False
    with open(path, "rb") as fh:
        head = fh.read(4)
        fh.seek(-4, 2)
        tail = fh.read(4)
    return head == PARQUET_MAGIC and tail == PARQUET_MAGIC


def download_urllib(url: str, dest: pathlib.Path, part: pathlib.Path) -> None:
    start = part.stat().st_size if part.exists() else 0
    headers = dict(BROWSER_HEADERS)
    if start:
        headers["Range"] = f"bytes={start}-"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0)) + start
        mode = "ab" if start else "wb"
        done = start
        with open(part, mode) as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                pct = f"{done / total * 100:5.1f}%" if total else "  ?  "
                print(f"\r  {dest.name}: {pct} ({human(done)})", end="", flush=True)
    print()


def download_curl(url: str, dest: pathlib.Path, part: pathlib.Path) -> None:
    print(f"  urllib was blocked, retrying {dest.name} via curl.exe")
    cmd = [
        "curl.exe", "-L", "--fail", "--retry", "3", "-C", "-",
        "-A", BROWSER_HEADERS["User-Agent"],
        "-H", f"Accept: {BROWSER_HEADERS['Accept']}",
        "-H", f"Accept-Language: {BROWSER_HEADERS['Accept-Language']}",
        "-H", f"Accept-Encoding: {BROWSER_HEADERS['Accept-Encoding']}",
        "-H", f"Sec-Fetch-Dest: {BROWSER_HEADERS['Sec-Fetch-Dest']}",
        "-H", f"Sec-Fetch-Mode: {BROWSER_HEADERS['Sec-Fetch-Mode']}",
        "-H", f"Sec-Fetch-Site: {BROWSER_HEADERS['Sec-Fetch-Site']}",
        "-H", f"Referer: {BROWSER_HEADERS['Referer']}",
        "-H", f"Connection: {BROWSER_HEADERS['Connection']}",
        "-o", str(part),
        url,
    ]
    subprocess.run(cmd, check=True)


def download(url: str, dest: pathlib.Path) -> None:
    if dest.exists():
        print(f"  already have {dest.name} ({human(dest.stat().st_size)}), skipping")
        return

    part = dest.with_suffix(dest.suffix + ".part")
    if part.exists() and part.stat().st_size:
        print(f"  resuming {dest.name} at {human(part.stat().st_size)}")

    try:
        download_urllib(url, dest, part)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 406, 429):
            download_curl(url, dest, part)
        else:
            raise

    if not is_valid_parquet(part):
        part.unlink()
        raise RuntimeError(
            f"{dest.name}: downloaded file is not valid parquet (missing PAR1 "
            "magic bytes) - likely an HTML error/interstitial page, not the data"
        )

    part.rename(dest)
    print(f"  done: {dest.name} ({human(dest.stat().st_size)})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-policies", action="store_true",
                    help="skip the 74.7M-row policies file")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    wanted = ["claims", "multiloss"] + ([] if args.skip_policies else ["policies"])

    failed = []
    for key in wanted:
        url, name = FILES[key]
        print(f"{key}:")
        try:
            download(url, DATA / name)
        except Exception as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            failed.append((key, url, name))

    if failed:
        print("\nCould not download the following files automatically:", file=sys.stderr)
        for key, url, name in failed:
            print(f"  {key}: {url} -> data/{name}", file=sys.stderr)
        print(
            "\nOpen each URL above in a browser and save it into the data/ "
            "directory under the given filename, then re-run this script - "
            "it will skip files that already exist.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
