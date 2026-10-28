"""Explicit numeric feature generation, independent of string inference."""


def transform(df):
    result = df[["spend", "visits"]].copy()
    result["spend_per_visit"] = result["spend"] / result["visits"]
    return result


def existing_test(df):
    output = transform(df)
    assert len(output) == len(df)
    assert output["spend_per_visit"].notna().all()

