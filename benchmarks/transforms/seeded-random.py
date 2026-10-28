"""Seeded random feature repeats. Reviewed benchmark fixture."""
import numpy as np
import pandas as pd


def transform(df):
    return pd.DataFrame({"noise": np.random.default_rng(42).random(len(df))})


def existing_test(df):
    assert len(transform(df)) >= 0
