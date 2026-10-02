"""Render aggregate cards without writing repository names, code, or credentials."""
import collections
import datetime as dt
import html
import json
import os
from pathlib import Path
import urllib.request

LOGIN = "Kaleab-y"


def graphql(query, variables):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": "Bearer " + os.environ["STATS_TOKEN"],
                 "Content-Type": "application/json", "User-Agent": "aggregate-profile-stats"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    if result.get("errors"):
        # API diagnostics can contain private repository identifiers.
        raise RuntimeError("GitHub query failed. Check the token's repository access.")
    return result["data"]


def card(title, rows, footer):
    height = 100 + len(rows) * 32
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" viewBox="0 0 495 {height}">',
             f'<rect x="1" y="1" width="493" height="{height-2}" rx="16" fill="#0D1424" stroke="#34425A"/>',
             '<g font-family="Verdana,sans-serif" font-size="13" fill="#C5D1E3">',
             f'<text x="24" y="34" fill="#48E4DC" font-size="17">{html.escape(title)}</text>']
    for index, (label, value) in enumerate(rows):
        y = 70 + index * 32
        parts += [f'<text x="24" y="{y}">{html.escape(label)}</text>',
                  f'<text x="465" y="{y}" text-anchor="end" fill="#B794F6">{html.escape(str(value))}</text>']
    parts += [f'<text x="24" y="{height-18}" font-size="10" fill="#9AAAC2">{html.escape(footer)}</text>', '</g></svg>']
    return "".join(parts)


def main():
    if not os.environ.get("STATS_TOKEN", "").strip():
        raise RuntimeError("Add a repository Actions secret named STATS_TOKEN in Kaleab-y/Kaleab-y.")
    now = dt.datetime.now(dt.timezone.utc)
    date = now.date().isoformat()
    data = graphql('''query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) { contributionsCollection(from:$from, to:$to) {
        totalCommitContributions totalPullRequestContributions
        totalIssueContributions totalPullRequestReviewContributions
        restrictedContributionsCount
      } }
    }''', {"login": LOGIN, "from": (now-dt.timedelta(days=365)).isoformat(), "to": now.isoformat()})
    activity = data["user"]["contributionsCollection"]
    repos = 0
    private = 0
    languages = collections.Counter()
    cursor = None
    while True:
        data = graphql('''query($login:String!, $cursor:String) {
          user(login:$login) { repositories(first:100, after:$cursor,
            ownerAffiliations:[OWNER], isFork:false) {
            pageInfo { hasNextPage endCursor }
            nodes { isPrivate languages(first:100) { edges { size node { name } } } }
          } }
        }''', {"login": LOGIN, "cursor": cursor})
        connection = data["user"]["repositories"]
        for repo in connection["nodes"]:
            repos += 1
            private += int(repo["isPrivate"])
            for edge in repo["languages"]["edges"]:
                languages[edge["node"]["name"]] += edge["size"]
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    if private == 0:
        raise RuntimeError("No private repositories are accessible. Check the stats token's repository selection.")
    destination = Path("assets")
    destination.mkdir(exist_ok=True)
    rows = [("Commits", activity["totalCommitContributions"]),
            ("Pull requests", activity["totalPullRequestContributions"]),
            ("Issues", activity["totalIssueContributions"]),
            ("Code reviews", activity["totalPullRequestReviewContributions"]),
            ("Additional anonymous private activity", activity["restrictedContributionsCount"]),
            ("Owned repositories (excluding forks)", repos),
            ("Private owned repositories", private)]
    destination.joinpath("private-stats.svg").write_text(card("Kaleab's GitHub activity", rows,
        f"Last 365 days; repositories accessible to stats token | Updated {date}"), encoding="utf-8")
    total = sum(languages.values())
    if total == 0:
        raise RuntimeError("No language data returned; refusing to publish an empty chart.")
    rows = [(name, f"{size/total:.1%}") for name, size in languages.most_common(8)]
    destination.joinpath("private-languages.svg").write_text(card("Languages across public + private code", rows,
        f"Owned non-fork repositories; measured by code bytes | Updated {date}"), encoding="utf-8")
    print("Aggregate SVG cards generated. No repository identifiers were saved.")


if __name__ == "__main__":
    main()
