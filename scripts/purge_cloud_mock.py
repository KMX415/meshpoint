"""Delete mock data from DynamoDB while preserving API keys.

Usage:
    python scripts/purge_cloud_mock.py
"""
import boto3

TABLE_NAME = "MeshRadar"

def main():
    table = boto3.resource("dynamodb").Table(TABLE_NAME)

    response = table.scan(ProjectionExpression="PK, SK")
    items = response.get("Items", [])

    while response.get("LastEvaluatedKey"):
        response = table.scan(
            ProjectionExpression="PK, SK",
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    deleted = 0
    kept = 0

    with table.batch_writer() as batch:
        for item in items:
            pk = item["PK"]
            if pk.startswith("APIKEY#"):
                kept += 1
                continue
            batch.delete_item(Key={"PK": pk, "SK": item["SK"]})
            deleted += 1

    print(f"Deleted {deleted} items (kept {kept} API keys)")


if __name__ == "__main__":
    main()
