import argparse

import boto3


def configure_bucket(bucket_name: str) -> None:
    s3 = boto3.client("s3")

    s3.create_bucket(Bucket=bucket_name)

    s3.put_bucket_versioning(
        Bucket=bucket_name,
        VersioningConfiguration={"Status": "Enabled"},
    )

    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket_name,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "prevent-silent-overwrites",
                    "Status": "Enabled",
                    "Filter": {},
                    "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                }
            ]
        },
    )

    print(f"Configured S3 bucket {bucket_name} with versioning and lifecycle policy")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enable S3 versioning and lifecycle policy")
    parser.add_argument("bucket_name", help="Name of the S3 bucket to configure")
    args = parser.parse_args()

    configure_bucket(args.bucket_name)
