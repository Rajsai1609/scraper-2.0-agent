"""Tests for the strict USA-only geography gate."""
from __future__ import annotations

import pytest

from src.enrichment.geography import is_usa_job


# ---------------------------------------------------------------------------
# MUST RETURN FALSE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("location", [
    "Remote - Mexico, Remote",
    "Remote - Denmark, Remote",
    "Remote - Poland, Remote",
    "Remote - Germany, Remote",
    "CA-Remote-British Columbia, Remote",
    "Remote - Canada, Remote",
    "London, UK",
    "Toronto, ON",
    "Bangalore, India",
    "Remote - Europe",
    "Remote - EMEA",
    "Remote - Global",
    "Worldwide",
    "Remote - Sweden, Remote",
    "Remote - Australia, Remote",
    "Remote - Ireland, Remote",
    "Paris, France",
    "Berlin, Germany",
    "Amsterdam, Netherlands",
    "Remote - anywhere",
    "International / Remote",
])
def test_must_return_false(location: str) -> None:
    assert is_usa_job(location) is False, f"Expected False for: {location!r}"


# ---------------------------------------------------------------------------
# MUST RETURN TRUE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("location", [
    "Seattle, WA",
    "New York, NY",
    "San Francisco, CA",
    "Austin, TX 78701",
    "Remote - US Only",
    "US-Remote",
    "Remote, United States",
    "United States",
    "Remote",
    "Chicago, Illinois",
    "Boston, MA",
    "Bothell, WA 98011",
    "San Francisco, New York, Seattle",
    "Remote - US: Select locations",
    "Indianapolis, IN",
    "Portland, OR",
    "Nashville, TN",
    "Denver, CO",
    "Miami, FL",
    "Pacific Northwest",
    "Midwest",
    "Northeast",
])
def test_must_return_true(location: str) -> None:
    assert is_usa_job(location) is True, f"Expected True for: {location!r}"


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestStep1Reject:
    def test_uk_word_boundary_not_bulk(self) -> None:
        """'uk' inside a word must NOT trigger rejection."""
        assert is_usa_job("bulk operations, Seattle WA") is True

    def test_india_not_indianapolis(self) -> None:
        """'india' must not be found inside 'Indianapolis'."""
        assert is_usa_job("Indianapolis, IN") is True

    def test_korea_word_boundary(self) -> None:
        assert is_usa_job("South Korea") is False

    def test_south_africa_full_phrase(self) -> None:
        assert is_usa_job("Johannesburg, South Africa") is False

    def test_global_remote(self) -> None:
        assert is_usa_job("Global Remote") is False

    def test_emea_apac(self) -> None:
        assert is_usa_job("EMEA / APAC") is False


class TestStep2Accept:
    def test_usa_uppercase(self) -> None:
        assert is_usa_job("USA") is True

    def test_us_dot_notation(self) -> None:
        assert is_usa_job("U.S.") is True

    def test_usa_dot_notation(self) -> None:
        assert is_usa_job("U.S.A") is True

    def test_zip_code_only(self) -> None:
        assert is_usa_job("94105") is True

    def test_us_remote_hyphen(self) -> None:
        assert is_usa_job("US-Remote") is True

    def test_remote_us_phrase(self) -> None:
        assert is_usa_job("Remote - US") is True


class TestStep3StateName:
    def test_illinois(self) -> None:
        assert is_usa_job("Chicago, Illinois") is True

    def test_washington_state(self) -> None:
        assert is_usa_job("Washington") is True

    def test_district_of_columbia(self) -> None:
        assert is_usa_job("District of Columbia") is True


class TestStep4Cities:
    def test_pacific_northwest_region(self) -> None:
        assert is_usa_job("Pacific Northwest") is True

    def test_midwest_region(self) -> None:
        assert is_usa_job("Midwest") is True

    def test_northeast_region(self) -> None:
        assert is_usa_job("Northeast") is True

    def test_multiple_cities(self) -> None:
        assert is_usa_job("San Francisco, New York, Seattle") is True


class TestStep5StateAbbr:
    def test_safe_abbr_end_of_string(self) -> None:
        # Tucson uses AZ (safe abbreviation) — not in the cities list, so Step 5 must accept it
        assert is_usa_job("Tucson, AZ") is True

    def test_safe_abbr_with_zip(self) -> None:
        assert is_usa_job("Austin, TX 78701") is True

    def test_collision_abbr_with_city(self) -> None:
        assert is_usa_job("Portland, OR") is True

    def test_collision_abbr_without_city_is_false(self) -> None:
        """OR alone without a known US city → False (strict mode)."""
        assert is_usa_job("OR") is False


class TestStep6Remote:
    def test_blank_location(self) -> None:
        assert is_usa_job("") is True

    def test_remote_work_mode_hint(self) -> None:
        assert is_usa_job("", work_mode="remote") is True

    def test_remote_no_country(self) -> None:
        assert is_usa_job("Remote") is True

    def test_remote_plus_non_usa_is_false(self) -> None:
        assert is_usa_job("Remote - Germany, Remote") is False

    def test_remote_plus_us_state(self) -> None:
        assert is_usa_job("Remote, Seattle WA") is True
