#!/usr/bin/env python3


def ecu_key(entry):
    """The address an ecu entry names, ignoring its year filter."""
    return (entry["hdr"], entry.get("eax"), entry.get("rax"))


def merge_ecu_entries(entries_by_repo):
    """
    Keep the ecu entries every model repo that maps an address agrees on.

    The same address is a different module on different models (a Ford EV's
    7E4 is its battery), and a make repo serves every model that falls back
    to it, so an address carries over only when every repo mapping it gives
    one type. A repo whose entries give an address different types in
    different years blocks it too, since the make repo can't know the year
    split. Repos that don't map an address abstain. Filters never carry over,
    as with commands.

    Args:
        entries_by_repo: Dictionary mapping repo names to their ecu entries

    Returns:
        Tuple of (agreed entries, dropped addresses with each repo's types)
    """
    opinions = {}
    for repo, entries in entries_by_repo.items():
        for entry in entries:
            opinions.setdefault(ecu_key(entry), {}).setdefault(repo, set()).add(entry["type"])

    agreed = []
    dropped = []
    for key in sorted(opinions, key=lambda k: tuple(part or "" for part in k)):
        address = {"hdr": key[0]}
        if key[1]:
            address["eax"] = key[1]
        if key[2]:
            address["rax"] = key[2]
        types = set().union(*opinions[key].values())
        if len(types) == 1:
            agreed.append({**address, "type": types.pop()})
        else:
            dropped.append({
                **address,
                "types": {repo: sorted(repo_types) for repo, repo_types in sorted(opinions[key].items())},
            })
    return agreed, dropped
