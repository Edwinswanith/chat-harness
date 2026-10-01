import asyncio


class R2Storage:
    """S3-compatible Cloudflare R2 object storage; credentials never leave the server."""

    def __init__(self, bucket, endpoint_url, access_key_id, secret_access_key):
        import boto3
        self.bucket = bucket
        self.provider = "r2"
        self.client = boto3.client("s3", endpoint_url=endpoint_url,
                                   aws_access_key_id=access_key_id,
                                   aws_secret_access_key=secret_access_key,
                                   region_name="auto")

    async def write(self, key, data):
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=data)

    async def read(self, key):
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)

    async def delete(self, key):
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    def metadata(self, key):
        return {"provider": self.provider, "bucket": self.bucket, "key": key}
