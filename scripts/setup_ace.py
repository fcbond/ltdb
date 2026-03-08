"""Download and install the ACE parser binary into etc/."""
import os
import sys
import platform
import tarfile
import urllib.request
from pathlib import Path

ETC_DIR = Path(__file__).parent.parent / "etc"

ACE_LINUX = {
    "version": "ace-0.9.31",
    "filename": "ace-0.9.31-x86-64.tar.gz",
    "url": "https://sweaglesw.org/linguistics/ace/download/ace-0.9.31-x86-64.tar.gz",
}

ACE_MACOS = {
    "version": "ace-0.9.34",
    "filename": "ace-0.9.34-m1-test",
    "url": "https://sweaglesw.org/linguistics/ace-0.9.34-m1-test",
}


def report_progress(block_count, block_size, total_size):
    downloaded = block_count * block_size
    if total_size > 0:
        pct = min(downloaded / total_size * 100, 100)
        print(f"\r  {pct:.1f}%  ({downloaded // 1024} / {total_size // 1024} KB)",
              end='', flush=True)


def download(url, dest):
    """Download url to dest, skipping if already present."""
    if dest.exists():
        print(f"  Already downloaded: {dest.name}")
        return
    print(f"  Downloading {url}")
    urllib.request.urlretrieve(url, dest, reporthook=report_progress)
    print()


def install_linux():
    info = ACE_LINUX
    ace_dir = ETC_DIR / info["version"]
    ace_bin = ace_dir / "ace"

    if ace_bin.exists():
        print(f"ACE already installed at {ace_bin}")
        return ace_bin

    ETC_DIR.mkdir(parents=True, exist_ok=True)
    tarball = ETC_DIR / info["filename"]
    download(info["url"], tarball)

    print(f"  Extracting {tarball.name} ...")
    with tarfile.open(tarball) as tf:
        tf.extractall(ETC_DIR)

    if not ace_bin.exists():
        raise FileNotFoundError(f"Expected ACE binary not found after extraction: {ace_bin}")

    print(f"ACE installed at {ace_bin}")
    return ace_bin


def install_macos():
    info = ACE_MACOS
    ace_dir = ETC_DIR / info["version"]
    ace_bin = ace_dir / "ace"

    if ace_bin.exists():
        print(f"ACE already installed at {ace_bin}")
        return ace_bin

    ace_dir.mkdir(parents=True, exist_ok=True)
    raw = ace_dir / info["filename"]
    download(info["url"], raw)

    raw.chmod(0o755)
    if not ace_bin.exists():
        ace_bin.symlink_to(raw.name)

    print(f"ACE installed at {ace_bin}")
    return ace_bin


def main():
    system = platform.system()
    print(f"Platform: {system}")

    if system == "Linux":
        ace_bin = install_linux()
    elif system == "Darwin":
        ace_bin = install_macos()
    else:
        sys.exit(f"Unsupported OS: {system}. Please install ACE manually.")

    print(f"\nDone. You can now use: --ace-bin {ace_bin}")


if __name__ == "__main__":
    main()
