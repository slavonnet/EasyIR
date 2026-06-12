"""Remote profile catalog helpers for UI and config flows."""

from __future__ import annotations

from collections import defaultdict

REMOTE_TYPE_CLIMATE = "climate"
REMOTE_TYPE_TV = "tv"
REMOTE_TYPE_OTHER = "other"


def split_brand_model(label: str) -> tuple[str, str]:
    """Split profile title into brand/model parts."""
    normalized = str(label).strip()
    if not normalized:
        return "Other", "Unknown model"
    if "—" in normalized:
        left, right = normalized.split("—", 1)
        return (left.strip() or "Other", right.strip() or "Unknown model")
    if "-" in normalized:
        left, right = normalized.split("-", 1)
        return (left.strip() or "Other", right.strip() or "Unknown model")
    return "Other", normalized


def climate_catalog_from_options(
    profile_options: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Build brand -> model selector options from bundled climate entries."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for option in profile_options:
        value = str(option.get("value", "")).strip()
        if not (value.startswith("climate/") and value.endswith(".json")):
            continue
        label = str(option.get("label", value)).strip()
        brand, model = split_brand_model(label)
        grouped[brand].append({"value": value, "label": model})
    catalog: dict[str, list[dict[str, str]]] = {}
    for brand in sorted(grouped, key=lambda item: item.lower()):
        catalog[brand] = sorted(grouped[brand], key=lambda item: item["label"].lower())
    return catalog


def non_climate_catalog_from_options(
    profile_options: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Build brand -> model options from non-climate profiles."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for option in profile_options:
        value = str(option.get("value", "")).strip()
        if not value:
            continue
        if value.startswith("climate/") and value.endswith(".json"):
            continue
        label = str(option.get("label", value)).strip()
        brand, model = split_brand_model(label)
        grouped[brand].append({"value": value, "label": model})
    catalog: dict[str, list[dict[str, str]]] = {}
    for brand in sorted(grouped, key=lambda item: item.lower()):
        catalog[brand] = sorted(grouped[brand], key=lambda item: item["label"].lower())
    return catalog


def tv_catalog_from_options(
    profile_options: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Build TV-only catalog using title heuristics on non-climate profiles."""
    tv_tokens = (" tv", "tv ", "television", "телев", "smart tv")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for option in profile_options:
        value = str(option.get("value", "")).strip()
        if not value:
            continue
        if value.startswith("climate/") and value.endswith(".json"):
            continue
        label = str(option.get("label", value)).strip()
        low = f" {label.lower()} "
        if not any(token in low for token in tv_tokens):
            continue
        brand, model = split_brand_model(label)
        grouped[brand].append({"value": value, "label": model})
    catalog: dict[str, list[dict[str, str]]] = {}
    for brand in sorted(grouped, key=lambda item: item.lower()):
        catalog[brand] = sorted(grouped[brand], key=lambda item: item["label"].lower())
    return catalog


def catalog_for_remote_type(
    profile_options: list[dict[str, str]],
    remote_type: str | None,
) -> dict[str, list[dict[str, str]]]:
    """Return profile catalog grouped by brand for selected type."""
    if remote_type == REMOTE_TYPE_CLIMATE:
        return climate_catalog_from_options(profile_options)
    if remote_type == REMOTE_TYPE_TV:
        return tv_catalog_from_options(profile_options)
    if remote_type == REMOTE_TYPE_OTHER:
        return non_climate_catalog_from_options(profile_options)
    return {}

