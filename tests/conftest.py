from pathlib import Path

import pandas as pd
import pytest

from unbundle import load_sample

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample() -> pd.DataFrame:
    """The bundled Ken French sample from July 1963, the usual start of the Compustat era."""
    return load_sample().loc["1963-07":]


@pytest.fixture(scope="session")
def size_value(sample) -> pd.DataFrame:
    cols = ["S1V1", "S1V3", "S1V5", "S3V1", "S3V3", "S3V5", "S5V1", "S5V3", "S5V5"]
    return sample[cols].sub(sample["RF"], axis=0)


@pytest.fixture
def fixture_text():
    def read(name: str) -> str:
        return (FIXTURES / name).read_bytes().decode("latin-1")

    return read
