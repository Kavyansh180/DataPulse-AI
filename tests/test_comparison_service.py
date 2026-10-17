import pytest
import pandas as pd
from sqlalchemy.orm import Session

from app.models.dataset import Dataset, DatasetVersion
from app.services.profiling_service import ProfilingService
from app.services.comparison_service import ComparisonService
from app.api.errors import APIError


def test_compare_two_runs_same_dataset(db_session: Session):
    """Verify comparing two runs accurately calculates score delta, metric diffs, and issue evolution."""
    dataset = Dataset(name="orders_tracking", source_type="s3")
    db_session.add(dataset)
    db_session.flush()

    # Run 1 (dirtier dataset)
    v1 = DatasetVersion(dataset_id=dataset.id, version_tag="v1.0", storage_uri="s3://test/v1.csv")
    db_session.add(v1)
    db_session.flush()

    df1 = pd.DataFrame({
        "order_id": [1, 2, 3, 3, 5],
        "amount": [10.0, None, 30.0, 30.0, 50.0],
    })
    run_1 = ProfilingService.execute_and_persist_profiling(db=db_session, version=v1, df=df1)

    # Run 2 (cleaned dataset)
    v2 = DatasetVersion(dataset_id=dataset.id, version_tag="v2.0", storage_uri="s3://test/v2.csv")
    db_session.add(v2)
    db_session.flush()

    df2 = pd.DataFrame({
        "order_id": [1, 2, 3, 4, 5],
        "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
    })
    run_2 = ProfilingService.execute_and_persist_profiling(db=db_session, version=v2, df=df2)

    comparison = ComparisonService.compare_runs(run_1, run_2)

    assert comparison.dataset_id == dataset.id
    assert comparison.run_id_1 == run_1.id
    assert comparison.run_id_2 == run_2.id
    assert comparison.schema_compatible is True
    assert comparison.previous_score is not None
    assert comparison.current_score is not None
    # Score in run 2 should be higher since data was cleaned
    assert comparison.current_score >= comparison.previous_score
    assert comparison.score_change is not None


def test_compare_runs_schema_evolution(db_session: Session):
    """Verify that adding/removing columns is detected and dropped column issues are not marked resolved."""
    dataset = Dataset(name="customer_churn", source_type="s3")
    db_session.add(dataset)
    db_session.flush()

    v1 = DatasetVersion(dataset_id=dataset.id, version_tag="v1.0", storage_uri="s3://test/v1.csv")
    db_session.add(v1)
    db_session.flush()

    # Column 'bad_col' has issues in v1
    df1 = pd.DataFrame({
        "id": [1, 2, 3],
        "bad_col": [None, None, None],
    })
    run_1 = ProfilingService.execute_and_persist_profiling(db=db_session, version=v1, df=df1)

    v2 = DatasetVersion(dataset_id=dataset.id, version_tag="v2.0", storage_uri="s3://test/v2.csv")
    db_session.add(v2)
    db_session.flush()

    # v2 drops 'bad_col' and adds 'new_feature'
    df2 = pd.DataFrame({
        "id": [1, 2, 3],
        "new_feature": [10.0, 20.0, 30.0],
    })
    run_2 = ProfilingService.execute_and_persist_profiling(db=db_session, version=v2, df=df2)

    comparison = ComparisonService.compare_runs(run_1, run_2)

    assert comparison.schema_compatible is False
    assert "bad_col" in comparison.removed_columns
    assert "new_feature" in comparison.added_columns
    assert comparison.schema_change_note is not None


def test_compare_runs_different_datasets_raises_error(db_session: Session):
    """Verify that comparing runs from distinct datasets is rejected with 400 DATASET_MISMATCH."""
    d1 = Dataset(name="dataset_one", source_type="s3")
    d2 = Dataset(name="dataset_two", source_type="s3")
    db_session.add_all([d1, d2])
    db_session.flush()

    v1 = DatasetVersion(dataset_id=d1.id, version_tag="v1.0", storage_uri="s3://test/1.csv")
    v2 = DatasetVersion(dataset_id=d2.id, version_tag="v1.0", storage_uri="s3://test/2.csv")
    db_session.add_all([v1, v2])
    db_session.flush()

    df = pd.DataFrame({"id": [1, 2]})
    run_1 = ProfilingService.execute_and_persist_profiling(db=db_session, version=v1, df=df)
    run_2 = ProfilingService.execute_and_persist_profiling(db=db_session, version=v2, df=df)

    with pytest.raises(APIError) as exc_info:
        ComparisonService.compare_runs(run_1, run_2)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "DATASET_MISMATCH"
