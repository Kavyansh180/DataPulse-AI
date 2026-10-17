import pytest
import io
import pandas as pd
from app.services.csv_service import CSVValidationService
from app.api.errors import APIError


def test_validate_filename_extension():
    """Verify CSVValidationService rejects non-csv extensions and empty filenames."""
    CSVValidationService.validate_file_metadata("valid_data.csv")
    CSVValidationService.validate_file_metadata("customers_2026.CSV")

    with pytest.raises(APIError) as exc_info:
        CSVValidationService.validate_file_metadata("malicious.exe")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "UNSUPPORTED_FILE_TYPE"

    with pytest.raises(APIError) as exc_info:
        CSVValidationService.validate_file_metadata("")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_FILENAME"


def test_empty_and_whitespace_csv():
    """Verify empty and whitespace-only CSV files are rejected with 400."""
    with pytest.raises(APIError) as exc_info:
        CSVValidationService.parse_and_validate_csv(b"", "empty.csv")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "EMPTY_FILE"

    with pytest.raises(APIError) as exc_info:
        CSVValidationService.parse_and_validate_csv(b"   \n  \t  \n  ", "blank.csv")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "EMPTY_FILE"


def test_missing_headers_and_duplicate_columns():
    """Verify missing headers and duplicate columns are flagged."""
    # Missing headers
    with pytest.raises(APIError) as exc_info:
        CSVValidationService.parse_and_validate_csv(b",,,,\n1,2,3,4", "no_header.csv")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "MISSING_HEADERS"

    # Duplicate column names
    duplicate_header_csv = b"id,name,email,name\n1,Alice,alice@example.com,Alice"
    with pytest.raises(APIError) as exc_info:
        CSVValidationService.parse_and_validate_csv(duplicate_header_csv, "duplicate_cols.csv")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "DUPLICATE_COLUMNS"


def test_valid_csv_parsing():
    """Verify valid CSV content parses successfully into DataFrame with correct dimensions."""
    csv_bytes = (
        b"id,name,age,salary,signup_date\n"
        b"1,Alice,28,75000,2026-01-15\n"
        b"2,Bob,34,82000,2026-02-20\n"
        b"3,Charlie,22,50000,2026-03-01\n"
    )
    df, row_count, col_count = CSVValidationService.parse_and_validate_csv(csv_bytes, "users.csv")
    assert row_count == 3
    assert col_count == 5
    assert list(df.columns) == ["id", "name", "age", "salary", "signup_date"]


def test_latin1_encoding_handling():
    """Verify non-UTF8 encodings like Latin-1 with accented characters are decoded properly."""
    content = "id,city,comment\n1,São Paulo,Excelente\n2,Zürich,Schön\n"
    latin1_bytes = content.encode("latin-1")

    df, row_count, col_count = CSVValidationService.parse_and_validate_csv(latin1_bytes, "latin1.csv")
    assert row_count == 2
    assert df["city"].iloc[0] == "São Paulo"
    assert df["city"].iloc[1] == "Zürich"
