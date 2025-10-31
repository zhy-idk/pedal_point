# GCS Upload Troubleshooting Guide

## Issue: NoSuchKey Error

The error `NoSuchKey: No such object: pedalpoint_bucket/products/22/pedalpoint_logo.png` indicates that the file doesn't exist in the bucket when trying to access it. This usually means:

1. **The upload is failing silently** - The file never actually gets uploaded
2. **The upload succeeds but to wrong path** - File is uploaded but to a different location
3. **Permissions issue** - Service account doesn't have upload permissions

## What Was Fixed

### 1. Improved Credential File Discovery
- The settings now search for credentials in multiple locations:
  - `/etc/secrets/` (Render secrets)
  - Absolute path (if provided)
  - `BASE_DIR/` (project root)
  - `BASE_DIR/pedal_point/` (pedal_point subdirectory)
  - Settings directory
- Uses absolute paths to avoid path resolution issues

### 2. Credential Validation
- Validates that credentials file is valid JSON
- Checks that it's a service account key
- Shows which service account is being used

### 3. Better Error Logging
- Added detailed logging in storage backend
- Shows exactly where credentials are found (or not found)
- Logs upload progress and errors

### 4. Environment Variable Sync
- Sets `GOOGLE_APPLICATION_CREDENTIALS` env var when credentials file is found
- Ensures both django-storages and Google Cloud libraries can access credentials

## Testing Your Configuration

Run the diagnostic script to test your GCS setup:

```bash
cd pedal_point
python test_gcs_upload.py
```

This will:
- Verify all settings are correct
- Test storage backend initialization
- Attempt a test upload
- Verify the file exists
- Generate a URL
- Read the file back
- Clean up the test file

## Common Issues and Solutions

### Issue 1: Credentials File Not Found

**Symptoms:**
- Warning messages about credentials file not found
- Uploads fail silently

**Solution:**
1. Verify the credentials file exists at: `pedal_point/pedalpoint-474521-33b822d2861b.json`
2. Check that `GOOGLE_APPLICATION_CREDENTIALS` env var points to the correct file
3. Use absolute path if relative path doesn't work:
   ```
   GOOGLE_APPLICATION_CREDENTIALS=C:\Users\ralph\Desktop\pogramming\html\system_pedal_point\pedal_point\pedalpoint-474521-33b822d2861b.json
   ```

### Issue 2: Wrong Bucket Name

**Symptoms:**
- Upload appears to succeed but file doesn't exist
- Errors about bucket not found

**Solution:**
1. Verify bucket name in GCS console matches `GS_BUCKET_NAME`
2. Bucket names are case-sensitive
3. Check for typos (e.g., `pedalpoint_bucket` vs `pedalpoint-bucket`)

### Issue 3: Service Account Permissions

**Symptoms:**
- Uploads fail with permission errors
- `NoSuchKey` error when accessing files

**Solution:**
1. Verify service account `pedalpoint-storage-14@pedalpoint-474521.iam.gserviceaccount.com` has:
   - `Storage Object Admin` role (for uploads)
   - `Storage Object Viewer` role (for reads)
2. Check bucket-level IAM permissions
3. Ensure the service account key file matches the service account with permissions

### Issue 4: Bucket Doesn't Exist

**Symptoms:**
- Errors about bucket not found
- Uploads fail immediately

**Solution:**
1. Create the bucket in GCS console if it doesn't exist
2. Verify bucket name is correct
3. Check project ID matches: `pedalpoint-474521`

## Environment Variables Checklist

Verify these are set correctly:

```bash
USE_GCS=True
GS_BUCKET_NAME=pedalpoint_bucket
GS_PROJECT_ID=pedalpoint-474521
GOOGLE_APPLICATION_CREDENTIALS=pedalpoint-474521-33b822d2861b.json
```

## Debugging Steps

1. **Check Django startup logs** - Look for GCS initialization messages:
   ```
   GCS: Bucket name: pedalpoint_bucket
   GCS: Using credentials from file: ...
   GCS: Credentials configured: ...
   ```

2. **Check storage backend logs** - When uploading, you should see:
   ```
   GCS _save: Starting upload for products/22/pedalpoint_logo.png
   GCS _save: File uploaded successfully to products/22/pedalpoint_logo.png
   GCS: Verified file exists at products/22/pedalpoint_logo.png
   ```

3. **Run diagnostic script** - Use `test_gcs_upload.py` to test the connection

4. **Check GCS Console** - Manually verify files exist in the bucket

5. **Check service account** - Verify the JSON key file matches the service account with permissions

## Additional Notes

- The `NoSuchKey` error appears when **accessing** a file, not necessarily when uploading
- If uploads are failing silently, check Django logs for error messages
- The storage backend will log detailed error information if uploads fail
- Make sure the bucket exists and is accessible from your service account

