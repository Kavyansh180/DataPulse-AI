import io
import csv
from typing import Tuple, Optional, List
import pandas as pd

from app.core.config import get_settings
from app.api.errors import APIError

settings = get_settings()


class CSVValidationService:
    """Service providing robust, secure ingestion and validation for CSV files."""

    @staticmethod
    def validate_file_metadata(filename: Optional[str], content_type: Optional[str] = None) -> None:
        """Validate filename extension and safety."""
        if not filename or not filename.strip():
            raise APIError(
                status_code=400,
                message="No filename provided in upload payload.",
                code="INVALID_FILENAME",
            )

        clean_name = filename.strip().lower()
        if not clean_name.endswith(".csv"):
            raise APIError(
                status_code=400,
                message=f"Invalid file extension for '{filename}'. Only .csv files are supported.",
                code="UNSUPPORTED_FILE_TYPE",
            )

    @classmethod
    def parse_and_validate_csv(cls, file_bytes: bytes, filename: str) -> Tuple[pd.DataFrame, int, int]:
        """Validate raw bytes, detect encoding, check structure, and parse into a DataFrame.

        Returns:
            (dataframe, row_count, column_count)
        Raises:
            APIError with appropriate status codes on validation failure.
        """
        # 1. Check size limit
        byte_size = len(file_bytes)
        if byte_size == 0:
            raise APIError(
                status_code=400,
                message=f"Uploaded file '{filename}' is empty (0 bytes).",
                code="EMPTY_FILE",
            )

        if byte_size > settings.MAX_UPLOAD_SIZE_BYTES:
            max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise APIError(
                status_code=413,
                message=f"File exceeds maximum allowed upload size of {max_mb} MB.",
                code="FILE_TOO_LARGE",
            )

        # 2. Detect encoding
        encoding = None
        decoded_text = None
        for candidate_enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                decoded_text = file_bytes.decode(candidate_enc)
                encoding = candidate_enc
                break
            except UnicodeDecodeError:
                continue

        if decoded_text is None:
            raise APIError(
                status_code=400,
                message="Unable to decode CSV file. Please upload a valid UTF-8 or Latin-1 encoded CSV.",
                code="INVALID_ENCODING",
            )

        # Check for whitespace-only content
        if not decoded_text.strip():
            raise APIError(
                status_code=400,
                message=f"Uploaded CSV '{filename}' contains only whitespace or blank content.",
                code="EMPTY_FILE",
            )

        # 3. Check CSV header structure & duplicate columns
        stream = io.StringIO(decoded_text)
        try:
            reader = csv.reader(stream)
            header_row = next(reader, None)
        except Exception as exc:
            raise APIError(
                status_code=400,
                message=f"Malformed CSV header: {str(exc)}",
                code="MALFORMED_CSV",
            )

        if not header_row or all(col.strip() == "" for col in header_row):
            raise APIError(
                status_code=400,
                message="CSV file is missing a valid header row.",
                code="MISSING_HEADERS",
            )

        # Detect duplicate column names in header
        seen_cols = set()
        duplicates = set()
        for col in header_row:
            col_clean = col.strip()
            if col_clean in seen_cols:
                duplicates.add(col_clean)
            seen_cols.add(col_clean)

        if duplicates:
            raise APIError(
                status_code=400,
                message=f"Duplicate column names detected in CSV header: {list(duplicates)}",
                code="DUPLICATE_COLUMNS",
                details={"duplicate_columns": list(duplicates)},
            )

        # 4. Parse with Pandas
        stream.seek(0)
        try:
            df = pd.read_csv(
                stream,
                encoding=encoding,
                on_bad_lines="error",  # Raise error on malformed rows
                low_memory=False,
            )
        except csv.Error as err:
            raise APIError(
                status_code=400,
                message=f"CSV format parsing error: {str(err)}",
                code="MALFORMED_CSV",
            )
        except Exception as exc:
            raise APIError(
                status_code=400,
                message=f"Failed to parse CSV: {str(exc)}",
                code="CSV_PARSE_ERROR",
            )

        row_count, col_count = df.shape

        # 5. Check row limit
        if row_count > settings.MAX_ROW_COUNT_LIMIT:
            raise APIError(
                status_code=413,
                message=(
                    f"Dataset contains {row_count} rows, which exceeds the limit "
                    f"of {settings.MAX_ROW_COUNT_LIMIT} rows."
                ),
                code="ROW_LIMIT_EXCEEDED",
            )

        return df, row_count, col_count
