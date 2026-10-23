"""
Tests for catalog models and utilities.
"""

import pytest
from django.db import IntegrityError

from catalog.models import InventoryItem, Manufacturer, ManufacturerAlias, Part
from catalog.utils import normalize_mpn, normalize_name


# ---------------------------------------------------------------------------
# normalize_mpn
# ---------------------------------------------------------------------------

class TestNormalizeMpn:
    def test_strips_spaces(self):
        assert normalize_mpn("LM 317 T") == "LM317T"

    def test_strips_dashes(self):
        assert normalize_mpn("LM-317-T") == "LM317T"

    def test_strips_dots(self):
        assert normalize_mpn("LM.317.T") == "LM317T"

    def test_uppercases(self):
        assert normalize_mpn("lm317t") == "LM317T"

    def test_combined(self):
        assert normalize_mpn(" lm-317.t ") == "LM317T"

    def test_empty(self):
        assert normalize_mpn("") == ""


# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------

class TestNormalizeName:
    def test_uppercases(self):
        assert normalize_name("Texas Instruments") == "TEXAS INSTRUMENTS"

    def test_strips_punctuation(self):
        assert normalize_name("Texas, Instruments.") == "TEXAS INSTRUMENTS"

    def test_collapses_whitespace(self):
        assert normalize_name("Texas  Instruments") == "TEXAS INSTRUMENTS"

    def test_strips_leading_trailing(self):
        assert normalize_name("  Texas Instruments  ") == "TEXAS INSTRUMENTS"


# ---------------------------------------------------------------------------
# Part unique_together constraint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPartUniqueTogether:
    def test_duplicate_mpn_normalized_and_manufacturer_raises(self):
        mfr = Manufacturer.objects.create(
            name="Test Mfr",
            name_normalized="TEST MFR",
        )
        Part.objects.create(
            mpn="LM317T",
            mpn_normalized="LM317T",
            manufacturer=mfr,
        )
        with pytest.raises(IntegrityError):
            Part.objects.create(
                mpn="LM317T",
                mpn_normalized="LM317T",
                manufacturer=mfr,
            )

    def test_same_mpn_different_manufacturer_allowed(self):
        mfr1 = Manufacturer.objects.create(name="Mfr One", name_normalized="MFR ONE")
        mfr2 = Manufacturer.objects.create(name="Mfr Two", name_normalized="MFR TWO")
        p1 = Part.objects.create(mpn="LM317T", mpn_normalized="LM317T", manufacturer=mfr1)
        p2 = Part.objects.create(mpn="LM317T", mpn_normalized="LM317T", manufacturer=mfr2)
        assert p1.pk != p2.pk


# ---------------------------------------------------------------------------
# ManufacturerAlias unique constraint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestManufacturerAliasUnique:
    def test_duplicate_alias_normalized_raises(self):
        mfr = Manufacturer.objects.create(name="Texas Instruments", name_normalized="TEXAS INSTRUMENTS")
        ManufacturerAlias.objects.create(manufacturer=mfr, alias_normalized="TI")
        with pytest.raises(IntegrityError):
            ManufacturerAlias.objects.create(manufacturer=mfr, alias_normalized="TI")

    def test_different_aliases_allowed(self):
        mfr = Manufacturer.objects.create(name="Texas Instruments", name_normalized="TEXAS INSTRUMENTS")
        a1 = ManufacturerAlias.objects.create(manufacturer=mfr, alias_normalized="TI")
        a2 = ManufacturerAlias.objects.create(manufacturer=mfr, alias_normalized="TI INC")
        assert a1.pk != a2.pk


# ---------------------------------------------------------------------------
# InventoryItem creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestInventoryItemCreation:
    def test_create_without_part(self, company):
        item = InventoryItem.objects.create(
            company=company,
            mpn_raw="LM317T",
            manufacturer_raw="Texas Instruments",
            quantity=500,
            source=InventoryItem.Source.MANUAL,
        )
        assert item.pk is not None
        assert item.part is None
        assert item.is_active is True

    def test_create_with_part(self, company):
        mfr = Manufacturer.objects.create(name="TI", name_normalized="TI")
        part = Part.objects.create(mpn="LM317T", mpn_normalized="LM317T", manufacturer=mfr)
        item = InventoryItem.objects.create(
            company=company,
            part=part,
            mpn_raw="LM317T",
            manufacturer_raw="TI",
            quantity=100,
            source=InventoryItem.Source.CSV,
        )
        assert item.part == part
