"""Constructed migration case: the supplied input has no missing numeric values.

The generated null-boundary probe exposes astype(str)'s changed missingness.
"""


def transform(df):
    converted = df["value"].astype(str)
    return converted.isna().astype("int64").to_frame("missing_indicator")


def existing_test(df):
    assert transform(df)["missing_indicator"].eq(0).all()

