"""A specimen with no photo must not crash the Reports page.

The Photo Evidence section guarded with `if row.get("_first_photo"):` — which looks
right and is not. Under pandas 3 the applied column takes the new `str` dtype, and the
None returned for a photo-less row comes back out as float NaN. NaN is truthy, so the
guard passed and st.image() was handed a float:

    AttributeError: 'float' object has no attribute 'format'

Every real dataset has photo-less rows, so this killed the page for anyone who opened it.
"""
import pandas as pd

from components.reports import _first_photo_url


class TestPhotoColumnUnderPandas3:
    def _photo_column(self, photo_urls_values):
        """Exactly what reports.py builds: apply over the photo_urls column."""
        df = pd.DataFrame(
            {
                "specimen_id": [f"s{i}" for i in range(len(photo_urls_values))],
                # Numeric columns alongside — this is what makes iterrows hand back NaN.
                "Anopheles": [1] * len(photo_urls_values),
                "photo_urls": photo_urls_values,
            }
        )
        df["_first_photo"] = df["photo_urls"].apply(_first_photo_url)
        return df

    def test_photoless_row_is_not_mistaken_for_a_photo(self):
        df = self._photo_column([[], ["https://example.test/p.png"]])

        rows = [row for _, row in df.iterrows()]
        photoless, with_photo = rows[0], rows[1]

        # The trap: NaN is truthy, so `if row.get(...)` was True for a row with no photo.
        # The check must be "is this a URL string", not "is this truthy".
        assert not isinstance(photoless.get("_first_photo"), str)
        assert isinstance(with_photo.get("_first_photo"), str)
        assert with_photo["_first_photo"] == "https://example.test/p.png"

    def test_every_row_photoless(self):
        df = self._photo_column([[], []])
        for _, row in df.iterrows():
            assert not isinstance(row.get("_first_photo"), str)

    def test_null_photo_urls_column(self):
        # Supabase returns null (not []) when the column was never written.
        df = self._photo_column([None, ["https://example.test/p.png"]])
        rows = [row for _, row in df.iterrows()]
        assert not isinstance(rows[0].get("_first_photo"), str)
        assert isinstance(rows[1].get("_first_photo"), str)


class TestFirstPhotoUrl:
    def test_returns_first_url(self):
        assert _first_photo_url(["a.png", "b.png"]) == "a.png"

    def test_empty_list(self):
        assert _first_photo_url([]) is None

    def test_not_a_list(self):
        assert _first_photo_url(None) is None
        assert _first_photo_url("not-a-list") is None
