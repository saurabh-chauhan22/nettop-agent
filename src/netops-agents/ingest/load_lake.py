"""Load data/ parquet into DuckDB (local Data Lake), and optionally publish the file to S3 with --upload."""
import os
import sys
from pathlib import Path

# Allow running this file directly: put the package root (src/netops-agents) on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3
import duckdb

from base import DATA_DIR, DUCKDB_FILE
from utils.config import load_env


class DataLakeLoader:
    '''
    Load data/ parquet into DuckDB (local Data Lake)
    and publish the file to S3, where the agent ATTACHes it read-only
    '''
    def __init__(self, parquet_dir:str):
        assert parquet_dir is not None, "parquet_dir must be provided"
        self.parquet_dir = Path(parquet_dir).absolute()


    def load_parquet_to_duckdb(self, db_file:str=str(DUCKDB_FILE)):
        # Connect to DuckDB (creates the database file if it doesn't exist)
        conn = duckdb.connect(db_file)
        conn.enable_profiling()

        for parquet_file in Path(self.parquet_dir).glob('*.parquet'):
            table_name = parquet_file.stem  # Use the file name (without extension) as the table name
            # OR REPLACE so regenerated data actually lands in the lake
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_parquet('{parquet_file}')")
            print(f"Loaded {parquet_file} into table {table_name}")

        conn.close()

    def upload_to_s3(self, db_file:str=str(DUCKDB_FILE)):
        # Overwrites the S3 object, so it only runs on an explicit --upload
        bucket = os.environ["S3_LAKE_BUCKET"]  # raises if unset: fail loud, not silent
        key = os.getenv("S3_LAKE_KEY", Path(db_file).name)
        boto3.client("s3", region_name=os.getenv("AWS_REGION")).upload_file(db_file, bucket, key)
        print(f"Uploaded {db_file} to s3://{bucket}/{key}")


if __name__ == '__main__':
    loader = DataLakeLoader(parquet_dir=DATA_DIR)
    loader.load_parquet_to_duckdb()
    if '--upload' in sys.argv:
        load_env()
        loader.upload_to_s3()
