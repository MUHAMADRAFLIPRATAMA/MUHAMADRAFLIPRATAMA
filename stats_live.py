"""
Isi angka "GitHub Stats" di dark_mode.svg / light_mode.svg dengan data asli dari GitHub.

Tidak butuh Personal Access Token: cukup GITHUB_TOKEN bawaan GitHub Actions
(opsional, hanya menaikkan rate limit dan mengaktifkan search commits).
Data diambil dari REST API publik + API kontribusi publik, lalu ditulis ke
elemen SVG berdasarkan id (repo_data, contrib_data, star_data, commit_data,
follower_data, loc_data, loc_add, loc_del).

Jalankan: python stats_live.py
"""

import io
import json
import os
import re
import time
import tarfile
import urllib.request
import urllib.error

USER_NAME = os.environ.get("USER_NAME") or "MUHAMADRAFLIPRATAMA"
UPTIME_SINCE = (2020, 7, 1)  # awal belajar komputer (SMK Malaka, TKJ)
TOKEN = os.environ.get("ACCESS_TOKEN") or ""
SVG_FILES = ["dark_mode.svg", "light_mode.svg"]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": USER_NAME + "-readme-stats",
}
if TOKEN:
    HEADERS["Authorization"] = "Bearer " + TOKEN


def api(url, retries=2, sleep_s=2):
    """GET JSON dari GitHub REST API, return (data, headers)."""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8")), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, {}
            if e.code in (403, 429) and attempt < retries:
                time.sleep(sleep_s * (attempt + 1))
                continue
            return None, {}
        except Exception:
            if attempt < retries:
                time.sleep(sleep_s)
                continue
            return None, {}
    return None, {}


def get_json_any(url, retries=2, sleep_s=2):
    """Untuk endpoint non-GitHub (api kontribusi publik)."""
    req = urllib.request.Request(url, headers={"User-Agent": "readme-stats"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt < retries:
                time.sleep(sleep_s)
                continue
            return None
    return None


def fetch_repos():
    repos, page = [], 1
    while page <= 10:
        data, _ = api(
            f"https://api.github.com/users/{USER_NAME}/repos"
            f"?per_page=100&page={page}&sort=pushed&type=owner"
        )
        if not isinstance(data, list) or not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def fetch_user():
    data, _ = api(f"https://api.github.com/users/{USER_NAME}")
    return data or {}


def fetch_contributions():
    data = get_json_any(
        f"https://github-contributions-api.jogruber.de/v4/{USER_NAME}?y=last"
    )
    if isinstance(data, dict):
        total = data.get("total") or {}
        if isinstance(total, dict) and total.get("lastYear") is not None:
            return int(total["lastYear"])
    return None


def fetch_commits(repos):
    """Total commit oleh user. Search API kalau ada token, kalau tidak jumlahkan per repo."""
    if TOKEN:
        data, _ = api(
            "https://api.github.com/search/commits"
            f"?q=author:{USER_NAME}&per_page=1",
        )
        if isinstance(data, dict) and data.get("total_count") is not None:
            return int(data["total_count"])
    if len(repos) > 40:
        return None  # tanpa token hasilnya tidak lengkap, lebih baik tidak diisi
    total = ok = 0
    for r in repos[:40]:
        data, headers = api(
            f"https://api.github.com/repos/{USER_NAME}/{r['name']}/commits"
            f"?author={USER_NAME}&per_page=1"
        )
        if isinstance(data, list) and data:
            ok += 1
            link = headers.get("Link", "")
            m = re.search(r'[?&]page=(\d+)>; rel="last"', link)
            total += int(m.group(1)) if m else len(data)
    return total if ok else None


def repo_code_frequency(repo):
    """(additions, deletions) dari endpoint code_frequency; 202 = masih dihitung."""
    url = f"https://api.github.com/repos/{USER_NAME}/{repo}/stats/code_frequency"
    for attempt in range(4):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "ignore")
                if r.status == 202 or not body.strip():
                    time.sleep(2 + attempt * 2)
                    continue
                data = json.loads(body)
                if not isinstance(data, list):
                    return 0, 0
                add = sum(int(row[1]) for row in data if len(row) > 1 and row[1] > 0)
                dele = sum(-int(row[2]) for row in data if len(row) > 2 and row[2] < 0)
                return add, dele
        except urllib.error.HTTPError as e:
            if e.code == 202:
                time.sleep(2 + attempt * 2)
                continue
            return 0, 0
        except Exception:
            return 0, 0
    return 0, 0


CODE_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".java", ".kt", ".kts",
    ".c", ".cpp", ".cc", ".h", ".hpp", ".cs", ".go", ".rs", ".php", ".rb",
    ".css", ".scss", ".html", ".htm", ".sql", ".json", ".yml", ".yaml",
    ".sh", ".xml", ".dart", ".swift", ".vue", ".svelte", ".md",
}


def tarball_lines(repo, max_bytes=20_000_000):
    """Hitung baris kode dari tarball repo (tanpa API, tanpa rate limit)."""
    url = f"https://codeload.github.com/{USER_NAME}/{repo}/tar.gz/HEAD"
    req = urllib.request.Request(url, headers={"User-Agent": "readme-stats"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            blob = r.read(max_bytes + 1)
    except Exception:
        return 0
    if len(blob) > max_bytes:
        return 0
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for m in tf:
                if not m.isfile() or m.size > 400_000:
                    continue
                if os.path.splitext(m.name)[1].lower() not in CODE_EXT:
                    continue
                f = tf.extractfile(m)
                if not f:
                    continue
                txt = f.read().decode("utf-8", "ignore")
                total += txt.count("\n") + (0 if txt.endswith("\n") else 1)
    except Exception:
        return 0
    return total


def gather(limit_loc=None):
    repos = fetch_repos()
    user = fetch_user()
    stats = {
        "repos": len(repos) if repos else None,
        "stars": sum(int(r.get("stargazers_count") or 0) for r in repos) if repos else None,
        "followers": int(user["followers"]) if user.get("followers") is not None else None,
        "contrib": fetch_contributions(),
        "commits": fetch_commits(repos) if repos else None,
        "uptime": uptime_text(),
    }
    targets = repos if limit_loc is None else repos[:limit_loc]
    skip_cf = os.environ.get("SKIP_CODE_FREQUENCY") == "1"

    additions = deletions = ok = tried = 0
    if targets and not skip_cf:
        for r in targets:
            if r.get("size", 0) > 60000:
                continue
            tried += 1
            a, d = repo_code_frequency(r["name"])
            if a or d:
                ok += 1
                additions += a
                deletions += d

    if tried and ok >= max(1, int(tried * 0.8)):
        stats["loc_add"], stats["loc_del"] = additions, deletions
        stats["loc"] = additions - deletions
    elif targets:
        lines = 0
        for r in targets:
            lines += tarball_lines(r["name"])
        if lines:
            stats["loc_add"], stats["loc_del"], stats["loc"] = lines, 0, lines
        else:
            stats["loc_add"] = stats["loc_del"] = stats["loc"] = None
    else:
        stats["loc_add"] = stats["loc_del"] = stats["loc"] = None
    return stats


def uptime_text():
    """'6 years, 4 months, 16 days' sejak UPTIME_SINCE."""
    from datetime import date

    today = date.today()
    y0, m0, d0 = UPTIME_SINCE
    years = today.year - y0
    months = today.month - m0
    days = today.day - d0
    if days < 0:
        months -= 1
        prev_month = today.month - 1 or 12
        prev_year = today.year if today.month > 1 else today.year - 1
        import calendar

        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    if years < 0:
        return None
    return f"{years} year{'s' if years != 1 else ''}, {months} month{'s' if months != 1 else ''}, {days} day{'s' if days != 1 else ''}"


def fmt(n):
    return f"{n:,}" if isinstance(n, int) else str(n)


def dots_for(value, base):
    """Kurangi titik pengisi sepanjang selisih panjang angka, minimal 1 titik."""
    extra = len(fmt(value)) - len(str(base))
    return max(1, 4 - extra)


def patch_svg(path, stats):
    if not os.path.exists(path):
        print(f"! {path} tidak ada, dilewati")
        return False
    src = open(path, encoding="utf-8").read()
    out = src

    def set_text(svg, el_id, value):
        pattern = re.compile(r'(id="' + el_id + r'"[^>]*>)([^<]*)(<)', re.S)
        return pattern.sub(lambda m: m.group(1) + value + m.group(3), svg, count=1)

    def pad(n, width):
        n = fmt(n) if isinstance(n, int) else str(n)
        return " " * max(1, width - len(n)) + " "

    if stats.get("repos") is not None:
        out = set_text(out, "repo_data", fmt(stats["repos"]))
    if stats.get("contrib") is not None:
        out = set_text(out, "contrib_data", fmt(stats["contrib"]))
    if stats.get("stars") is not None:
        out = set_text(out, "star_data", fmt(stats["stars"]))
    if stats.get("commits") is not None:
        out = set_text(out, "commit_data", fmt(stats["commits"]))
    if stats.get("followers") is not None:
        out = set_text(out, "follower_data", fmt(stats["followers"]))
    if stats.get("uptime"):
        out = set_text(out, "age_data", stats["uptime"])
    if stats.get("loc") is not None:
        out = set_text(out, "loc_data", fmt(stats["loc"]))
        out = set_text(out, "loc_add", fmt(stats["loc_add"]))
        out = set_text(out, "loc_del", fmt(stats["loc_del"]))

    if out != src:
        open(path, "w", encoding="utf-8", newline="").write(out)
        print(f"OK {path} diperbarui")
        return True
    print(f"= {path} tidak berubah")
    return False


def main():
    limit = os.environ.get("LOC_REPO_LIMIT")
    stats = gather(limit_loc=int(limit) if limit else None)
    print("stats:", {k: stats.get(k) for k in ("repos", "stars", "followers", "contrib", "commits", "loc")})
    changed = False
    for f in SVG_FILES:
        changed = patch_svg(f, stats) or changed
    if not changed:
        print("tidak ada perubahan")


if __name__ == "__main__":
    main()
