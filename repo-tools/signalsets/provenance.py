#!/usr/bin/env python3
import json
from pathlib import Path

def generate_provenance_report(signal_origins, cmd_origins, output_path):
    """
    Generate a GitHub Actions-friendly report showing which vehicle repositories
    contributed to which signals and commands in the merged result.

    Args:
        signal_origins: Dictionary mapping signal IDs to their source information
        cmd_origins: Dictionary mapping command IDs to their source information
        output_path: Path to save the report
    """
    # Generate a detailed report
    report = {
        "signalCount": len(signal_origins),
        "commandCount": len(cmd_origins),
        "repoContributions": {},
        "commands": {},
        "signals": {}
    }

    # Track contributions by repository
    for signal_id, sources in signal_origins.items():
        # Add detailed signal info
        report["signals"][signal_id] = {
            "sources": [
                {
                    "repo": source["repo"],
                    "make": source["make"],
                    "model": source["model"],
                    "file": source.get("file", "unknown"),
                    "url": f"https://github.com/OBDb/{source['repo']}/blob/main/signalsets/v3/{source.get('file', 'default.json')}"
                }
                for source in sources
            ]
        }

        # Track contribution counts by repository
        for source in sources:
            repo_name = source["repo"]
            if repo_name not in report["repoContributions"]:
                report["repoContributions"][repo_name] = {
                    "make": source["make"],
                    "model": source["model"],
                    "signalCount": 0,
                    "commandCount": 0,
                    "signals": [],
                    "commands": [],
                    "url": f"https://github.com/OBDb/{repo_name}/blob/main/signalsets/v3/default.json"
                }

            if signal_id not in report["repoContributions"][repo_name]["signals"]:
                report["repoContributions"][repo_name]["signalCount"] += 1
                report["repoContributions"][repo_name]["signals"].append(signal_id)

    # Add command origins to the report
    for cmd_id, sources in cmd_origins.items():
        report["commands"][cmd_id] = {
            "sources": [
                {
                    "repo": source["repo"],
                    "make": source["make"],
                    "model": source["model"],
                    "file": source.get("file", "unknown"),
                    "url": f"https://github.com/OBDb/{source['repo']}/blob/main/signalsets/v3/{source.get('file', 'default.json')}"
                }
                for source in sources
            ],
            "description": sources[0].get("description", "")  # Use the first source's description
        }

        # Track contribution counts by repository
        for source in sources:
            repo_name = source["repo"]
            if repo_name not in report["repoContributions"]:
                report["repoContributions"][repo_name] = {
                    "make": source["make"],
                    "model": source["model"],
                    "signalCount": 0,
                    "commandCount": 0,
                    "signals": [],
                    "commands": [],
                    "url": f"https://github.com/OBDb/{repo_name}/blob/main/signalsets/v3/default.json"
                }

            if cmd_id not in report["repoContributions"][repo_name]["commands"]:
                report["repoContributions"][repo_name]["commandCount"] += 1
                report["repoContributions"][repo_name]["commands"].append(cmd_id)

    # Sort repositories by total contribution count (signals + commands)
    sorted_repos = sorted(
        report["repoContributions"].items(),
        key=lambda x: (x[1]["signalCount"] + x[1]["commandCount"], x[1]["signalCount"]),
        reverse=True
    )

    # Generate GitHub Actions-friendly summary output
    summary = []

    # Add header with overall statistics
    summary.append(f"\n**Total signals in merged output:** {report['signalCount']}")
    summary.append(f"**Total commands in merged output:** {report['commandCount']}")
    summary.append(f"**Total contributing repositories:** {len(report['repoContributions'])}\n")

    # Add repository contribution table
    summary.append("## Repository Contributions")
    summary.append("\n| Repository | Make | Model | Signal Count | Command Count | Total Contributions |")
    summary.append("| --- | --- | --- | ---: | ---: | ---: |")

    for repo_name, data in sorted_repos:
        total = data["signalCount"] + data["commandCount"]
        # Create markdown link to the repository
        repo_link = f"[{repo_name}]({data['url']})"
        summary.append(f"| {repo_link} | {data['make']} | {data['model']} | {data['signalCount']} | {data['commandCount']} | {total} |")

    # Add detailed signal provenance section
    summary.append("\n## Signal Provenance")
    summary.append("\nThis table shows all signals with their contributing repositories:")
    summary.append("\n| Signal ID | Contributing Repositories | Source Count |")
    summary.append("| --- | --- | ---: |")

    # Sort signals by number of contributing repos
    sorted_signals = sorted(
        report["signals"].items(),
        key=lambda x: len(x[1]["sources"]),
        reverse=True
    )

    for signal_id, data in sorted_signals:
        # Create list of repo links
        repo_links = []
        for src in data["sources"]:
            repo_name = src["repo"]
            repo_url = src["url"]
            repo_links.append(f"[{repo_name}]({repo_url})")

        # Join unique links with commas
        unique_links = []
        seen_repos = set()
        for link in repo_links:
            repo_name = link[link.find('[')+1:link.find(']')]
            if repo_name not in seen_repos:
                unique_links.append(link)
                seen_repos.add(repo_name)

        repo_list = ", ".join(unique_links)
        summary.append(f"| `{signal_id}` | {repo_list} | {len(data['sources'])} |")

    # Add detailed command provenance section
    summary.append("\n## Command Provenance")
    summary.append("\nThis table shows all commands with their contributing repositories:")
    summary.append("\n| Command ID | Description | Contributing Repositories | Source Count |")
    summary.append("| --- | --- | --- | ---: |")

    # Sort commands by number of contributing repos
    sorted_commands = sorted(
        report["commands"].items(),
        key=lambda x: len(x[1]["sources"]),
        reverse=True
    )

    for cmd_id, data in sorted_commands:
        # Create list of repo links
        repo_links = []
        for src in data["sources"]:
            repo_name = src["repo"]
            repo_url = src["url"]
            repo_links.append(f"[{repo_name}]({repo_url})")

        # Join unique links with commas
        unique_links = []
        seen_repos = set()
        for link in repo_links:
            repo_name = link[link.find('[')+1:link.find(']')]
            if repo_name not in seen_repos:
                unique_links.append(link)
                seen_repos.add(repo_name)

        repo_list = ", ".join(unique_links)
        description = data["description"][:50] + "..." if len(data["description"]) > 50 else data["description"]
        summary.append(f"| `{cmd_id}` | {description} | {repo_list} | {len(data['sources'])} |")

    # Note about full report
    summary.append(f"\n\nFor complete details, see the full JSON report at `{output_path}`")

    # Save the full JSON report
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    # Save the GitHub Actions-friendly markdown summary
    summary_path = output_path.with_suffix('.md')
    with open(summary_path, 'w') as f:
        f.write("\n".join(summary))

    return report, summary_path