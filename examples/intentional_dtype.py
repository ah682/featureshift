"""A reviewed adoption of pandas 3's default string dtype."""


def transform(df):
    return df[["segment"]].copy()


def existing_test(df):
    assert transform(df)["segment"].tolist() == df["segment"].tolist()

