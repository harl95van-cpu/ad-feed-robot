# -*- coding: utf-8 -*-
"""Yandex Object Storage helpers (S3-compatible)."""
import os
import json
import mimetypes
import boto3
from botocore.exceptions import ClientError

ENDPOINT = 'https://storage.yandexcloud.net'


def client():
    return boto3.client(
        's3',
        endpoint_url=ENDPOINT,
        region_name='ru-central1',
        aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
    )


def public_url(bucket, key):
    return '%s/%s/%s' % (ENDPOINT, bucket, key)


def get_json(s3, bucket, key, default=None):
    try:
        body = s3.get_object(Bucket=bucket, Key=key)['Body'].read()
        return json.loads(body.decode('utf-8'))
    except ClientError as e:
        if e.response['Error']['Code'] in ('NoSuchKey', '404'):
            return default if default is not None else {}
        raise


def put_json(s3, bucket, key, data):
    s3.put_object(Bucket=bucket, Key=key,
                  Body=json.dumps(data, ensure_ascii=False, indent=1).encode('utf-8'),
                  ContentType='application/json; charset=utf-8')


def put_text(s3, bucket, key, text, content_type):
    s3.put_object(Bucket=bucket, Key=key, Body=text.encode('utf-8'), ContentType=content_type)


def put_file(s3, bucket, key, path):
    ctype = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    with open(path, 'rb') as f:
        s3.put_object(Bucket=bucket, Key=key, Body=f, ContentType=ctype)


def list_images(s3, bucket, prefix):
    """Map image key -> object filename.

    Keys are either an offer id (``72206.jpg``) or a micro-category
    (``cluster_psy_cbt.jpg``); the feed builder prefers the former.
    """
    images = {}
    token = None
    while True:
        kwargs = dict(Bucket=bucket, Prefix=prefix, MaxKeys=1000)
        if token:
            kwargs['ContinuationToken'] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get('Contents', []):
            filename = obj['Key'][len(prefix):]
            if '/' in filename or not filename:
                continue
            stem = filename.rsplit('.', 1)[0]
            if stem.isdigit() or stem.startswith('cluster_'):
                images[stem] = filename
        if not resp.get('IsTruncated'):
            break
        token = resp.get('NextContinuationToken')
    return images
