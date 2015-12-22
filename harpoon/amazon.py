from harpoon.errors import BadAmazon
from harpoon import VERSION

from botocore.exceptions import ClientError, NoCredentialsError
from six.moves.urllib.parse import urlparse
from contextlib import contextmanager
import logging
import base64
import boto3
import os

log = logging.getLogger("harpoon.amazon.iam")

@contextmanager
def catch_no_credentials(message, **info):
    """Turn a NoCredentialsError into a BadAmazon"""
    try:
        yield
    except NoCredentialsError as error:
        if hasattr(error, "response"):
            info['error_code'] = error.response["ResponseMetadata"]["HTTPStatusCode"]
            info['error_message'] = error.response["Error"]["Message"]
        else:
            info['error_message'] = error.message

        raise BadAmazon(message, **info)

@contextmanager
def catch_boto_400(message, **info):
    """Turn a BotoServerError 400 into a BadAmazon"""
    try:
        yield
    except ClientError as error:
        if str(error.response["ResponseMetadata"]["HTTPStatusCode"]).startswith("4"):
            error_message = error.response["Error"]["Message"]
            raise BadAmazon(message, error_message=error_message, error_code=error.response["ResponseMetadata"]["HTTPStatusCode"], **info)
        else:
            raise

def assume_role(arn):
    log.info("Assuming role as %s", arn)

    session = boto3.session.Session()
    session_name = "harpoon-{0}-".format(VERSION)

    # Clear out empty values
    for name in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SECURITY_TOKEN', 'AWS_SESSION_TOKEN']:
        if name in os.environ and not os.environ[name]:
            del os.environ[name]

    sts = session.client("sts")
    with catch_no_credentials("Couldn't assume role", arn=arn):
        with catch_boto_400("Couldn't assume role", arn=arn):
            creds = sts.assume_role(RoleArn=arn, RoleSessionName=session_name)["Credentials"]

    return boto3.session.Session(
          aws_access_key_id = creds["AccessKeyId"]
        , aws_secret_access_key = creds["SecretAccessKey"]
        , aws_session_token = creds["SessionToken"]
        )

def get_s3_slip(session, location):
    parsed = urlparse(location)
    log.info("Getting slip from s3://{0}{1}".format(parsed.netloc, parsed.path))
    return session.resource("s3").Object(parsed.netloc, parsed.path[1:]).get()["Body"].read().strip()

def decrypt_kms(session, ciphertext, region):
    return session.client("kms", region).decrypt(CiphertextBlob=base64.b64decode(ciphertext))["Plaintext"]
