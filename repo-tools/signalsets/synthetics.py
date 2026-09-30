"""Carry model repos' synthetics into the make repo.

A synthetic refers to the signals it is computed from by id, and merging renames
signals: the signal prefix is rewritten, a signal equal to one already merged
is dropped for it, and duplicate ids get a version suffix. So a synthetic keeps
a reference to each signal object it reads, every drop is recorded as an alias
to the object kept instead, and the references resolve to final ids only after
all renaming is done.
"""
import copy

from .utils import replace_signal_prefix


class SignalAliases:
    """Which merged signal object stands in for each dropped one."""

    def __init__(self):
        # Keyed by id() of the dropped object, which the value keeps alive so
        # its id() cannot be reused by another object.
        self._replacements = {}

    def record(self, dropped, kept):
        if dropped is not kept:
            self._replacements[id(dropped)] = (dropped, kept)

    def update(self, other):
        self._replacements.update(other._replacements)

    def resolve(self, signal):
        seen = set()
        while id(signal) in self._replacements and id(signal) not in seen:
            seen.add(id(signal))
            signal = self._replacements[id(signal)][1]
        return signal


def formula_signal_ids(formula):
    """The signal ids a formula reads, or None for an op this tool doesn't know."""
    op = formula.get("op")
    if op == "ratio":
        return [formula["a"], formula["b"]]
    if op == "select":
        cases = formula["cases"]
        return list(cases.keys()) + list(cases.values())
    return None


def collect_synthetics(signalset_data, signal_objects, signal_prefix):
    """This signalset's synthetics, each with the signal objects it reads.

    Args:
        signalset_data: One signalset file's data
        signal_objects: Its signal ids, before the prefix rewrite, to the
            signal objects the merge kept for them
        signal_prefix: The make's signal prefix, or None

    Returns:
        A list of (synthetic, references) pairs, where references maps each
        signal id the formula reads to its signal object, or None when a
        signal it reads is not among this signalset's merged commands.
    """
    collected = []
    for synthetic in signalset_data.get("synthetics", []):
        signal_ids = formula_signal_ids(synthetic.get("formula", {}))
        if signal_ids is None:
            print(f"Skipping synthetic {synthetic.get('id')}: unknown formula op")
            continue
        references = {signal_id: signal_objects.get(signal_id) for signal_id in signal_ids}
        if any(reference is None for reference in references.values()):
            missing = [signal_id for signal_id, reference in references.items() if reference is None]
            print(f"Skipping synthetic {synthetic.get('id')}: reads {', '.join(missing)}, which no merged command has")
            continue
        synthetic = copy.deepcopy(synthetic)
        if signal_prefix:
            synthetic["id"] = replace_signal_prefix(synthetic["id"], signal_prefix)
        collected.append((synthetic, references))
    return collected


def resolve_synthetics(collected, aliases):
    """The synthetics with every signal they read under its final id.

    Run after all signal renaming. A synthetic identical to one already kept is
    dropped; one that shares an id with a different definition gets a version
    suffix, as signals do.
    """
    resolved = []
    definitions_by_id = {}
    for synthetic, references in collected:
        final_ids = {signal_id: aliases.resolve(signal)["id"] for signal_id, signal in references.items()}
        formula = synthetic["formula"]
        if formula["op"] == "ratio":
            formula["a"] = final_ids[formula["a"]]
            formula["b"] = final_ids[formula["b"]]
        else:
            formula["cases"] = {final_ids[key]: final_ids[value] for key, value in formula["cases"].items()}

        base_id = synthetic["id"]
        definition = {k: v for k, v in synthetic.items() if k != "id"}
        versions = definitions_by_id.setdefault(base_id, [])
        if definition in versions:
            continue
        versions.append(definition)
        if len(versions) > 1:
            synthetic["id"] = f"{base_id}_V{len(versions)}"
        resolved.append(synthetic)
    return resolved
